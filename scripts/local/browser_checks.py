"""Revisión en un navegador real (Playwright + Chromium) del servidor local. Uso: python dev.py e2e

Recorre las vistas principales en 320, 390 y 1280 px, con lectura sencilla y detallada y con letra normal
y grande, y reporta:
- errores de JavaScript y violaciones de la política de seguridad de contenidos (CSP);
- textos cortados (desbordados con overflow oculto) o que salen de la pantalla;
- violaciones de accesibilidad axe-core (WCAG 2.2 AA) con impacto serious/critical.
Guarda capturas de cada vista en --out. Termina con código 1 si encuentra algún problema.

Regresión visual: con --baseline DIR compara las capturas contra una referencia (≤ 0,5 % de píxeles
distintos por defecto, ajustable con --tolerancia) y falla si algo se movió; con --update-baseline DIR
fija la referencia copiando las capturas nuevas.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
import urllib.request
from pathlib import Path

from PIL import Image, ImageChops
from playwright.async_api import async_playwright

CLIPPED_JS = """() => {
  const out = []; const W = innerWidth;
  const sel = document.querySelector('#app') ? '#app *, #modal *' : 'body *';
  for (const el of document.querySelectorAll(sel)) {
    if (!el.offsetParent && getComputedStyle(el).position !== 'fixed') continue;
    const cs = getComputedStyle(el); if (cs.display === 'none' || cs.visibility === 'hidden') continue;
    const txt = (el.innerText || '').trim(); if (!txt || el.children.length > 3) continue;
    const r = el.getBoundingClientRect(); if (r.width < 4) continue;
    const clipped = el.scrollWidth > el.clientWidth + 1 && ['hidden','clip','auto','scroll'].includes(cs.overflowX);
    const outside = r.right > W + 1 && !el.closest('.maplibregl-control-container,.card-actions-scroll');
    if (clipped || outside) out.push({ tag: el.tagName.toLowerCase(), cls: String(el.className).slice(0, 40), text: txt.slice(0, 50),
      why: clipped ? 'cortado' : 'fuera de pantalla' });
  }
  return out;
}"""

BASE_ROUTES = [
    "mi-zona",
    "mapa",
    "riesgo",
    "riesgo?comuna=5801",
    "casos",
    "casos/penco-lirquen-2026",
    "preparate",
    "alertas",
    "privacidad",
    "calidad",
    "temporada",
]

# Páginas estáticas fuera de la SPA (se sirven bajo /web/): modo liviano, pantalla pública
# (con comuna fija para pintar datos) y la hoja imprimible. No leen las preferencias de
# lectura simple/experto ni de letra, así que se revisan una sola vez por ancho.
STATIC_PAGES = ["/web/lite.html", "/web/pantalla.html?comuna=5801", "/web/lista.html"]

AXE = Path(__file__).with_name("axe.min.js")
# axe.run sobre cada vista ya cargada: solo WCAG 2.x A/AA (incluye 2.2) y solo violaciones serious/critical.
# El lienzo WebGL y los controles internos de MapLibre/Cesium son de terceros y no los controla BRASA:
# se excluyen #map/#globe para que la auditoría mida lo que este repo puede arreglar.
AXE_RUN_JS = """async () => {
  const r = await axe.run({ exclude: [['#map'], ['#globe']] }, {
    resultTypes: ['violations'],
    runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'] }
  });
  const out = [];
  for (const v of r.violations) {
    if (v.impact !== 'serious' && v.impact !== 'critical') continue;
    for (const n of v.nodes) out.push({ rule: v.id, impact: v.impact, help: v.help, sel: (n.target || []).join(' ') });
  }
  return out;
}"""
# Excepciones justificadas, una por entrada: (id de regla, selector) → motivo. No es un cajón de sastre.
AXE_ALLOW: dict[tuple[str, str], str] = {}


def first_incident(url: str) -> str | None:
    try:
        with urllib.request.urlopen(f"{url}/api/incidents?hours=336", timeout=10) as r:
            items = json.load(r)["incidents"]
        return items[0]["id"] if items else None
    except Exception:
        return None


def compare_shots(ref: Path, new: Path) -> tuple[float, bool, Image.Image]:
    """Compara dos capturas. Devuelve (% de píxeles distintos, cambió el tamaño, imagen diff).

    Un píxel cuenta como distinto si algún canal difiere en más de 16. El diff deja la captura
    nueva con los píxeles distintos marcados en magenta; si el tamaño cambió, ambas se montan en
    un lienzo del tamaño mayor para que la zona sin solape también quede marcada.
    """
    a = Image.open(ref).convert("RGB")
    b = Image.open(new).convert("RGB")
    size_changed = a.size != b.size
    if size_changed:
        w, h = max(a.width, b.width), max(a.height, b.height)
        ca, cb = Image.new("RGB", (w, h)), Image.new("RGB", (w, h))
        ca.paste(a)
        cb.paste(b)
        a, b = ca, cb
    diff = ImageChops.difference(a, b)
    r, g, bl = diff.split()
    mask = ImageChops.lighter(ImageChops.lighter(r, g), bl).point(lambda v: 255 if v > 16 else 0)
    pct = mask.histogram()[255] / (a.width * a.height)
    marked = Image.composite(Image.new("RGB", b.size, (255, 0, 255)), b, mask)
    return (1.0 if size_changed else pct), size_changed, marked


async def main(url: str, out: Path, baseline: Path | None, update_baseline: Path | None, tolerancia: float) -> int:
    out.mkdir(parents=True, exist_ok=True)
    routes = list(BASE_ROUTES)
    incident = first_incident(url)
    routes.append(f"incendio/{incident}") if incident else print(
        "  (sin incidentes: corre `python dev.py run --demo` para revisar la ficha)"
    )
    problems: dict[tuple, set] = {}
    axe_problems: dict[tuple, set] = {}
    errors: list[str] = []
    shots: list[str] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=os.getenv("BRASA_CHROMIUM") or None)
        for width in (320, 390, 1280):
            for detail, text in (("simple", "normal"), ("experto", "grande")):
                # reduced_motion: las animaciones de entrada (.enter → rise, opacity 0→1) dejarían a axe
                # midiendo contraste a mitad de una transición: resultado no determinista.
                ctx = await browser.new_context(
                    viewport={"width": width, "height": 800 if width < 1000 else 900}, service_workers="block", reduced_motion="reduce"
                )
                await ctx.add_init_script(
                    f"localStorage.setItem('brasa:text', JSON.stringify('{text}'));"
                    f"localStorage.setItem('brasa:detail', JSON.stringify('{detail}'))"
                )
                # axe en cada página del contexto. add_init_script corre por CDP, exento de CSP: un
                # add_script_tag inline sería rechazado por script-src 'self' y contaría como error CSP.
                await ctx.add_init_script(path=AXE)
                page = await ctx.new_page()
                page.on("pageerror", lambda e: errors.append(f"JS: {str(e)[:200]}"))
                page.on(
                    "console",
                    lambda m: (
                        errors.append(f"CSP: {m.text[:200]}")
                        if any(k in m.text for k in ("Content Security Policy", "Refused to"))
                        else None
                    ),
                )
                for route in routes:
                    await page.goto(f"{url}/#/{route}")
                    await page.wait_for_timeout(1800)
                    for item in await page.evaluate(CLIPPED_JS):
                        problems.setdefault((item["why"], item["tag"], item["cls"], item["text"]), set()).add(
                            f"{route} @{width} {detail}/{text}"
                        )
                    for v in await page.evaluate(AXE_RUN_JS):
                        if (v["rule"], v["sel"]) in AXE_ALLOW:
                            continue
                        axe_problems.setdefault((v["rule"], v["impact"], v["sel"], v["help"]), set()).add(
                            f"{route} @{width} {detail}/{text}"
                        )
                    if detail == "simple":
                        name = route.replace("/", "_").replace("?", "_").replace("=", "-")
                        shots.append(f"{name}-{width}.png")
                        await page.screenshot(path=str(out / f"{name}-{width}.png"))
                if detail == "simple":
                    for path in STATIC_PAGES:
                        await page.goto(f"{url}{path}")
                        await page.wait_for_timeout(1800)
                        for item in await page.evaluate(CLIPPED_JS):
                            problems.setdefault((item["why"], item["tag"], item["cls"], item["text"]), set()).add(f"{path} @{width}")
                        for v in await page.evaluate(AXE_RUN_JS):
                            if (v["rule"], v["sel"]) in AXE_ALLOW:
                                continue
                            axe_problems.setdefault((v["rule"], v["impact"], v["sel"], v["help"]), set()).add(f"{path} @{width}")
                        name = path.lstrip("/").replace("/", "_").replace("?", "_").replace("=", "-")
                        shots.append(f"{name}-{width}.png")
                        await page.screenshot(path=str(out / f"{name}-{width}.png"))
                await ctx.close()
        await browser.close()
    for e in sorted(set(errors)):
        print("  ✗", e)
    for (why, tag, cls, txt), where in sorted(problems.items(), key=lambda kv: -len(kv[1])):
        print(f"  ✗ texto {why}: {tag}.{cls} «{txt}» ({len(where)}×, ej.: {sorted(where)[0]})")
    for (rule, impact, sel, help_), where in sorted(axe_problems.items(), key=lambda kv: (kv[0][0], kv[0][2])):
        print(f"  ✗ a11y {impact} [{rule}]: {sel} — {help_} ({len(where)}×, ej.: {sorted(where)[0]})")
    visual_fails = 0
    if update_baseline:
        update_baseline.mkdir(parents=True, exist_ok=True)
        for f in shots:
            shutil.copy2(out / f, update_baseline / f)
        print(f"  referencia visual actualizada: {len(shots)} capturas en {update_baseline}")
    elif baseline:
        compared = 0
        for f in shots:
            ref = baseline / f
            if not ref.exists():
                continue
            compared += 1
            pct, size_changed, marked = compare_shots(ref, out / f)
            fails = size_changed or pct > tolerancia
            diff_path = out / f"{f[:-4]}.diff.png"
            if fails:
                visual_fails += 1
                marked.save(diff_path)
            else:
                diff_path.unlink(missing_ok=True)
            note = " · tamaño distinto" if size_changed else ""
            print(f"  {'✗' if fails else '✓'} {f}: {pct:.2%} píxeles distintos{note}")
        if not compared:
            print(f"  ! referencia vacía o inexistente: {baseline}")
        print(
            f"  {compared} captura(s) comparadas · tolerancia {tolerancia:.2%}" + (f" · diffs en {out}/*.diff.png" if visual_fails else "")
        )
    else:
        print("  sin referencia visual (usa --baseline o --update-baseline)")
    total = len(set(errors)) + len(problems) + len(axe_problems)
    print(
        f"{'Sin problemas' if not total else f'{total} problema(s)'} · {len(routes)} vistas SPA × 3 anchos × 2 modos"
        f" + {len(STATIC_PAGES)} estáticas × 3 anchos · capturas en {out}"
    )
    return 1 if total or visual_fails else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--out", default="data/shots")
    parser.add_argument("--baseline", type=Path, help="directorio con la referencia visual a comparar")
    parser.add_argument("--update-baseline", type=Path, metavar="DIR", help="copia las capturas a DIR como nueva referencia y no compara")
    parser.add_argument("--tolerancia", type=float, default=0.005, help="fracción máxima de píxeles distintos permitida (defecto 0,5 %%)")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.url.rstrip("/"), Path(args.out), args.baseline, args.update_baseline, args.tolerancia)))

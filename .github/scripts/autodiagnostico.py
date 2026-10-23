"""Autodiagnóstico de la cara pública de BRASA (OPS-27).

Revisa cada pocas horas las páginas y endpoints públicos del sitio desplegado: código HTTP,
tiempo total y enlaces internos rotos. Umbrales explícitos: 5xx siempre alerta; más de
LENTO_PAGINA_S en una página o LENTO_API_S en un endpoint JSON alerta como «lento».

    python .github/scripts/autodiagnostico.py                  # sonda contra producción
    python .github/scripts/autodiagnostico.py --base-url URL   # otro despliegue
    python .github/scripts/autodiagnostico.py --payload p.json # sin red: respuestas grabadas

El payload es un objeto {url: {"status": N, "ms": M, "body": "…"}} sin las entradas que se
quieran simular como timeout (status 0). Sale 1 si hay hallazgos y deja alerta/titulo en
GITHUB_OUTPUT para que el workflow abra —o reutilice— un issue con etiqueta «autodiagnostico».
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET

UA = {"User-Agent": "BRASA-Chile autodiagnostico (+https://github.com/falopass/brasas)"}
BASE = "https://brasa-chile.ddiegosebastianbb.workers.dev"
LENTO_PAGINA_S = 3.0
LENTO_API_S = 1.5

PAGINAS = ["/", "/web/datos.html", "/web/preguntas.html", "/web/respuesta.html",
           "/web/lista.html", "/web/plan.html"]
APIS = ["/api/status", "/api/opendata", "/api/observations?hours=1"]

HREF = re.compile(r'<a\b[^>]*\bhref\s*=\s*["\']([^"\']+)["\']', re.I)
SITEMAP_LOC = re.compile(r"<loc>([^<]+)</loc>")


def sonda(base: str, ruta: str) -> dict:
    """GET a `ruta` con medición; nunca lanza: el fallo ES el hallazgo."""
    t0 = time.perf_counter()
    try:
        req = urllib.request.Request(base + ruta, headers=UA)
        with urllib.request.urlopen(req, timeout=20) as res:
            body = res.read().decode("utf-8", "replace")
            return {"status": res.status, "ms": round((time.perf_counter() - t0) * 1000), "body": body}
    except Exception as err:  # HTTPError trae .code; el resto es 0 (caída/timeout)
        code = getattr(err, "code", 0)
        return {"status": code, "ms": round((time.perf_counter() - t0) * 1000), "body": ""}


def sitemaps(payload: dict, base: str, get) -> list[str]:
    """Rutas del <loc> del sitemap si el payload no las trae grabadas."""
    r = payload.get("/web/sitemap.xml") or get(base, "/web/sitemap.xml")
    return [u.replace(base, "") or "/" for u in SITEMAP_LOC.findall(r.get("body", ""))]


def revisar(rutas_api: list[str], rutas_pagina: list[str], get) -> tuple[list[dict], list[str]]:
    """Corre las sondas y devuelve (hallazgos, hrefs internos vistos)."""
    hallazgos, hrefs = [], []
    for ruta in rutas_pagina + rutas_api:
        r = get(ruta)
        ms_s = r["ms"] / 1000
        if r["status"] >= 500 or r["status"] == 0:
            hallazgos.append({"url": ruta, "fallo": f"HTTP {r['status']}" if r['status'] else "sin respuesta", "ms": r["ms"]})
        elif ms_s > (LENTO_PAGINA_S if ruta in rutas_pagina else LENTO_API_S):
            hallazgos.append({"url": ruta, "fallo": "lento", "ms": r["ms"]})
        if ruta in rutas_pagina:
            hrefs += [h for h in HREF.findall(r.get("body", "")) if h.startswith(("/web/", "/#/", "/api/"))]
    return hallazgos, hrefs


def enlaces_rotos(hrefs: list[str], get) -> list[dict]:
    """De los href internos, los que responden 404 (los #/… de la SPA no se sondan)."""
    rotos = []
    for h in sorted(set(hrefs)):
        if h.startswith("/#/"):
            continue
        ruta = h.split("?")[0]
        if get(ruta)["status"] == 404:
            rotos.append({"url": ruta, "fallo": "HTTP 404", "ms": 0})
    return rotos


def alerta_md(hallazgos: list[dict]) -> str:
    filas = "\n".join(f"| `{h['url']}` | {h['fallo']} | {h['ms']/1000:.1f} s |" for h in hallazgos)
    return ("## Autodiagnóstico de la cara pública\n\n"
            "| URL | Qué falló | Tiempo |\n|---|---|---|\n" + filas + "\n\n"
            "Qué revisar: la sección «Autodiagnóstico del sitio» de `docs/OPERACION.md`.\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default=BASE)
    ap.add_argument("--payload", help="JSON {url: {status, ms, body}} para correr sin red")
    args = ap.parse_args(argv)

    payload = json.loads(open(args.payload, encoding="utf-8").read()) if args.payload else {}
    get = (lambda ruta: payload.get(ruta) or {"status": 0, "ms": 0, "body": ""}) if args.payload \
        else (lambda ruta: sonda(args.base_url, ruta))

    rutas_pagina = PAGINAS + [r for r in sitemaps(payload, args.base_url, get) if r not in PAGINAS]
    hallazgos, hrefs = revisar(APIS, rutas_pagina, get)
    hallazgos += enlaces_rotos(hrefs, get)

    for h in hallazgos:
        print(f"::warning::{h['url']}: {h['fallo']} ({h['ms']/1000:.1f} s)")
    print(f"{len(hallazgos)} hallazgo{'s' if len(hallazgos) != 1 else ''} en {len(rutas_pagina)} páginas y {len(APIS)} endpoints")

    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as fh:
            fh.write(f"alerta={'true' if hallazgos else 'false'}\n")
            fh.write(f"titulo=Autodiagnóstico: {len(hallazgos)} hallazgo{'s' if len(hallazgos) != 1 else ''} en la cara pública\n")
    if hallazgos:
        with open("alerta.md", "w", encoding="utf-8") as fh:
            fh.write(alerta_md(hallazgos))
    return 1 if hallazgos else 0


if __name__ == "__main__":
    sys.exit(main())

"""Comprobación en navegador de la pantalla pública (UX-08). Uso:

    python dev.py run --demo            # en otra terminal (con `python dev.py seed` antes)
    .venv/bin/python scripts/local/pantalla_check.py --url 'http://127.0.0.1:8000/web/pantalla.html?comuna=13101'

Abre la página, verifica que aparezca el nombre de la comuna del parámetro ?comuna=
(código o nombre), la línea «No es una alerta oficial» y que no haya errores de
JavaScript ni de consola. Con ?comunas=a,b&rotar=N además verifica el encabezado de
rotación («Comuna 1 de N») y, si la rotación es corta, que pase a «Comuna 2 de N».
Termina con código 0 solo si todo pasa.

El parseo (?comunas=, ?rotar=) y la resolución contra el índice son funciones puras,
probadas en tests/test_pantalla_check.py sin navegador. El import de Playwright va
dentro de main() por eso.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
import unicodedata
import urllib.parse
import urllib.request

# Mismos límites que web/js/pantalla-rotacion.js.
SEGUNDOS_DEF = 45
SEGUNDOS_MIN = 5
SEGUNDOS_MAX = 300


def fold(text: str) -> str:
    """Texto comparable: minúsculas, sin tildes y con espacios simples (como backend/geo.py)."""
    normalized = unicodedata.normalize("NFKD", text.casefold())
    return " ".join("".join(ch for ch in normalized if not unicodedata.combining(ch)).split())


def comunas_pedidas(url: str) -> list[str]:
    """Parámetros de ?comunas= (código o nombre), sin vacíos ni duplicados por fold()."""
    query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    params, seen = [], set()
    for trozo in query.get("comunas", [""])[0].split(","):
        p = trozo.strip()
        key = fold(p)
        if key and key not in seen:
            seen.add(key)
            params.append(p)
    return params


def segundos_pedidos(url: str) -> int:
    """?rotar= acotado a [5, 300]; ausente, cero, negativo o no numérico cae a 45."""
    raw = urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get("rotar", [""])[0]
    try:
        n = float(raw)
    except ValueError:
        return SEGUNDOS_DEF
    if not math.isfinite(n) or n <= 0:
        return SEGUNDOS_DEF
    return int(min(max(n + 0.5, SEGUNDOS_MIN), SEGUNDOS_MAX))


def load_index(base: str) -> list[dict]:
    """Índice de comunas que sirve el propio servidor comprobado."""
    with urllib.request.urlopen(f"{base}/web/data/comunas-index.json", timeout=10) as r:
        return json.load(r)


def resolve_comuna(index: list[dict], param: str) -> dict | None:
    """Comuna del índice por código numérico o por nombre plegado (como resolveComuna de la página)."""
    if param.isdigit():
        return next((c for c in index if c["code"] == int(param)), None)
    return next((c for c in index if fold(c["name"]) == fold(param)), None)


def expected_comuna(url: str, index: list[dict] | None = None) -> dict | None:
    """Comuna que debería mostrar la página, según ?comuna= de la URL."""
    param = urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get("comuna", [""])[0].strip()
    if not param:
        return None
    if index is None:
        try:
            index = load_index(url.split("/web/")[0])
        except Exception:
            return None
    return resolve_comuna(index, param)


def expected_comunas(url: str, index: list[dict] | None = None) -> list[str]:
    """Nombre oficial de cada comuna pedida en ?comunas= (una vez por código). La que no
    resuelve queda con su texto tal cual, para que el chequeo la marque como desconocida."""
    if index is None:
        index = load_index(url.split("/web/")[0])
    names, seen = [], set()
    for param in comunas_pedidas(url):
        comuna = resolve_comuna(index, param)
        if comuna is None:
            names.append(param)
        elif comuna["code"] not in seen:
            seen.add(comuna["code"])
            names.append(comuna["name"])
    return names


def has_risk(base: str, comuna: dict) -> bool | None:
    """¿El servidor tiene riesgo sembrado para la comuna? None si no se pudo consultar."""
    try:
        with urllib.request.urlopen(f"{base}/api/risk/{comuna['code']}", timeout=10) as r:
            return bool(json.load(r).get("days"))
    except Exception:
        return None


async def main(url: str) -> int:
    from playwright.async_api import async_playwright

    base = url.split("/web/")[0]
    giratorias: list[dict] = []
    if comunas_pedidas(url):
        # ?comunas= manda sobre ?comuna=, igual que en la página.
        try:
            index = load_index(base)
        except Exception:
            print("  ✗ no se pudo leer web/data/comunas-index.json del servidor")
            return 1
        malas = [p for p in comunas_pedidas(url) if resolve_comuna(index, p) is None]
        if malas:
            print(f"  ✗ ?comunas= trae valores que no existen en el índice: {', '.join(malas)}")
            return 1
        seen: set[int] = set()
        for param in comunas_pedidas(url):
            c = resolve_comuna(index, param)
            if c["code"] not in seen:
                seen.add(c["code"])
                giratorias.append(c)
    comuna = giratorias[0] if giratorias else expected_comuna(url)
    name = comuna["name"] if comuna else None
    if comuna:
        risk = has_risk(base, comuna)
        if risk is not True:
            detalle = "no respondió" if risk is None else "respondió sin días de riesgo"
            print(f"  ✗ el demo no tiene riesgo para «{name}» ({comuna['code']}): /api/risk {detalle}")
            return 1
    errors: list[str] = []
    ok = True
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        page.on("pageerror", lambda e: errors.append(f"JS: {str(e)[:200]}"))
        page.on("console", lambda m: errors.append(f"Consola: {m.text[:200]}") if m.type == "error" else None)
        await page.goto(url)
        try:
            await page.wait_for_selector("#comuna-name:not(:empty)", timeout=20000)
        except Exception:
            ok = False
            print("  ✗ la página no mostró el encabezado de la comuna (¿servidor con datos? prueba `python dev.py run --demo`)")
        body = await page.inner_text("body")
        if name and name not in body:
            ok = False
            print(f"  ✗ no aparece el nombre de la comuna «{name}»")
        elif name:
            print(f"  · comuna «{name}» visible")
        if len(giratorias) >= 2:
            n = len(giratorias)
            segundos = segundos_pedidos(url)
            if f"Comuna 1 de {n}" not in body:
                ok = False
                print(f"  ✗ falta el encabezado de rotación «Comuna 1 de {n}»")
            else:
                print(f"  · rotación «Comuna 1 de {n}» visible")
            # Con rotación corta se espera el cambio; con una larga (hasta 300 s) solo se
            # comprueba el encabezado, porque esperar el giro haría el chequeo lentísimo.
            if segundos <= 20:
                try:
                    await page.wait_for_function(
                        f"document.body.innerText.includes('Comuna 2 de {n}')", timeout=max(20000, segundos * 1000 + 10000)
                    )
                    print(f"  · rotó a «Comuna 2 de {n}»")
                except Exception:
                    ok = False
                    print(f"  ✗ no rotó a «Comuna 2 de {n}» en el tiempo esperado")
        if "No es una alerta oficial" not in body:
            ok = False
            print("  ✗ falta la línea «No es una alerta oficial»")
        else:
            print("  · aviso «No es una alerta oficial» visible")
        if "se refresca solo cada 5 min" not in body:
            ok = False
            print("  ✗ falta la hora del último refresco")
        await browser.close()
    for e in sorted(set(errors)):
        ok = False
        print("  ✗", e)
    print("OK" if ok else "FALLÓ")
    return 0 if ok else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000/web/pantalla.html")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.url)))

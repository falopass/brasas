"""Comprobación en navegador de la pantalla pública (UX-08). Uso:

    python dev.py run --demo            # en otra terminal (con `python dev.py seed` antes)
    .venv/bin/python scripts/local/pantalla_check.py --url 'http://127.0.0.1:8000/web/pantalla.html?comuna=13101'

Abre la página, verifica que aparezca el nombre de la comuna del parámetro ?comuna=
(código o nombre), la línea «No es una alerta oficial» y que no haya errores de
JavaScript ni de consola. Termina con código 0 solo si todo pasa.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import unicodedata
import urllib.parse
import urllib.request

from playwright.async_api import async_playwright


def fold(text: str) -> str:
    """Texto comparable: minúsculas, sin tildes y con espacios simples (como backend/geo.py)."""
    normalized = unicodedata.normalize("NFKD", text.casefold())
    return " ".join("".join(ch for ch in normalized if not unicodedata.combining(ch)).split())


def expected_comuna(url: str) -> str | None:
    """Nombre de la comuna que debería mostrar la página, según ?comuna= de la URL."""
    param = urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get("comuna", [""])[0].strip()
    if not param:
        return None
    base = url.split("/web/")[0]
    try:
        with urllib.request.urlopen(f"{base}/web/data/comunas-index.json", timeout=10) as r:
            index = json.load(r)
    except Exception:
        return None
    if param.isdigit():
        hit = next((c for c in index if c["code"] == int(param)), None)
    else:
        hit = next((c for c in index if fold(c["name"]) == fold(param)), None)
    return hit["name"] if hit else None


async def main(url: str) -> int:
    name = expected_comuna(url)
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

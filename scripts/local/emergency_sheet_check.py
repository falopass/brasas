"""Prueba en navegador del FIX-18: en el celular, el modo emergencia abre la hoja completa
y al salir («Ver todo») vuelve a la mitad. Uso:

    python dev.py run --demo            # en otra terminal
    .venv/bin/python scripts/local/emergency_sheet_check.py [--url http://127.0.0.1:8000]

Crea un suscriptor y un lugar de prueba cerca de Quilpué (donde el demo siembra calor
«urgente»), abre #/mi-zona en 390 px y mide --sheet-h en ambos estados. Borra el lugar
al terminar. Termina con código 1 si la hoja no queda como corresponde.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import urllib.request

from playwright.async_api import async_playwright

PLACE = {"name": "Prueba emergencia (local)", "kind": "casa", "lat": -33.075, "lon": -71.405, "radius_km": 10}


def api(url: str, path: str, token: str | None = None, body: dict | None = None, method: str | None = None) -> dict:
    req = urllib.request.Request(f"{url}{path}", method=method or ("POST" if body is not None else "GET"),
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", **({"X-Brasa-Token": token} if token else {})})
    return json.load(urllib.request.urlopen(req, timeout=15))


async def main(url: str) -> int:
    token = api(url, "/api/subscribers", body={})["token"]
    place = api(url, "/api/places", token=token, body=PLACE)
    print(f"Lugar de prueba: {place['id']} ({PLACE['lat']}, {PLACE['lon']})")
    ok = True
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            ctx = await browser.new_context(viewport={"width": 390, "height": 844}, service_workers="block")
            await ctx.add_init_script(f"localStorage.setItem('brasa:token', JSON.stringify('{token}'))")
            page = await ctx.new_page()
            await page.goto(f"{url}/#/mi-zona")
            await page.wait_for_selector(".emergency", timeout=20000)

            async def sheet_px():
                return await page.evaluate("() => parseFloat(document.documentElement.style.getPropertyValue('--sheet-h'))")

            full = await sheet_px()
            want = round(0.9 * (await page.evaluate("() => innerHeight") - 64))
            print(f"Modo emergencia: --sheet-h = {full:.0f}px (full espera ≈{want}px)")
            ok &= abs(full - want) <= 2

            await page.click("#em-full")
            await page.wait_for_selector(".place-card", timeout=20000)
            half = await sheet_px()
            want = round(0.5 * (await page.evaluate("() => innerHeight") - 64))
            print(f"Tras «Ver todo»:  --sheet-h = {half:.0f}px (half espera ≈{want}px)")
            ok &= abs(half - want) <= 2
            await browser.close()
    finally:
        api(url, f"/api/places/{place['id']}", token=token, method="DELETE")
    print("OK" if ok else "FALLÓ")
    return 0 if ok else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.url.rstrip("/"))))

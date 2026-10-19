"""Verifica FIX-05 en un navegador real: la ficha #/incendio/<id> se actualiza sola cada 3 minutos
y NO debe devolver al lector al inicio ni quitarle el foco. Uso:

    python dev.py run --demo            (en otra terminal)
    .venv/bin/python scripts/local/check_ficha_refresco.py

Para no esperar 3 minutos, el script acelera SOLO en el navegador de prueba: intercepta la
respuesta de /web/js/views/incendio.js y baja REFRESH_MS de 180000 a 1500 ms (nada del servidor
ni del código cambia; add_init_script no sirve aquí porque la CSP del sitio lo bloquea).
Comprueba que hubo una actualización real —el innerHTML se reconstruye, así que un nodo de la
lista de evidencia queda reemplazado— y que después #view.scrollTop y el foco en #in-slider
se conservan. Termina con código 1 si falla.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import urllib.request

from playwright.async_api import async_playwright

REFRESH_LINE = "const REFRESH_MS = 3 * 60 * 1000;"
FAST_LINE = "const REFRESH_MS = 1500;"
TIMEOUT_MS = 12000


def first_incident(url: str) -> str | None:
    try:
        with urllib.request.urlopen(f"{url}/api/incidents?hours=336", timeout=10) as r:
            items = json.load(r)["incidents"]
        return items[0]["id"] if items else None
    except Exception:
        return None


async def main(url: str) -> int:
    incident = first_incident(url)
    if not incident:
        print("  ✗ sin incidentes: corre el servidor con `python dev.py run --demo`")
        return 1
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=os.getenv("BRASA_CHROMIUM") or None)
        ctx = await browser.new_context(viewport={"width": 390, "height": 844}, service_workers="block")
        patched = False

        async def speed_up(route):
            nonlocal patched
            r = await route.fetch()
            body = (await r.text()).replace(REFRESH_LINE, FAST_LINE, 1)
            patched = patched or FAST_LINE in body and REFRESH_LINE not in body
            await route.fulfill(response=r, body=body)

        await ctx.route("**/js/views/incendio.js", speed_up)
        page = await ctx.new_page()
        page_errors: list[str] = []
        page.on("pageerror", lambda e: page_errors.append(str(e)[:200]))
        await page.goto(f"{url}/#/incendio/{incident}")
        await page.wait_for_selector(".evidence-list li", timeout=15000)
        if not patched:
            print("  ✗ no se pudo acelerar el refresco (¿cambió REFRESH_MS en incendio.js?)")
            await browser.close()
            return 1

        # Scroll instantáneo: con el smooth de .panel-body la animación seguiría corriendo al
        # llegar el refresco y taparía el scrollTop que restaura keepPlace.
        await page.evaluate("""() => { const v = document.querySelector('#view');
          v.style.scrollBehavior = 'auto'; v.scrollTop = v.scrollHeight; v.style.scrollBehavior = ''; }""")
        await page.wait_for_timeout(100)

        scroll_before = await page.evaluate("() => document.querySelector('#view').scrollTop")

        # Controles que pueden tener foco: los que keepPlace reenfoca por id. El foco va con
        # preventScroll para que la vista siga abajo (en la lista de evidencia) como un lector real.
        targets = ["in-slider", "in-back", "in-call"]
        results: dict[str, str] = {}
        scroll_after = None
        for i, target in enumerate(targets):
            if not await page.query_selector(f"#{target}"):
                results[target] = "ausente"
                continue
            await page.evaluate(f"document.querySelector('#{target}').focus({{preventScroll: true}})")
            probe = await page.query_selector(".evidence-list li:last-child")
            # Espera una actualización real: el nodo de la lista queda reemplazado (innerHTML nuevo).
            try:
                await page.wait_for_function("(el) => !el.isConnected", arg=probe, timeout=TIMEOUT_MS)
            except Exception:
                print("  ✗ no hubo actualización en 12 s (¿el refresco acelerado no corrió?)")
                await browser.close()
                return 1
            # keepPlace reasigna scrollTop con el smooth del CSS: espera a que la animación asiente.
            await page.wait_for_timeout(700)
            state = await page.evaluate("""() => ({
              top: document.querySelector('#view').scrollTop,
              focus: document.activeElement && document.activeElement.id || document.activeElement?.tagName,
            })""")
            results[target] = state["focus"]
            if i == 0:
                scroll_after = state["top"]
        await browser.close()

    ok = True
    if scroll_after is None or abs(scroll_after - scroll_before) > 1:
        print(f"  ✗ scroll: era {scroll_before:.0f} y quedó {scroll_after}")
        ok = False
    else:
        print(f"  ✓ scroll conservado en {scroll_after:.0f} px tras la actualización")
    for target in targets:
        got = results[target]
        if got == "ausente":
            print(f"  – #{target} no existe en esta ficha (omitido)")
        elif got == target:
            print(f"  ✓ foco conservado en #{target}")
        else:
            print(f"  ✗ foco: estaba en #{target} y quedó en «{got}»")
            ok = False
    for e in page_errors:
        print("  ✗ JS:", e)
        ok = False
    print("OK: la ficha conserva la posición y el foco al refrescarse" if ok else "FALLÓ la prueba de FIX-05")
    return 0 if ok else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.url.rstrip("/"))))

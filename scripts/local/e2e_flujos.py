"""Suite e2e de los flujos principales de una persona (QA-E2E).

Corre contra el servidor de demostración, igual que scripts/local/browser_checks.py,
pero en vez de revisar errores, CSP y cortes por vista recorre los caminos de punta a
punta: fuego cerca, guardar/editar/borrar un lugar, compartir con la familia, reportar
humo y arrancar sin conexión.

  python scripts/local/seed_demo.py /tmp/demo-e2e
  BRASA_DATA_DIR=/tmp/demo-e2e BRASA_SCHEDULER=0 python -m uvicorn backend.main:app --port 8024
  python scripts/local/e2e_flujos.py --url http://127.0.0.1:8024
  python dev.py e2e --flujos

Cada flujo corre en su propio contexto 390×844 táctil con su propio suscriptor, que se
borra al final (DELETE /api/me); service_workers="block" salvo en el flujo 6, que
necesita el service worker activo. Las esperas son por estado del DOM
(wait_for_selector / wait_for_function); no hay wait_for_timeout. Imprime
«✓ <flujo>» o «✗ <flujo>: <motivo>» por flujo, guarda una captura por flujo en --out
(data/shots/flujos) y termina con código 1 si alguno falla.

Límites conocidos del servidor de demostración (en memoria, se limpian al reiniciar el
proceso): 20 suscriptores/hora y 6 reportes/hora por IP. Una corrida gasta 7
suscriptores (uno por flujo más el que la app registra sola en el contexto vecino del
flujo 4), así que tres corridas piden 21: entre corrida y corrida hay que reiniciar el
servidor para que no aparezca 429 — la base sembrada no se toca.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

from playwright.async_api import Browser, BrowserContext, Page, async_playwright

VIEWPORT = {"width": 390, "height": 844}
# Punto junto al incidente que siembra seed_demo.py en Quilpué.
QUILPUE = {"latitude": -33.075, "longitude": -71.405}
# Punto tranquilo, lejos de los incidentes de la demo: con un lugar en «urgente»
# Mi zona cambia a la vista de emergencia y la tarjeta deja de existir, así que los
# flujos de tarjeta (guardar, editar, compartir, sin conexión) usan este lugar.
QUIETO = {"latitude": -33.4372, "longitude": -70.6506}
ESPERA = 30_000

# %s recibe el token JSON-encoded: add_init_script no acepta argumentos en Python y
# solo evalúa el código, así que va como sentencias sueltas (una expresión de función
# queda definida sin llamarse).
INIT = """
localStorage.setItem('brasa:token', JSON.stringify(%s));
// Sáltese la propuesta de «probar un aviso» tras guardar el primer lugar.
localStorage.setItem('brasa:avisoProbado', JSON.stringify(true));
window.__toques = 0;
addEventListener('pointerdown', () => { window.__toques += 1; }, true);
"""


class FalloFlujo(Exception):
    """Una comprobación del flujo no pasó: el motivo va en el mensaje."""


def check(cond: object, motivo: str) -> None:
    if not cond:
        raise FalloFlujo(motivo)


def api(url: str, path: str, token: str | None = None, body: dict | None = None, method: str | None = None) -> dict:
    req = urllib.request.Request(
        url + path,
        data=json.dumps(body).encode() if body is not None else None,
        method=method or ("POST" if body is not None else "GET"),
        headers={"Content-Type": "application/json"},
    )
    if token:
        req.add_header("X-Brasa-Token", token)
    with urllib.request.urlopen(req, timeout=30) as res:
        return json.loads(res.read() or b"{}")


def suscriptor(url: str) -> str:
    return api(url, "/api/subscribers", body={})["token"]


def borrar_dispositivo(url: str, token: str) -> None:
    try:
        api(url, "/api/me", token=token, method="DELETE")
    except Exception:
        pass  # la limpieza no debe tapar el motivo real del fallo


def guardar_lugar(url: str, token: str, nombre: str = "Parcela e2e", **extra) -> str:
    cuerpo = {"name": nombre, "kind": "casa", "lat": QUIETO["latitude"], "lon": QUIETO["longitude"], "radius_km": 10}
    cuerpo.update(extra)
    return api(url, "/api/places", token=token, body=cuerpo)["id"]


async def contexto(browser: Browser, token: str | None, punto: dict = QUILPUE) -> BrowserContext:
    ctx = await browser.new_context(
        viewport=VIEWPORT,
        has_touch=True,
        service_workers="block",
        geolocation=punto,
        permissions=["geolocation"],
    )
    if token:
        await ctx.add_init_script(INIT % json.dumps(token))
    return ctx


async def captura(page: Page, ruta: Path) -> None:
    """Una captura por flujo: si el flujo ya guardó la suya, no la pisa."""
    if ruta.exists():
        return
    try:
        await page.screenshot(path=str(ruta))
    except Exception:
        pass


async def tocar_accion(page: Page, act: str) -> bool:
    """Abre «Más acciones» y toca el botón en la misma llamada: un repintado de la
    tarjeta no puede cerrar el <details> a mitad del toque."""
    return await page.evaluate(
        """(act) => {
            for (const d of document.querySelectorAll('.place-card details')) d.open = true;
            const b = document.querySelector(`.place-card [data-act="${act}"]`);
            if (!b) return false;
            b.click();
            return true;
        }""",
        act,
    )


async def flujo_fuego_cerca(browser: Browser, url: str, out: Path) -> None:
    """1 · Primera visita → «¿Hay fuego cerca de mí?»: ≤ 3 toques hasta la respuesta."""
    token = suscriptor(url)
    ctx = await contexto(browser, token)
    page = await ctx.new_page()
    try:
        await page.goto(f"{url}/#/mi-zona")
        await page.wait_for_selector("#cerca-btn", timeout=ESPERA)
        await page.click("#cerca-btn")
        await page.wait_for_selector("#modal #cerca-lista, #modal #cerca-vacia", timeout=ESPERA)
        texto = await page.inner_text("#modal")
        check(await page.locator("#modal #cerca-lista li").count() > 0, "la lista salió vacía junto al incidente de la demo")
        check("Ver en el mapa" in texto, "la respuesta no trae «Ver en el mapa»")
        check(any(p in texto.lower() for p in ("incendio", "calor", "conaf")), "la respuesta no nombra el incendio ni el calor cercano")
        toques = await page.evaluate("() => window.__toques")
        check(toques <= 3, f"tomó {toques} toques (máximo 3)")
    finally:
        await captura(page, out / "1-fuego-cerca.png")
        borrar_dispositivo(url, token)
        await ctx.close()


async def flujo_guardar_lugar(browser: Browser, url: str, out: Path) -> None:
    """2 · Guardar un lugar con «Estoy aquí ahora» y la casilla de aluvión marcada."""
    token = suscriptor(url)
    ctx = await contexto(browser, token, QUIETO)
    page = await ctx.new_page()
    try:
        await page.goto(f"{url}/#/mi-zona")
        await page.wait_for_selector("#add-place", timeout=ESPERA)
        await page.click("#add-place")
        await page.wait_for_selector("#place-form", timeout=ESPERA)
        check(await page.is_checked("#pf-aluvion"), "la casilla de aluvión viene desmarcada")
        await page.fill("#pf-name", "Parcela e2e")
        await page.click("#pf-gps")
        await page.wait_for_function(
            "() => document.querySelector('#pf-point')?.innerText.includes('Ubicación lista')", timeout=ESPERA
        )
        await page.click("#place-form button[type=submit]")
        await page.wait_for_selector(".place-card", timeout=ESPERA)
        check("Parcela e2e" in await page.inner_text(".place-card .card-title"), "la tarjeta no trae el nombre del lugar")
        check((await page.inner_text(".place-card .status-badge")).strip() != "", "la tarjeta no muestra su estado")
        lugares = api(url, "/api/places", token=token)["places"]
        check(any(l["name"] == "Parcela e2e" for l in lugares), "GET /api/places no devuelve el lugar guardado")
    finally:
        await captura(page, out / "2-guardar-lugar.png")
        borrar_dispositivo(url, token)
        await ctx.close()


async def flujo_editar_borrar(browser: Browser, url: str, out: Path) -> None:
    """3 · Editar el nombre y la casilla de humo, después borrar con confirmación."""
    token = suscriptor(url)
    guardar_lugar(url, token, smoke_alerts=True)
    ctx = await contexto(browser, token, QUIETO)
    page = await ctx.new_page()
    try:
        await page.goto(f"{url}/#/mi-zona")
        await page.wait_for_selector(".place-card", timeout=ESPERA)
        check(await tocar_accion(page, "editar"), "no aparece el botón Editar")
        await page.wait_for_selector("#place-form", timeout=ESPERA)
        await page.fill("#pf-name", "Parcela e2e sur")
        check(await page.is_checked("#pf-smoke"), "la casilla de humo no venía marcada")
        await page.uncheck("#pf-smoke")
        await page.click("#place-form button[type=submit]")
        await page.wait_for_function(
            "() => document.querySelector('.place-card .card-title')?.innerText.includes('Parcela e2e sur')",
            timeout=ESPERA,
        )
        lugares = api(url, "/api/places", token=token)["places"]
        check(len(lugares) == 1 and lugares[0]["name"] == "Parcela e2e sur", "la API no refleja el nombre nuevo")
        check(lugares[0]["smoke_alerts"] is False, "la API no refleja la casilla de humo desmarcada")
        check(await tocar_accion(page, "borrar"), "no aparece el botón Eliminar")
        await page.wait_for_selector("#confirm-del", timeout=ESPERA)
        await page.click("#confirm-del")
        await page.wait_for_function("() => !document.querySelector('.place-card')", timeout=ESPERA)
        check(api(url, "/api/places", token=token)["places"] == [], "la API aún lista el lugar borrado")
    finally:
        await captura(page, out / "3-editar-borrar.png")
        borrar_dispositivo(url, token)
        await ctx.close()


async def flujo_compartir(browser: Browser, url: str, out: Path) -> None:
    """4 · Enlace para la familia: otro contexto, sin token, ve el lugar de solo lectura."""
    token = suscriptor(url)
    guardar_lugar(url, token)
    ctx = await contexto(browser, token, QUIETO)
    page = await ctx.new_page()
    pagina_compartida = None
    try:
        await page.goto(f"{url}/#/mi-zona")
        await page.wait_for_selector(".place-card", timeout=ESPERA)
        await page.click('[data-act="compartir"]')
        await page.wait_for_selector("#share-url", timeout=ESPERA)
        enlace = await page.input_value("#share-url")
        check("/#/v/" in enlace, f"enlace inesperado: {enlace}")
        vecino = await browser.new_context(viewport=VIEWPORT, has_touch=True, service_workers="block")
        pagina_compartida = await vecino.new_page()
        try:
            await pagina_compartida.goto(enlace)
            await pagina_compartida.wait_for_selector(".place-card", timeout=ESPERA)
            # El nombre va en el héroe de la vista compartida, sobre la tarjeta.
            check("Parcela e2e" in await pagina_compartida.inner_text("#view"), "el lugar no aparece en la vista compartida")
            edicion = await pagina_compartida.evaluate(
                "() => document.querySelectorAll('[data-act=\"editar\"], [data-act=\"borrar\"]').length"
            )
            check(edicion == 0, "la vista compartida muestra botones de edición")
            await captura(pagina_compartida, out / "4-compartir.png")
        finally:
            # La app registra un dispositivo propio en el contexto vecino (deviceToken):
            # también se borra, como hace check_zona_contexto con el suyo.
            try:
                token_vecino = await pagina_compartida.evaluate("() => JSON.parse(localStorage.getItem('brasa:token') || 'null')")
            except Exception:
                token_vecino = None
            if token_vecino:
                borrar_dispositivo(url, token_vecino)
            await vecino.close()
    finally:
        await captura(pagina_compartida or page, out / "4-compartir.png")
        borrar_dispositivo(url, token)
        await ctx.close()


async def flujo_reportar(browser: Browser, url: str, out: Path, corrida: int) -> None:
    """5 · Reportar humo sin foto: queda «no_verificado» y fuera de /api/reports público."""
    token = suscriptor(url)
    # Los reportes del mismo tipo a ≤ 1,5 km y ≤ 3 h se fusionan como duplicado en el
    # servidor (DUPLICATE_KM/DUPLICATE_HOURS) y los pendientes sobreviven en la base
    # sembrada: cada corrida mueve el punto ~4 km para crear el suyo. Repetir una
    # corrida dentro de 3 h necesita otro --corrida o la base resembrada.
    punto = {"latitude": QUILPUE["latitude"] + 0.03 * (corrida - 1), "longitude": QUILPUE["longitude"] + 0.03 * (corrida - 1)}
    ctx = await contexto(browser, token, punto)
    page = await ctx.new_page()
    try:
        await page.goto(f"{url}/#/mapa")
        await page.wait_for_selector("#report", timeout=ESPERA)
        await page.click("#report")
        await page.wait_for_selector("#report-form", timeout=ESPERA)
        await page.click('#rf-kind [data-kind="humo"]')
        await page.click("#rf-gps")
        await page.wait_for_function(
            "() => document.querySelector('#rf-point')?.innerText.includes('Ubicación lista')", timeout=ESPERA
        )
        desc = f"Humo e2e {int(time.time())}: columna tras el cerro, sin llamas visibles."
        await page.fill("#rf-desc", desc)
        await page.click("#report-form button[type=submit]")
        await page.wait_for_function(
            "() => document.querySelector('#modal-title')?.innerText.includes('Reporte recibido')", timeout=ESPERA
        )
        propios = [r for r in api(url, "/api/reports/mine", token=token)["reports"] if r["description"] == desc]
        check(propios, "GET /api/reports/mine no devuelve el reporte enviado")
        check(propios[0]["status"] == "no_verificado", f"el reporte quedó «{propios[0]['status']}», no pendiente")
        publicos = api(url, "/api/reports")["reports"]
        check(all(r["id"] != propios[0]["id"] for r in publicos), "el reporte ya sale en /api/reports sin moderar")
    finally:
        await captura(page, out / "5-reportar.png")
        borrar_dispositivo(url, token)
        await ctx.close()


async def flujo_sin_conexion(browser: Browser, url: str, out: Path) -> None:
    """6 · Sin conexión: con el service worker activo, Mi zona, /focos.html y
    /web/lite.html abren con los datos guardados."""
    token = suscriptor(url)
    guardar_lugar(url, token)
    # Este flujo no bloquea el service worker: es el protagonista de la prueba.
    ctx = await browser.new_context(viewport=VIEWPORT, has_touch=True, geolocation=QUIETO, permissions=["geolocation"])
    await ctx.add_init_script(INIT % json.dumps(token))
    page = await ctx.new_page()
    try:
        await page.goto(f"{url}/")
        await page.wait_for_function(
            """async () => {
                if (!('serviceWorker' in navigator)) return false;
                const reg = await navigator.serviceWorker.ready;
                return reg?.active?.state === 'activated' && !!navigator.serviceWorker.controller;
            }""",
            timeout=ESPERA * 2,
        )
        # Calienta la caché del service worker: sin conexión solo responde lo ya guardado.
        await page.goto(f"{url}/#/mi-zona")
        await page.wait_for_selector(".place-card", timeout=ESPERA)
        await page.goto(f"{url}/focos.html")
        await page.wait_for_selector(
            "#focos-tabla-wrap:not([hidden]), #focos-vacio:not([hidden]), #focos-error:not([hidden])", timeout=ESPERA
        )
        await page.goto(f"{url}/web/lite.html")
        await page.wait_for_selector("#lite-places .card", timeout=ESPERA)

        await ctx.set_offline(True)
        await page.goto(f"{url}/#/mi-zona")
        await page.wait_for_selector(".place-card", timeout=ESPERA)
        check("Parcela e2e" in await page.inner_text(".place-card"), "Mi zona no pinta el lugar guardado sin conexión")
        fallido = await page.evaluate(
            "() => { const el = document.querySelector('#arranque-fallido'); return !!el && !el.hidden; }"
        )
        check(not fallido, "apareció la pantalla de arranque fallido")
        await captura(page, out / "6-sin-conexion.png")
        await page.goto(f"{url}/focos.html")
        await page.wait_for_selector(
            "#focos-tabla-wrap:not([hidden]), #focos-vacio:not([hidden])", timeout=ESPERA
        )
        await page.goto(f"{url}/web/lite.html")
        await page.wait_for_selector("#lite-places .card", timeout=ESPERA)
    finally:
        await captura(page, out / "6-sin-conexion.png")
        borrar_dispositivo(url, token)
        await ctx.close()


FLUJOS = [
    ("1 · fuego cerca", flujo_fuego_cerca),
    ("2 · guardar un lugar", flujo_guardar_lugar),
    ("3 · editar y borrar", flujo_editar_borrar),
    ("4 · compartir con la familia", flujo_compartir),
    ("5 · reportar humo", flujo_reportar),
    ("6 · sin conexión", flujo_sin_conexion),
]


async def main_async(url: str, out: Path, corrida: int) -> int:
    out.mkdir(parents=True, exist_ok=True)
    for vieja in out.glob("*.png"):
        vieja.unlink()  # una captura de otra corrida no debe pasar por evidencia de esta
    async with async_playwright() as pw:
        chromium = os.environ.get("BRASA_CHROMIUM")
        browser = await pw.chromium.launch(**({"executable_path": chromium} if chromium else {}))
        try:
            fallos = 0
            for nombre, fn in FLUJOS:
                try:
                    if fn is flujo_reportar:
                        await fn(browser, url, out, corrida)
                    else:
                        await fn(browser, url, out)
                    print(f"✓ {nombre}", flush=True)
                except Exception as e:
                    print(f"✗ {nombre}: {' '.join(str(e).splitlines()[:2])}", flush=True)
                    fallos += 1
        finally:
            await browser.close()
    return 1 if fallos else 0


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--url", default="http://127.0.0.1:8024", help="base del servidor de demostración")
    p.add_argument("--out", type=Path, default=Path("data/shots/flujos"), help="directorio de capturas")
    p.add_argument("--corrida", type=int, default=1, help="número de corrida ≥ 1: mueve el reporte del flujo 5 para no chocar con los pendientes")
    args = p.parse_args()
    sys.exit(asyncio.run(main_async(args.url.rstrip("/"), args.out, max(1, args.corrida))))


if __name__ == "__main__":
    main()

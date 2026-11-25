"""Verifica en navegador real que la app siga usable mientras /api/config llega tarde (REND-02 PR2).

El orquestador del CI ya levantó el servidor efímero con el retraso pedido
(``BRASA_BENCH_CONFIG_DELAY_MS`` en perf_server.py); este script NO arranca nada.
Entra frío con Playwright contra el despliegue servido, en DOS contextos independientes
(IP sintética distinta cada uno, sin caché ni datos previos):

- contexto A, interacciones con la config garantizada pendiente: la ventana de «config
  pendiente» se garantiza reteniendo ``/api/config`` en el navegador (el manejador de
  ruta guarda la petición y vuelve, sin bloquear Python; se libera al final y recién
  entonces actúa el retraso del servidor). La portada responde, el modal de lugar abre
  y cierra con sus callbacks vivos, el mapa navega, el formulario de reporte se usa y
  se cierra ANTES de la llegada (nada de widgets huérfanos) y el modal de canales de
  alerta queda abierto con su foco para comprobar que la llegada repinta solo la
  tarjeta de Telegram sin robar foco ni estado. Comprobación funcional, NO medición
  de latencia: para eso está medir_rendimiento.py;
- contexto B, conservación a través de la llegada: el modal de lugar queda abierto con
  un chip, un select y un texto con su foco puestos antes de liberar la config; la
  llegada tardía no puede borrarlos ni robar el foco. Después: mapa completo, apertura
  repetida del reporte (a lo más una promesa de script y un widget por apertura,
  siempre montado sobre un modal vivo) y un ciclo de lugar tras una transición SPA.

Turnstile es un proveedor externo: aquí es un mock efímero (el script de mentira se
sirve por ruta y todo lo demás de ese origen se aborta). Sin PII, sin red real ni
escrituras reales. El orquestador publica la clave de sitio de prueba de Cloudflare
(``BRASA_BENCH_TURNSTILE_SITE_KEY``, sin secreto), así que el widget se monta de verdad
sobre el mock: cero huérfanos, a lo más un render por apertura.

Envíos: el script no envía nada propio. La app da de alta el dispositivo nada más
arrancar (``POST /api/subscribers`` automático en el primer auth): esa alta anónima se
permite y se registra —es el arranque normal en un fixture efímero, con IP sintética
y sin datos reales—. Todo otro envío o mutación al mismo origen (reportes, push,
lugares, avisos) queda prohibido y falla la corrida. Nunca se envía un reporte (el
texto de «Columna de humo bench» jamás sale del navegador). Solo corre contra
``http://127.0.0.1:8002``: producción queda fuera por diseño. La IP sintética por
contexto (cabecera X-Forwarded-For) solo la acepta perf_server, que confía en
127.0.0.1 (``forwarded_allow_ips``).

Nota de entrada de UI: el botón que abre los canales (``#diag-canales``) solo existe
con lugares guardados; el fixture no los tiene (crearlos exige un POST prohibido), así
que el modal se abre invocando ``alertChannels()`` por su export público: se ejercita
el código real del modal, sin inyectar datos.

Uso (lo llama scripts/local/ejecutar_rendimiento_ci.py con --verificar-config):

    python scripts/local/config_check.py --url http://127.0.0.1:8002 --out DIR \
        --device movil --retraso-config-ms 3000 [--exigir-no-bloqueante]

Salida: ``DIR/config.json`` (todo lo medido), ``DIR/config.md`` (informe legible) y
capturas en ``DIR/capturas/``. Código de salida: 0 si cumple, 1 si no, 2 si el uso
es inválido. Los contratos de ventana pendiente se miden y reportan siempre, pero
solo fallan la corrida con --exigir-no-bloqueante (el orquestador del CI lo pasa).
"""
from __future__ import annotations

import argparse
import itertools
import json
import sys
import time
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

RUTA_SCRIPT = Path(__file__).resolve()
sys.path.insert(0, str(RUTA_SCRIPT.parent))
import medir_rendimiento as mr  # noqa: E402  (mismo harness: bloqueos externos, clasificación, dispositivos)

# Este harness es exclusivamente loopback contra el servidor efímero del CI.
HOST_PERMITIDO = "127.0.0.1"
PUERTO_PERMITIDO = 8002
MAX_RETRASO_MS = 10000
_CLIENTES = itertools.count(1)

# Alta anónima del dispositivo (api.js deviceToken): automática en el primer auth de un
# arranque frío. Se permite (fixture efímero, IP sintética, sin datos reales) y se registra;
# cualquier otro envío o mutación al mismo origen está prohibido.
POST_PERMITIDO = "/api/subscribers"
METODOS_SEGUROS = ("GET", "HEAD")

# Proveedor externo del antibot: mock efímero, sin PII, sin red ni escrituras reales.
TURNSTILE_ORIGEN = "challenges.cloudflare.com"
TURNSTILE_SCRIPT_URL = f"https://{TURNSTILE_ORIGEN}/turnstile/v0/api.js"
MOCKS_EXTERNOS = (TURNSTILE_ORIGEN,)

# Registra cada render con su estado de conexión (detector de widgets huérfanos) y no
# hace nada más: ni red, ni escrituras, ni token de verdad (el reporte nunca se envía).
TURNSTILE_MOCK_JS = """// Mock efímero de Cloudflare Turnstile para config_check (REND-02): sin PII, sin red,
// sin escrituras. window.turnstile no existe hasta que este script carga, como el real.
(() => {
  if (window.__benchTurnstile) return;
  const registro = { renders: [], ejecuciones: 0, removidos: 0 };
  window.__benchTurnstile = registro;
  window.turnstile = {
    render(host, opts) {
      const id = 'bench-ts-' + (registro.renders.length + 1);
      registro.renders.push({ id, conectado: Boolean(host && host.isConnected), sitekey: opts ? opts.sitekey : null });
      return id;
    },
    execute() { registro.ejecuciones += 1; },
    remove() { registro.removidos += 1; },
    reset() {},
  };
})();
"""

# Contratos duros: valen siempre. Los de ventana pendiente son el objetivo de REND-02 PR2
# y solo se exigen con --exigir-no-bloqueante, que el orquestador pasa con retraso > 0.
CONTRATOS_DUROS = (
    "configRespondio", "portadaUtilizable", "modalCiclosSanos", "modalCiclosTransicion",
    "focoConservadoTrasConfig", "valoresConservadosTrasConfig", "mapaUtilizable",
    "reporteUtilizableSinConfig", "reporteSinWidgetHuerfano", "reporteUnaAperturaUnWidget",
    "canalesFocoConservadoTrasConfig", "canalesRepintadoTrasConfig",
    "sinErroresProducto", "sinCspViolaciones", "sinEnviosNiMutaciones",
)
CONTRATOS_PENDIENTES = ("portadaAntesDeConfig", "modalDurantePendiente", "mapaDurantePendiente")

# Casos límite que este humo todavía no cubre: quedan en el informe para añadirles
# pruebas (helper JS, permisos del contexto o suite DOM) cuando toque.
PENDIENTES_FIJOS = (
    "«Estoy aquí ahora» (geolocalización sintética) con config pendiente: falta otorgar el permiso del contexto.",
    "Elección de comuna en «pf-comuna» con pickOnMap: cubre el flujo completo del motor del mapa.",
    "Selección de región del catálogo («chips-region»): fuera de este humo para no navegar el catálogo masivamente.",
    "vaciarOutbox/flushOutbox (ui.js) ya cumple el contrato aprobado (flushPromise compartido, una sola espera "
    "fresca para toda la cola, 403/429 dejan la cola intacta), pero no tiene suite en node: ui.js importa map.js "
    "(Cesium) y toca window al cargarse. Este humo solo ejercita su camino inerte (cola vacía y sin clave "
    "publicada): la cola real exigiría guardar un reporte sin señal y su POST a /api/reports está prohibido aquí.",
    "Sin el orquestador (BRASA_BENCH_TURNSTILE_SITE_KEY vacío) no hay clave publicada: el widget no se monta y "
    "los invariantes de Turnstile quedan inertes.",
    "Suite DOM en node del modal de reporte/canales (ui.test.mjs): ui.js no exporta sus funciones y toca window "
    "al cargarse; el humo de navegador cubre el recorrido funcional por ahora.",
)


def url_permitida(url: str) -> bool:
    """¿Es el servidor efímero del CI? Solo loopback en el puerto de la candidata, nunca producción."""
    partes = urlparse(url)
    return partes.scheme == "http" and partes.hostname == HOST_PERMITIDO and partes.port == PUERTO_PERMITIDO


def cabeceras_cliente() -> dict:
    """IP sintética por contexto: perf_server confía solo en 127.0.0.1 (forwarded_allow_ips)."""
    numero = next(_CLIENTES)
    return {"X-Forwarded-For": f"127.1.{numero // 256}.{numero % 256}"}


def clasificar_post(url: str, base: str) -> str:
    """Un envío al propio servidor: solo la alta anónima del dispositivo es normal."""
    if not mr.mismo_origen(url, base):
        return "externo"
    return "permitido" if urlparse(url).path == POST_PERMITIDO else "prohibido"


def parsear_args(argv):
    parser = argparse.ArgumentParser(prog="config_check.py", description=__doc__.splitlines()[0])
    parser.add_argument("--url", required=True,
                        help=f"servidor efímero ya levantado (solo http://{HOST_PERMITIDO}:{PUERTO_PERMITIDO})")
    parser.add_argument("--out", type=Path, required=True,
                        help="carpeta del informe (config.json, config.md, capturas/)")
    parser.add_argument("--device", required=True, help="movil|escritorio (alias mobile|desktop)")
    parser.add_argument("--retraso-config-ms", type=int, default=0,
                        help="retraso con el que el servidor tarda /api/config (lo puso el orquestador)")
    parser.add_argument("--timeout-s", type=float, default=45.0, help="segundos por paso")
    parser.add_argument("--exigir-no-bloqueante", action="store_true",
                        help="exige los contratos de ventana pendiente (front de REND-02 PR2 ya entregado)")
    args = parser.parse_args(argv)
    if not url_permitida(args.url):
        parser.error(f"--url debe ser http://{HOST_PERMITIDO}:{PUERTO_PERMITIDO} "
                     "(servidor efímero del CI; nunca producción)")
    if not 0 <= args.retraso_config_ms <= MAX_RETRASO_MS:
        parser.error(f"--retraso-config-ms debe estar entre 0 y {MAX_RETRASO_MS}")
    if args.timeout_s <= 0:
        parser.error("--timeout-s debe ser positivo")
    if args.exigir_no_bloqueante and args.retraso_config_ms == 0:
        parser.error("--exigir-no-bloqueante necesita --retraso-config-ms > 0: sin retraso no hay ventana pendiente")
    dispositivo = mr.ALIAS_DISPOSITIVO.get(args.device, args.device)
    if dispositivo not in mr.DISPOSITIVOS:
        parser.error(f"--device debe ser movil o escritorio; recibido: {args.device}")
    args.dispositivo = dispositivo
    return args


def contratos_incumplidos(contratos: dict, exigir: bool) -> list:
    """Duros siempre; los de ventana pendiente solo si se exigen. None nunca pasa por omisión."""
    mal = [clave for clave in CONTRATOS_DUROS if contratos.get(clave) is not True]
    if exigir:
        mal += [clave for clave in CONTRATOS_PENDIENTES if contratos.get(clave) is not True]
    return mal


class RetencionConfig:
    """Retiene /api/config en el navegador sin bloquear Python (REND-02).

    El manejador de ruta guarda la petición y vuelve: la página queda esperando y el
    script sigue interactuando con normalidad. liberar() la deja pasar y recién
    entonces actúa el retraso del servidor. Con esto la «ventana de config pendiente»
    está garantizada por construcción: la verificación no depende de que las acciones
    iniciales duren menos que el retraso. Es una comprobación funcional del arranque
    no bloqueante: NO mide latencia (medir_rendimiento.py la mide con el retraso real
    del servidor y sin retener nada).

    Límite duro: api.js corta la petición a los 12 s (AbortSignal.timeout) y ese TIMEOUT
    se reintenta con pausa creciente (api.js reintenta TIMEOUT igual que los 503): la
    retención total de un contexto debe quedar muy por debajo del tope, para que la
    respuesta de la config retenida llegue dentro de su propia petición. Los timeout_ms
    de las esperas son límites de fallo, no esperas fijas: en un arranque sano cada
    elemento aparece en milisegundos.
    """

    def __init__(self):
        self.retener = True
        self.retenidas = []
        self.capturadas = 0

    def instalar(self, contexto):
        contexto.route("**/api/config", self._manejador)

    def _manejador(self, ruta):
        if not self.retener:
            ruta.continue_()
            return
        self.retenidas.append(ruta)
        self.capturadas += 1
        # Sin continue_ la petición queda pendiente: el evento de ruta ya devolvió el
        # control a Python y el navegador sigue respondiendo a las interacciones.

    def liberar(self):
        self.retener = False
        while self.retenidas:
            ruta = self.retenidas.pop()
            try:
                ruta.continue_()
            except Exception:
                pass  # la propia página pudo cancelarla (tope de 12 s de api.js): se reporta aparte


def instalar_mock_turnstile(contexto) -> dict:
    """Mock efímero del proveedor antibot: sirve el script de mentira (sin PII, sin red
    ni escrituras reales) y aborta todo lo demás de ese origen. Devuelve su contador."""
    contador = {"script": 0}

    def manejador(ruta):
        if ruta.request.url == TURNSTILE_SCRIPT_URL and ruta.request.resource_type == "script":
            contador["script"] += 1
            ruta.fulfill(status=200, content_type="application/javascript", body=TURNSTILE_MOCK_JS)
            return
        ruta.abort()  # iframes y demás del proveedor: nada sale del navegador

    contexto.route(f"https://{TURNSTILE_ORIGEN}/**", manejador)
    return contador


class Bitacora:
    """Errores JS, consola, HTTP y red clasificados como en medir_rendimiento: nada se omite."""

    def __init__(self, base: str):
        self.base = base
        self.t0 = None
        self.config_ms = None
        self.errores = []
        self.posts = {"permitidos": [], "prohibidos": []}

    def arrancar(self):
        self.t0 = time.monotonic()

    def ms(self):
        return round((time.monotonic() - self.t0) * 1000, 1) if self.t0 else None

    def error(self, clase: str, **campos):
        self.errores.append({"clase": clase, **campos})

    def enganchar(self, ctx, page):
        ctx.on("request", self._al_pedir)
        page.on("response", self._al_responder)
        page.on("requestfailed", self._al_fallar)
        page.on("pageerror", self._al_error_js)
        page.on("console", self._a_la_consola)

    def _al_pedir(self, pedido):
        if pedido.method in METODOS_SEGUROS:
            return
        if not mr.mismo_origen(pedido.url, self.base):
            return  # lo externo ya lo bloquea el harness: se clasifica en _al_fallar
        self.posts[clasificar_post(pedido.url, self.base)].append(f"{pedido.method} {pedido.url}")

    def _al_responder(self, respuesta):
        if urlparse(respuesta.url).path == "/api/config" and respuesta.status < 400:
            if self.config_ms is None:
                self.config_ms = self.ms()
        if respuesta.status >= 400 and mr.mismo_origen(respuesta.url, self.base):
            self.error(mr.clasificar_url(respuesta.url, self.base), tipo="http",
                       estado=respuesta.status, url=respuesta.url)

    def _al_fallar(self, pedido):
        url, texto = pedido.url, pedido.failure or ""
        host = (urlparse(url).hostname or "").lower()
        es_mock = any(host == origen or host.endswith("." + origen) for origen in MOCKS_EXTERNOS)
        if mr.es_externa(url) or es_mock:
            self.error("bloqueado", tipo="red", url=url, texto=texto)  # el harness las aborta: esperado
        elif not mr.mismo_origen(url, self.base):
            self.error("externo", tipo="red", url=url, texto=texto)
        else:
            # ERR_ABORTED: la propia app canceló el pedido (navegación o su tope de tiempo):
            # ruido del medidor, no fallo del producto. Va al informe igual, nada se omite.
            self.error("medidor" if "ERR_ABORTED" in texto else "producto", tipo="red", url=url, texto=texto)

    def _al_error_js(self, excepcion):
        texto = str(excepcion)
        if "content security policy" in texto.lower():
            self.error("producto", tipo="csp", texto=texto[:400])  # una violación de CSP siempre es del producto
        else:
            self.error(mr.clase_texto(texto), tipo="js", texto=texto[:400])

    def _a_la_consola(self, mensaje):
        try:
            if mensaje.type != "error":
                return
            texto = mensaje.text or ""
        except Exception:
            return
        if "content security policy" in texto.lower():
            self.error("producto", tipo="csp", texto=texto[:400])  # una violación de CSP siempre es del producto
            return
        # «Failed to load resource: net::ERR_FAILED» no trae la URL en el texto: sin ella,
        # las teselas que este PROPIO harness aborta se clasificaban «producto» (texto sin
        # origen) y tiraban el gate sinErroresProducto del primer CI con retraso 3000. La
        # clasificación precisa usa la ubicación del mensaje (la URL del recurso que
        # falló): lo que el harness bloquea —externas abortadas o el mock del proveedor—
        # es «bloqueado», igual que en requestfailed; todo lo demás conserva la
        # clasificación por texto. Nada se omite del informe.
        try:
            url = mensaje.location.url if mensaje.location else ""
        except Exception:
            url = ""
        if url:
            host = (urlparse(url).hostname or "").lower()
            es_mock = any(host == origen or host.endswith("." + origen) for origen in MOCKS_EXTERNOS)
            if mr.es_externa(url) or es_mock:
                self.error("bloqueado", tipo="consola", url=url, texto=texto[:400])
                return
        self.error(mr.clase_texto(texto), tipo="consola", texto=texto[:400])


def ciclo_modal(page, timeout_ms, numero) -> dict:
    """Abre «Agregar mi casa», ejercita sus callbacks y lo cierra: detecta callbacks DOM muerto."""
    detalle = {"numero": numero}
    page.click("#add-place", timeout=timeout_ms)
    page.wait_for_selector("#modal[open] #place-form", state="visible", timeout=timeout_ms)
    # El clic en un chip cambia la marca y el nombre por defecto: el callback sigue vivo.
    page.click('#pf-kind .chip[data-kind="parcela"]', timeout=timeout_ms)
    detalle["nombrePorChip"] = page.input_value("#pf-name")
    page.fill("#pf-name", f"Casa bench {numero}")
    detalle["nombreEscrito"] = page.input_value("#pf-name")
    page.click("#modal-body [data-cancel]", timeout=timeout_ms)
    page.wait_for_function("!document.getElementById('modal').open", timeout=timeout_ms)
    detalle["cerro"] = True
    return detalle


def esperar_config(bitacora: Bitacora, page, segundos_max: float) -> bool:
    """Espera (sin crear tráfico) a que la configuración tardía llegue."""
    fin = time.monotonic() + segundos_max
    while bitacora.config_ms is None:
        if time.monotonic() >= fin:
            return False
        page.wait_for_timeout(50)
    return True


def esperar_visible(page, selector, timeout_ms, reintentos=None):
    """Espera un elemento visible con un presupuesto total, reintentando fallos instantáneos.

    Fallo real del primer CI con retraso 3000: en el arranque frío el service worker de la
    app instala rápido (el SHELL va por loopback) y su ``clients.claim()`` toma el control
    de la página apenas unos ms después de DCL; esa toma de control invalida el contexto de
    ejecución del documento y un ``wait_for_selector`` puntual muere al instante
    («Execution context was destroyed») en vez de esperar su plazo. Con la espera de la
    portada ese fallo se tragaba como False: portadaUtilizable en falso con portadaMs
    137,7 (la espera murió antes de empezar) mientras la portada misma pintaba y quedaba
    usable (el mismo botón respondió en el contexto B y medir_rendimiento midió la portada
    en ~0,5 s con el mismo retraso; allí no pasa porque su espera tras goto reintenta
    ``page.evaluate`` cada 100 ms).

    El reintento vive dentro del MISMO presupuesto: ni un ms más de plazo ni gates más
    blandas (mismo selector, mismo ``state="visible"``). Un fallo instantáneo reintenta
    con el plazo restante; un timeout real agota el presupuesto y devuelve False. Si
    ``reintentos`` es un dict, acumula el total de reintentos y el último error: queda en
    el informe, nada se oculta.
    """
    fin = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < fin:
        restante_ms = max(1, int((fin - time.monotonic()) * 1000))
        try:
            page.wait_for_selector(selector, state="visible", timeout=restante_ms)
            return True
        except Exception as fallo:
            if time.monotonic() + 0.05 >= fin:
                return False  # el presupuesto se agotó esperando: timeout real, sin reintentos ni plazo extra
            if reintentos is not None:
                reintentos["total"] = reintentos.get("total", 0) + 1
                reintentos["ultimo"] = f"{type(fallo).__name__}: {fallo}"[:200]
            time.sleep(0.05)  # fallo instantáneo (contexto invalidado al arrancar): no girar en vacío
    return False


def renders_turnstile(page) -> list:
    """Los renders que registró el mock del proveedor antibot (vacío si nunca cargó)."""
    try:
        return page.evaluate(
            "() => (window.__benchTurnstile ? window.__benchTurnstile.renders : [])") or []
    except Exception:
        return []


def correr(args, browser) -> dict:
    """Dos contextos fríos por corrida: interacciones pendientes y conservación tras la llegada."""
    paso_ms = int(args.timeout_s * 1000)
    retenido_ms = min(paso_ms, 3000)  # bajo retención, lejos del tope de 12 s de api.js
    contratos = {clave: None for clave in CONTRATOS_DUROS + CONTRATOS_PENDIENTES}
    eventos, ciclos, capturas = {}, [], []
    args.out.mkdir(parents=True, exist_ok=True)
    carpeta = args.out / "capturas"
    carpeta.mkdir(parents=True, exist_ok=True)

    def captura(nombre, page):
        try:
            page.screenshot(path=str(carpeta / f"{nombre}.png"))
            capturas.append(f"capturas/{nombre}.png")
        except Exception:
            pass  # la captura es apoyo del informe, no un contrato

    reintentos_espera = {"total": 0, "ultimo": None}

    def esperar(page, selector, timeout_ms=None):
        # La espera de la portada es la primera tras goto: es la que se cruza con la toma
        # de control del service worker de la app (ver esperar_visible). Mismo presupuesto,
        # mismos gates; solo sobrevive el fallo instantáneo del contexto.
        return esperar_visible(page, selector, timeout_ms or paso_ms, reintentos_espera)

    def nuevo_contexto():
        disp = mr.DISPOSITIVOS[args.dispositivo]
        contexto = browser.new_context(
            viewport={"width": disp["ancho"], "height": disp["alto"]}, has_touch=disp["tactil"],
            is_mobile=disp["esMovil"], device_scale_factor=disp["escala"], locale="es-CL",
            timezone_id="America/Santiago", service_workers="allow",
            extra_http_headers=cabeceras_cliente())
        for host in mr.ORIGENES_EXTERNOS:
            contexto.route(f"https://{host}/**", lambda ruta: ruta.abort())
        contador_turnstile = instalar_mock_turnstile(contexto)
        retencion = RetencionConfig()
        retencion.instalar(contexto)  # la petición de arranque queda retenida antes del goto
        page = contexto.new_page()
        bitacora = Bitacora(args.url)
        bitacora.enganchar(contexto, page)
        return contexto, page, bitacora, retencion, contador_turnstile

    # ------------------------------------------------ contexto A: config garantizada pendiente
    ctx_a, page_a, bitacora_a, retencion_a, ts_a = nuevo_contexto()
    bitacora_a.arrancar()
    try:
        try:
            page_a.goto(args.url, wait_until="domcontentloaded", timeout=paso_ms)
            contratos["portadaUtilizable"] = esperar(page_a, "#add-place", retenido_ms)
        except Exception:
            contratos["portadaUtilizable"] = False
        eventos["portadaMs"] = bitacora_a.ms()
        captura("portada", page_a)
        contratos["portadaAntesDeConfig"] = contratos["portadaUtilizable"] and bitacora_a.config_ms is None

        # Modal de lugar repetido con la config retenida: abrir, marcar, escribir y cerrar.
        if contratos["portadaUtilizable"]:
            for numero in (1, 2, 3):
                try:
                    ciclos.append(ciclo_modal(page_a, retenido_ms, numero))
                except Exception as fallo:
                    ciclos.append({"numero": numero, "fallo": f"{type(fallo).__name__}: {fallo}"})
                    break
            contratos["modalCiclosSanos"] = len(ciclos) == 3 and all(
                c.get("cerro") and c.get("nombrePorChip") == "Parcela / campo" for c in ciclos)
            contratos["modalDurantePendiente"] = contratos["modalCiclosSanos"] and bitacora_a.config_ms is None
            captura("modal-pendiente", page_a)

        # Mapa con la config pendiente: solo se exige que arranque y navegue (el cascarón).
        mr.ir_a_hash(page_a, "#/mapa")
        contratos["mapaDurantePendiente"] = esperar(page_a, "#map-search", retenido_ms) \
            and bitacora_a.config_ms is None

        # Formulario de reporte con la config pendiente: usable y cerrado ANTES de la llegada.
        if esperar(page_a, "#report", retenido_ms):
            try:
                page_a.click("#report", timeout=retenido_ms)
                page_a.wait_for_selector("#modal[open] #report-form", state="visible", timeout=retenido_ms)
                page_a.click('#rf-kind button[data-kind="llamas"]', timeout=retenido_ms)
                marca = page_a.get_attribute('#rf-kind button[data-kind="llamas"]', "aria-pressed")
                page_a.fill("#rf-desc", "Columna de humo bench")  # jamás se envía: sin envíos prohibidos
                page_a.click(".modal-x", timeout=retenido_ms)  # botón nativo del modal (form method=dialog)
                page_a.wait_for_function("!document.getElementById('modal').open", timeout=retenido_ms)
                contratos["reporteUtilizableSinConfig"] = marca == "true"
            except Exception:
                contratos["reporteUtilizableSinConfig"] = False
        captura("reporte-pendiente", page_a)

        # Canales de alerta abiertos con la config pendiente: la llegada repinta solo la
        # tarjeta de Telegram y no puede robar el foco de los botones del modal.
        # (#diag-canales exige lugares guardados; se abre alertChannels() por su export.)
        try:
            mr.ir_a_hash(page_a, "#/alertas")
            page_a.evaluate("() => import('/web/js/ui.js').then((m) => m.alertChannels())")
            page_a.wait_for_selector("#modal[open] #ch-push", state="visible", timeout=retenido_ms)
            page_a.locator("#ch-push").focus()
            foco_antes = page_a.evaluate(
                "() => document.activeElement ? document.activeElement.id : null")
            retencion_a.liberar()
            eventos["liberacionMs"] = bitacora_a.ms()
            if esperar_config(bitacora_a, page_a, args.retraso_config_ms / 1000 + args.timeout_s):
                foco_despues = page_a.evaluate(
                    "() => document.activeElement ? document.activeElement.id : null")
                contratos["canalesFocoConservadoTrasConfig"] = \
                    foco_antes == "ch-push" and foco_despues == "ch-push"
                sub = (page_a.text_content("#ch-telegram-card .card-sub") or "").strip()
                contratos["canalesRepintadoTrasConfig"] = "Comprobando" not in sub
            page_a.click(".modal-x", timeout=paso_ms)
            page_a.wait_for_function("!document.getElementById('modal').open", timeout=paso_ms)
        except Exception:
            contratos["canalesFocoConservadoTrasConfig"] = False
            contratos["canalesRepintadoTrasConfig"] = False
    finally:
        retencion_a.liberar()  # nunca dejar la config colgada, ni en los caminos de fallo
    renders_a = renders_turnstile(page_a)
    contratos["reporteSinWidgetHuerfano"] = len(renders_a) == 0  # cerrado antes de la llegada: nada se monta
    eventos["configMs"] = bitacora_a.config_ms
    captura("canales-tras-config", page_a)
    ctx_a.close()

    # ------------------------------------------- contexto B: conservación y re-aperturas
    ctx_b, page_b, bitacora_b, retencion_b, ts_b = nuevo_contexto()
    bitacora_b.arrancar()
    try:
        page_b.goto(args.url, wait_until="domcontentloaded", timeout=paso_ms)
        esperar(page_b, "#add-place", retenido_ms)  # la portada también arranca sin config aquí
        eventos["portadaBMs"] = bitacora_b.ms()
        # Modal de lugar con chip, select y texto puestos ANTES de liberar la config:
        # la llegada tardía no puede borrarlos ni robar el foco.
        page_b.click("#add-place", timeout=paso_ms)
        page_b.wait_for_selector("#modal[open] #place-form", state="visible", timeout=paso_ms)
        page_b.click('#pf-kind .chip[data-kind="parcela"]', timeout=paso_ms)
        page_b.select_option("#pf-radius", "15")
        page_b.fill("#pf-name", "Casa bench conservada")
    finally:
        retencion_b.liberar()
    eventos["liberacionBMs"] = bitacora_b.ms()
    captura("conservacion-pendiente", page_b)
    if esperar_config(bitacora_b, page_b, args.retraso_config_ms / 1000 + args.timeout_s):
        foco = page_b.evaluate(
            "() => { const el = document.activeElement; return el ? (el.id || el.tagName) : null; }")
        contratos["focoConservadoTrasConfig"] = foco == "pf-name"
        contratos["valoresConservadosTrasConfig"] = page_b.input_value("#pf-name") == "Casa bench conservada" \
            and page_b.input_value("#pf-radius") == "15" \
            and page_b.get_attribute('#pf-kind .chip[data-kind="parcela"]', "aria-pressed") == "true"
    try:
        page_b.click("#modal-body [data-cancel]", timeout=paso_ms)
        page_b.wait_for_function("!document.getElementById('modal').open", timeout=paso_ms)
    except Exception:
        pass
    eventos["configBMs"] = bitacora_b.config_ms
    captura("conservacion-tras-config", page_b)

    # Mapa completo con la configuración ya llegada: la hoja con las listas es el
    # contenido usable, no el cascarón.
    mr.ir_a_hash(page_b, "#/mapa")
    contratos["mapaUtilizable"] = esperar(page_b, "#map-listas h2")
    eventos["mapaMs"] = bitacora_b.ms()
    captura("mapa", page_b)

    # Apertura repetida del reporte: a lo más una carga de script y un widget por apertura,
    # siempre montado sobre un modal vivo (el mock registra la conexión del host).
    aperturas = 0
    for _ in (1, 2):
        try:
            page_b.click("#report", timeout=paso_ms)
            page_b.wait_for_selector("#modal[open] #report-form", state="visible", timeout=paso_ms)
            aperturas += 1
            page_b.click(".modal-x", timeout=paso_ms)
            page_b.wait_for_function("!document.getElementById('modal').open", timeout=paso_ms)
        except Exception:
            break
    renders_b = renders_turnstile(page_b)
    contratos["reporteUnaAperturaUnWidget"] = aperturas == 2 and len(renders_b) <= aperturas \
        and all(r.get("conectado") for r in renders_b) and ts_b["script"] <= 1
    captura("reporte-reabierto", page_b)

    # Transición de vuelta y un ciclo más: los callbacks no pueden quedar muertos tras navegar.
    mr.ir_a_hash(page_b, "#/")
    if esperar(page_b, "#add-place", retenido_ms):
        try:
            ciclo = ciclo_modal(page_b, paso_ms, "transicion")
            contratos["modalCiclosTransicion"] = ciclo.get("cerro") is True and \
                ciclo.get("nombrePorChip") == "Parcela / campo"
        except Exception:
            contratos["modalCiclosTransicion"] = False
    captura("transicion", page_b)
    ctx_b.close()

    # ------------------------------------------------ cierre global: lo que se exige siempre
    contratos["configRespondio"] = bitacora_a.config_ms is not None and bitacora_b.config_ms is not None
    errores = bitacora_a.errores + bitacora_b.errores
    posts = {"permitidos": bitacora_a.posts["permitidos"] + bitacora_b.posts["permitidos"],
             "prohibidos": bitacora_a.posts["prohibidos"] + bitacora_b.posts["prohibidos"]}
    contratos["sinErroresProducto"] = not [e for e in errores if e["clase"] == "producto"]
    contratos["sinCspViolaciones"] = not [e for e in errores if e.get("tipo") == "csp"]
    contratos["sinEnviosNiMutaciones"] = not posts["prohibidos"]
    eventos["turnstile"] = {
        "script": [ts_a["script"], ts_b["script"]],
        "renders": [len(renders_a), len(renders_b)],
        "nota": "mock efímero del proveedor, sin PII ni escrituras reales; el fixture no publica "
                "clave de sitio, ver pendientes",
    }
    # Transparencia del reintento: cuántas esperas murieron al instante (contexto invalidado
    # por la toma de control del service worker al arrancar) y se reintentaron dentro de
    # su mismo presupuesto. Con la portada usable esto suele ser 1 por contexto frío.
    eventos["esperaReintentos"] = dict(reintentos_espera)

    pendientes = list(PENDIENTES_FIJOS)
    if contratos.get("portadaAntesDeConfig") is not True:
        pendientes.insert(0, "La portada no respondió antes de /api/config: con --exigir-no-bloqueante "
                             "esta corrida falla (la ventana pendiente la garantiza la retención).")
    return {
        "generadoIso": mr.ahora_iso(),
        "url": args.url, "dispositivo": args.dispositivo, "retrasoConfigMs": args.retraso_config_ms,
        "exigido": args.exigir_no_bloqueante,
        "navegador": mr.version_navegador(browser), "playwright": mr.version_playwright(),
        "eventos": eventos, "contratos": contratos, "ciclosModal": ciclos,
        "errores": errores, "posts": posts,
        "pendientes": pendientes, "capturas": capturas,
    }


def informe_markdown(resultado: dict) -> str:
    si_no = {True: "cumple", False: "NO cumple", None: "pendiente"}
    lineas = [
        "# Verificación de configuración tardía (REND-02 PR2)",
        "",
        f"Generada: {resultado['generadoIso']} · Chromium {resultado['navegador']} · "
        f"Playwright {resultado['playwright'] or '—'}",
        f"Servidor: {resultado['url']} (efímero del CI; nunca producción) · "
        f"Retraso de /api/config: {resultado['retrasoConfigMs']} ms · Dispositivo: {resultado['dispositivo']}",
        f"Contratos de ventana pendiente: {'exigidos' if resultado['exigido'] else 'reportados'} · "
        "Dos contextos fríos con IP sintética: la ventana se garantiza reteniendo /api/config "
        "en el navegador (comprobación funcional, no medición de latencia).",
        "",
        "## Contratos",
        "",
    ]
    for clave in CONTRATOS_DUROS:
        lineas.append(f"- {clave}: {si_no.get(resultado['contratos'].get(clave))}")
    for clave in CONTRATOS_PENDIENTES:
        lineas.append(f"- {clave}: {si_no.get(resultado['contratos'].get(clave))} "
                      "(exigible con --exigir-no-bloqueante)")
    lineas += ["", "## Eventos", ""]
    for clave, valor in resultado["eventos"].items():
        lineas.append(f"- {clave}: {valor} ms" if isinstance(valor, (int, float)) else f"- {clave}: {valor}")
    por_clase = Counter(e["clase"] for e in resultado["errores"])
    lineas += ["", "## Errores (nada se omite)", "",
               "- " + (" · ".join(f"{clase}: {n}" for clase, n in sorted(por_clase.items())) or "ninguno")]
    for e in resultado["errores"]:
        if e["clase"] == "producto" or e.get("tipo") == "csp":
            lineas.append(f"- **{e['clase']} ({e.get('tipo')})**: "
                          f"{e.get('texto') or e.get('url')} {e.get('estado') or ''}".rstrip())
    posts = resultado["posts"]
    lineas += ["", "## Envíos al mismo origen", "",
               f"- Altas anónimas del dispositivo permitidas (POST {POST_PERMITIDO}): "
               f"{len(posts['permitidos'])}"]
    lineas += [f"- **Envío prohibido**: {url}" for url in posts["prohibidos"]]
    lineas += ["", "## Pendientes (edge cases para pruebas futuras)", ""]
    lineas += [f"- {p}" for p in resultado["pendientes"]]
    if resultado["capturas"]:
        lineas += ["", "## Capturas", ""]
        lineas += [f"- {c}" for c in resultado["capturas"]]
    lineas += ["",
               f"Cobertura y límites: docs/RENDIMIENTO_INTEGRAL.md · "
               f"Harness exclusivamente loopback ({HOST_PERMITIDO}:{PUERTO_PERMITIDO}).", ""]
    return "\n".join(lineas)


def main(argv=None) -> int:
    args = parsear_args(sys.argv[1:] if argv is None else argv)
    args.out.mkdir(parents=True, exist_ok=True)
    pw, browser = mr.lanzar_navegador()
    try:
        resultado = correr(args, browser)
    finally:
        pw.stop()
    (args.out / "config.json").write_text(
        json.dumps(resultado, indent=2, ensure_ascii=False), encoding="utf-8")
    (args.out / "config.md").write_text(informe_markdown(resultado), encoding="utf-8")
    incumplidos = contratos_incumplidos(resultado["contratos"], args.exigir_no_bloqueante)
    estado = "cumple" if not incumplidos else "NO cumple: " + ", ".join(incumplidos)
    print(f"config_check {estado} · informe: {args.out / 'config.md'} · "
          f"pendientes: {len(resultado['pendientes'])}", flush=True)
    return 0 if not incumplidos else 1


if __name__ == "__main__":
    sys.exit(main())

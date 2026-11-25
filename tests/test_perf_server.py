"""REND-02 PR2 — pruebas puras del retraso de /api/config en el servidor de rendimiento.

perf_server.retrasar_config(app, retraso_ms) envuelve la app ASGI para el perfil de
configuración tardía: solo las peticiones http con camino exacto /api/config duermen
(``await asyncio.sleep``) antes de reenviar a la app; el lifespan, el resto de rutas
y todos los mensajes (scope, receive, send, cuerpo, respuesta) pasan intactos.

Nada de esto levanta servidor ni proceso: las apps son falsas, las llamadas son directas
al wrapper y el reloj se controla parcheando asyncio.sleep. También quedan aquí las
pruebas puras de config_check.py (guarda de loopback, retención de /api/config,
política de envíos —solo el alta anónima del dispositivo se permite— y evaluación de
contratos), que importa Playwright solo al correr.
"""
from __future__ import annotations

import asyncio
import inspect
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "scripts" / "local"))
import config_check as cc  # noqa: E402
import perf_server as ps  # noqa: E402


# ------------------------------------------------------------------ fakes ASGI

def alcance_http(metodo="GET", camino="/api/config"):
    return {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
            "method": metodo, "path": camino, "raw_path": camino.encode(),
            "query_string": b"", "headers": [(b"host", b"127.0.0.1")]}


class AppFalsa:
    """App ASGI mínima: registra scope/receive/send y responde 200 con el cuerpo que llegó."""

    def __init__(self):
        self.alcances, self.cuerpos = [], []
        self.recibir = self.enviar = None

    async def __call__(self, scope, receive, send):
        self.alcances.append(scope)
        self.recibir, self.enviar = receive, send
        cuerpo = b""
        while True:
            mensaje = await receive()
            if mensaje["type"] == "http.request":
                cuerpo += mensaje.get("body", b"")
                if not mensaje.get("more_body"):
                    break
                continue
            break
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": cuerpo})
        self.cuerpos.append(cuerpo)


class AppVida:
    """App de lifespan: contesta startup y shutdown y registra todo lo que vio."""

    def __init__(self):
        self.eventos = []

    async def __call__(self, scope, receive, send):
        self.eventos.append(("alcance", scope["type"]))
        while True:
            mensaje = await receive()
            self.eventos.append((mensaje["type"],))
            if mensaje["type"] == "lifespan.startup":
                await send({"type": "lifespan.startup.complete"})
            elif mensaje["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return


def receptor(cuerpo=b'{"prueba": 1}'):
    cola = [{"type": "http.request", "body": cuerpo, "more_body": False}]

    async def recibir():
        return cola.pop(0) if cola else {"type": "http.disconnect"}

    return recibir


def receptor_vida():
    cola = [{"type": "lifespan.startup"}, {"type": "lifespan.shutdown"}]

    async def recibir():
        return cola.pop(0)

    return recibir


def emisor(registro):
    async def enviar(mensaje):
        registro.append(mensaje)

    return enviar


class SuenoGrabado:
    """asyncio.sleep falso que registra la espera y devuelve enseguida."""

    def __init__(self):
        self.llamadas = []

    async def __call__(self, segundos):
        self.llamadas.append(segundos)


class SuenoBloqueante:
    """asyncio.sleep falso que duerme hasta que la prueba lo despierte (como el retraso real)."""

    def __init__(self):
        self.llamadas = []
        self.entro = None
        self.despertar = None

    async def __call__(self, segundos):
        self.llamadas.append(segundos)
        self.entro.set()
        await self.despertar.wait()


# ------------------------------------------------------------------ el wrapper ASGI

def test_solo_el_camino_exacto_de_api_config_duerme(monkeypatch):
    sueno = SuenoGrabado()
    monkeypatch.setattr(asyncio, "sleep", sueno)
    app = AppFalsa()
    envolver = ps.retrasar_config(app, 3000)
    asyncio.run(envolver(alcance_http("GET", "/api/config"), receptor(), emisor([])))
    asyncio.run(envolver(alcance_http("POST", "/api/config"), receptor(), emisor([])))
    assert sueno.llamadas == [3.0, 3.0]
    assert [a["path"] for a in app.alcances] == ["/api/config", "/api/config"]


def test_ninguna_otra_ruta_ni_websocket_duerme(monkeypatch):
    sueno = SuenoGrabado()
    monkeypatch.setattr(asyncio, "sleep", sueno)
    app = AppFalsa()
    envolver = ps.retrasar_config(app, 3000)
    caminos = ("/", "/api/risk", "/api/config/", "/api/configx", "/api/configuracion",
               "/web/js/app.js", "/sw.js", "/API/CONFIG")
    for camino in caminos:
        asyncio.run(envolver(alcance_http("GET", camino), receptor(), emisor([])))
    # el retraso es solo http: un websocket al mismo camino pasa sin dormir
    asyncio.run(envolver({"type": "websocket", "path": "/api/config"}, receptor(), emisor([])))
    assert sueno.llamadas == []
    assert len(app.alcances) == len(caminos) + 1


def test_retraso_cero_o_nulo_no_duerme_nunca(monkeypatch):
    sueno = SuenoGrabado()
    monkeypatch.setattr(asyncio, "sleep", sueno)
    for retraso in (0, None):
        envolver = ps.retrasar_config(AppFalsa(), retraso)
        asyncio.run(envolver(alcance_http("GET", "/api/config"), receptor(), emisor([])))
    assert sueno.llamadas == []


def test_el_lifespan_pasa_sin_retraso(monkeypatch):
    sueno = SuenoGrabado()
    monkeypatch.setattr(asyncio, "sleep", sueno)
    app = AppVida()
    envolver = ps.retrasar_config(app, 3000)
    respuestas = []
    asyncio.run(envolver({"type": "lifespan"}, receptor_vida(), emisor(respuestas)))
    assert app.eventos[0] == ("alcance", "lifespan")
    assert ("lifespan.startup",) in app.eventos
    assert ("lifespan.shutdown",) in app.eventos
    assert respuestas == [{"type": "lifespan.startup.complete"}, {"type": "lifespan.shutdown.complete"}]
    assert sueno.llamadas == []


def test_la_espera_de_config_no_bloquea_una_ruta_concurrente(monkeypatch):
    async def escena():
        sueno = SuenoBloqueante()
        sueno.entro, sueno.despertar = asyncio.Event(), asyncio.Event()
        monkeypatch.setattr(asyncio, "sleep", sueno)
        app = AppFalsa()
        envolver = ps.retrasar_config(app, 3000)
        respuestas_config, respuestas_risk = [], []
        tarea = asyncio.create_task(
            envolver(alcance_http("GET", "/api/config"), receptor(), emisor(respuestas_config)))
        await sueno.entro.wait()  # /api/config quedó dormida en su retraso
        assert not tarea.done()
        # otra ruta atiende completa mientras config espera: el await no bloquea el bucle
        await envolver(alcance_http("GET", "/api/risk"), receptor(), emisor(respuestas_risk))
        assert [a["path"] for a in app.alcances] == ["/api/risk"]
        assert len(respuestas_risk) == 2
        sueno.despertar.set()
        await tarea
        assert [a["path"] for a in app.alcances] == ["/api/config", "/api/risk"]
        assert len(respuestas_config) == 2
        assert sueno.llamadas == [3.0]

    asyncio.run(escena())


def test_scope_recieve_send_cuerpo_y_respuesta_intactos(monkeypatch):
    sueno = SuenoGrabado()
    monkeypatch.setattr(asyncio, "sleep", sueno)
    app = AppFalsa()
    envolver = ps.retrasar_config(app, 1500)
    respuestas = []
    alcance = alcance_http("POST", "/api/config")
    recibir = receptor(b'{"prueba": "bench"}')
    enviar = emisor(respuestas)
    asyncio.run(envolver(alcance, recibir, enviar))
    assert sueno.llamadas == [1.5]
    assert app.alcances[0] is alcance  # el mismo alcance, sin copias ni reescrituras
    assert app.recibir is recibir and app.enviar is enviar  # receive/send pasan tal cual
    assert app.cuerpos == [b'{"prueba": "bench"}']  # el cuerpo llega entero y sin cambios
    assert respuestas == [{"type": "http.response.start", "status": 200, "headers": []},
                          {"type": "http.response.body", "body": b'{"prueba": "bench"}'}]


def test_el_wrapper_cumple_el_contrato_asgi():
    envolver = ps.retrasar_config(AppFalsa(), 10)
    assert inspect.iscoroutinefunction(envolver)
    assert list(inspect.signature(envolver).parameters) == ["scope", "receive", "send"]


def test_el_servidor_confia_solo_en_localhost_para_la_ip_sintetica():
    """La IP sintética por cabecera solo vale si uvicorn confía en 127.0.0.1 (nunca producción)."""
    texto = (RAIZ / "scripts" / "local" / "perf_server.py").read_text(encoding="utf-8")
    assert "proxy_headers=True" in texto
    assert 'forwarded_allow_ips="127.0.0.1"' in texto
    assert "BRASA_BENCH_CONFIG_DELAY_MS" in texto


# ------------------------------------------------------------------ config_check: guarda y contratos

def test_config_check_solo_corre_contra_el_loopback_del_harness():
    assert cc.url_permitida("http://127.0.0.1:8002")
    assert cc.url_permitida("http://127.0.0.1:8002/")  # mismo origen loopback
    rehusadas = (
        "https://brasa-chile.ddiegosebastianbb.workers.dev",  # producción: jamás
        "https://127.0.0.1:8002",
        "http://localhost:8002",
        "http://127.0.0.1:8001",  # el servidor base no es el de la comprobación
        "http://0.0.0.0:8002",
        "http://127.0.0.1.evil.example:8002",
        "file:///etc/hostname",
    )
    for url in rehusadas:
        assert not cc.url_permitida(url), url


def test_config_check_ip_sintetica_por_contexto():
    primera = cc.cabeceras_cliente()
    segunda = cc.cabeceras_cliente()
    assert primera != segunda  # cada contexto representa una IP distinta
    assert primera["X-Forwarded-For"].startswith("127.1.")
    assert segunda["X-Forwarded-For"].startswith("127.1.")


def test_config_check_solo_permite_el_alta_anonima_del_dispositivo():
    """La app da de alta el dispositivo nada más arrancar (automática); todo otro envío o
    mutación al mismo origen queda prohibido: reportes, push, lugares y avisos no se tocan."""
    base = "http://127.0.0.1:8002"
    assert cc.clasificar_post("http://127.0.0.1:8002/api/subscribers", base) == "permitido"
    prohibidos = (
        "http://127.0.0.1:8002/api/places",
        "http://127.0.0.1:8002/api/reports",
        "http://127.0.0.1:8002/api/push/subscribe",
        "http://127.0.0.1:8002/api/alerts/test",
        "http://127.0.0.1:8002/api/subscribers/otra-cosa",
        "http://127.0.0.1:8002/api/places/7",
    )
    for url in prohibidos:
        assert cc.clasificar_post(url, base) == "prohibido", url
    # lo externo no es «prohibido»: ya lo bloquea el harness y se clasifica aparte
    assert cc.clasificar_post("https://tiles.openfreemap.org/x", base) == "externo"


class CtxRutas:
    """Contexto de Playwright de mentira: registra los patrones que se enrutan."""

    def __init__(self):
        self.patrones = []

    def route(self, patron, manejador):
        self.patrones.append((patron, manejador))


class RutaConfig:
    """Ruta de /api/config de mentira: recuerda si la dejaron pasar."""

    def __init__(self):
        self.estado = "pendiente"

    def continue_(self):
        self.estado = "siguio"


def test_config_check_retiene_y_libera_config():
    """La ventana de «config pendiente» se garantiza reteniendo la ruta: el manejador
    guarda la petición y vuelve (Python libre); liberar la deja pasar y las nuevas pasan
    directas. Verificación funcional, no medición de latencia."""
    ctx = CtxRutas()
    retencion = cc.RetencionConfig()
    retencion.instalar(ctx)
    assert [p for p, _ in ctx.patrones] == ["**/api/config"]
    manejador = ctx.patrones[0][1]
    primera, segunda, tercera = RutaConfig(), RutaConfig(), RutaConfig()
    manejador(primera)
    manejador(segunda)
    assert primera.estado == "pendiente" and segunda.estado == "pendiente"
    assert retencion.capturadas == 2
    retencion.liberar()
    assert primera.estado == "siguio" and segunda.estado == "siguio"
    manejador(tercera)
    assert tercera.estado == "siguio"  # tras liberar, ninguna petición vuelve a retenerse
    assert retencion.retenidas == []


def test_config_check_liberar_tolera_rutas_canceladas():
    """Si la propia página canceló la petición retenida (su tope de 12 s), liberar no explota."""
    class RutaCancelada:
        def continue_(self):
            raise RuntimeError("net::ERR_ABORTED")

    retencion = cc.RetencionConfig()
    retencion._manejador(RutaCancelada())
    assert retencion.capturadas == 1
    retencion.liberar()  # no lanza: el fallo real se reporta como contracto roto, no como excepción
    assert retencion.retenidas == []


def test_config_check_argumentos():
    args = cc.parsear_args(["--url", "http://127.0.0.1:8002", "--out", "salida",
                            "--device", "mobile", "--retraso-config-ms", "3000"])
    assert args.dispositivo == "movil" and args.retraso_config_ms == 3000
    assert args.exigir_no_bloqueante is False
    exigentes = cc.parsear_args(["--url", "http://127.0.0.1:8002", "--out", "salida",
                                 "--device", "escritorio", "--retraso-config-ms", "3000",
                                 "--exigir-no-bloqueante"])
    assert exigentes.dispositivo == "escritorio" and exigentes.exigir_no_bloqueante
    invalidos = (
        ["--url", "https://produccion.example", "--out", "s", "--device", "movil",
         "--retraso-config-ms", "3000"],
        ["--url", "http://127.0.0.1:8002", "--out", "s", "--device", "tablet",
         "--retraso-config-ms", "3000"],
        ["--url", "http://127.0.0.1:8002", "--out", "s", "--device", "movil",
         "--retraso-config-ms", "-1"],
        ["--url", "http://127.0.0.1:8002", "--out", "s", "--device", "movil",
         "--retraso-config-ms", "11000"],
        ["--url", "http://127.0.0.1:8002", "--out", "s", "--device", "movil",
         "--retraso-config-ms", "0", "--exigir-no-bloqueante"],
        ["--url", "http://127.0.0.1:8002", "--out", "s", "--device", "movil",
         "--retraso-config-ms", "3000", "--timeout-s", "0"],
    )
    for argv in invalidos:
        with pytest.raises(SystemExit):
            cc.parsear_args(argv)


def test_config_check_contratos_duros_y_de_ventana_pendiente():
    sanos = {k: True for k in cc.CONTRATOS_DUROS + cc.CONTRATOS_PENDIENTES}
    assert cc.contratos_incumplidos(sanos, exigir=True) == []
    # Una corrida donde la ventana pendiente no se cumplió (p. ej. una regresión del front):
    # sin --exigir-no-bloqueante queda reportada como pendiente; con el flag (que pasa el
    # orquestador) falla la corrida. Nunca es un verde silencioso.
    humo = dict(sanos, portadaAntesDeConfig=False, modalDurantePendiente=None, mapaDurantePendiente=None)
    assert cc.contratos_incumplidos(humo, exigir=False) == []
    assert cc.contratos_incumplidos(humo, exigir=True) == \
        ["portadaAntesDeConfig", "modalDurantePendiente", "mapaDurantePendiente"]
    roto = dict(sanos, mapaUtilizable=False)
    assert cc.contratos_incumplidos(roto, exigir=False) == ["mapaUtilizable"]
    # un contrato duro sin medir también incumple: nada pasa por omisión
    assert "configRespondio" in cc.contratos_incumplidos(dict(sanos, configRespondio=None), exigir=False)

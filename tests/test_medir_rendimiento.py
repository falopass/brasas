"""PR1 — medición integral de rendimiento: lo puro de medir_rendimiento y comparar_rendimiento.

Sin navegador: Playwright se importa perezosamente y estas pruebas ejercitan la lógica
que decide si una medición es comparable: la matriz de perfiles, el mínimo de 5 muestras,
el orden alterno por pares, el resumen con medianas solo de muestras completas (errores e
incompletas conservadas), la validez de una comparación, la clasificación de errores
(producto/externo/bloqueado/esperado), los bytes de red vs caché, el reinicio de cada
transición SPA y los filtros de CLI para jobs de CI.

La medición en sí (navegador, CDP, contextos) la corren los scripts contra despliegues
reales; su cobertura está en docs/RENDIMIENTO_INTEGRAL.md.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "scripts" / "local"))
import medir_rendimiento as mr  # noqa: E402
import comparar_rendimiento as cr  # noqa: E402


def muestra(ms, estado="util", *, errores=None, fcp=None, lcp=None, bytes_red=1000, pasos_extra=None):
    """Muestra mínima con la forma real de medir_contexto."""
    pasos = {"directo": {"estado": estado, "ms": ms, "cls": 0.0, "tareasLargasMs": 10.0, "nTareasLargas": 1}}
    if pasos_extra:
        pasos.update(pasos_extra)
    return {
        "ruta": "mapa", "dispositivo": "movil", "red": "normal", "cpu": 1, "cache": "fria", "numero": 1,
        "pasos": pasos, "estado": mr.estado_global(pasos),
        "documento": {"fcpMs": fcp, "lcpMs": lcp, "clsMs": None, "loadMs": None, "dclMs": None},
        "errores": errores or [],
        "bytes": {"bytesRed": bytes_red, "bytesCache": 0, "pedidos": 2, "pedidosUnicos": 2, "duplicados": 0, "porTipo": {}},
        "procesamiento": {}, "interaccionRafMs": None, "captura": None,
        "completa": all(p["estado"] == "util" for p in pasos.values()),
    }


# ------------------------------------------------------------------ perfiles y rutas

def test_clientes_ci_aislados_sin_modificar_despliegues(monkeypatch):
    monkeypatch.delenv("BRASA_BENCH_CLIENT_IPS", raising=False)
    assert mr.cabeceras_cliente_ci("http://127.0.0.1:8001") == {}
    monkeypatch.setenv("BRASA_BENCH_CLIENT_IPS", "1")
    primera = mr.cabeceras_cliente_ci("http://127.0.0.1:8001")
    segunda = mr.cabeceras_cliente_ci("http://127.0.0.1:8002")
    assert primera != segunda
    assert primera["X-Forwarded-For"].startswith("127.1.")
    for base in ("https://brasa.example", "https://127.0.0.1:8001",
                 "http://127.0.0.1:9000", "http://127.0.0.1.example:8001"):
        assert mr.cabeceras_cliente_ci(base) == {}


def test_perfiles_de_la_matriz():
    assert mr.DISPOSITIVOS["movil"] == {"ancho": 390, "alto": 844, "tactil": True, "esMovil": True, "escala": 2}
    assert mr.DISPOSITIVOS["escritorio"]["ancho"] == 1280 and mr.DISPOSITIVOS["escritorio"]["alto"] == 900
    assert mr.DISPOSITIVOS["escritorio"]["tactil"] is False
    assert mr.REDES["normal"] == {"latencia": 40, "bajada": 12 * 1024 * 1024 // 8, "subida": 4 * 1024 * 1024 // 8}
    assert mr.REDES["lenta"] == {"latencia": 2000, "bajada": 400 * 1024 // 8, "subida": 400 * 1024 // 8}
    assert mr.CPUS == (1, 4)
    assert mr.CACHES == ("fria", "caliente", "offline")
    assert mr.ORIGENES_EXTERNOS == ("tiles.openfreemap.org", "gibs.earthdata.nasa.gov")


def test_rutas_reales_con_criterio_de_contenido_usable():
    for rid, ruta in mr.RUTAS.items():
        assert ruta["url"].startswith("/"), f"{rid}: la URL debe ser relativa al despliegue"
        assert ruta["tipo"] in ("spa", "estatica")
        assert ruta["listo"], f"{rid}: falta el selector de contenido usable"
        if ruta["tipo"] == "spa":
            assert ruta["hash"], f"{rid}: las rutas SPA necesitan hash para la navegación repetida"
    # El caso profundo apunta a un caso que de verdad existe en el catálogo versionado.
    casos = json.loads((RAIZ / "web" / "data" / "cases.json").read_text(encoding="utf-8"))["cases"]
    assert "penco-lirquen-2026" in {c["id"] for c in casos}
    assert mr.RUTAS["caso-penco-2026"]["url"] == "/#/casos/penco-lirquen-2026"


def test_criterios_por_ruta():
    assert mr.criterio_de("mapa")["fallo"].startswith("#map-carga-err")
    assert mr.criterio_de("riesgo")["listo"] == "#r-search"
    assert mr.criterio_de("riesgo")["listoPrimero"] is False
    # Calidad puede tener un bloque parcial fallido con la vista pintada: el contenido manda.
    assert mr.criterio_de("calidad")["listoPrimero"] is True
    assert mr.criterio_de("preguntas")["minTexto"] == 300
    js = mr.criterio_js("riesgo")
    assert js.startswith("window.__brasaPerfCriterio = ") and "#r-search" in js


# ------------------------------------------------------------------ CLI: mínimo, filtros y alias

def test_minimo_cinco_muestras():
    with pytest.raises(SystemExit):
        mr.parsear_args(["https://a.example", "salida", "--muestras", "4"])
    with pytest.raises(SystemExit):
        cr.parsear_args(["--base", "https://a.example", "--candidata", "https://b.example",
                         "--out", "salida", "--samples", "3"])


def test_filtros_recortan_la_matriz():
    args = mr.parsear_args(["https://a.example", "salida", "--device", "mobile", "--network", "3g",
                            "--cpu", "4", "--cache", "cold", "--ruta", "mapa,riesgo"])
    assert args.dispositivos == ["movil"]
    assert args.redes == ["lenta"]
    assert args.cpus == [4]
    assert args.caches == ["fria"]
    assert args.rutas == ["mapa", "riesgo"]
    combos = mr.combinaciones(args.dispositivos, args.redes, args.cpus, args.caches, args.rutas)
    assert combos == [{"dispositivo": "movil", "red": "lenta", "cpu": 4, "cache": "fria", "ruta": "mapa"},
                      {"dispositivo": "movil", "red": "lenta", "cpu": 4, "cache": "fria", "ruta": "riesgo"}]


def test_filtros_invalidos_se_rechazan():
    for extra in (["--device", "tablet"], ["--network", "5g"], ["--cpu", "3"],
                  ["--cache", "tibia"], ["--ruta", "inexistente"]):
        with pytest.raises(SystemExit):
            mr.parsear_args(["https://a.example", "salida", *extra])


def test_sin_filtros_la_matriz_es_completa():
    args = mr.parsear_args(["https://a.example", "salida"])
    assert args.dispositivos == ["movil", "escritorio"]
    assert args.redes == ["normal", "lenta"]
    assert args.cpus == [1, 4]
    assert args.caches == ["fria", "caliente", "offline"]
    assert args.rutas == list(mr.RUTAS)
    assert args.muestras == 5
    # La matriz completa existe (360 combinaciones × rutas); los filtros la hacen manejable en CI.
    assert len(mr.combinaciones(args.dispositivos, args.redes, args.cpus, args.caches, args.rutas)) \
        == 2 * 2 * 2 * 3 * len(mr.RUTAS)


def test_alias_ingles_del_cli_de_comparacion():
    args = cr.parsear_args(["--base", "https://a.example", "--candidate", "https://b.example",
                            "--out", "salida", "--samples", "5", "--device", "desktop"])
    assert args.candidata == "https://b.example"
    assert args.dispositivos == ["escritorio"]


# ------------------------------------------------------------------ orden alterno y estados

def test_orden_de_pares_alternado():
    assert mr.orden_pares(1) == ["base", "candidata"]
    assert mr.orden_pares(2) == ["base", "candidata", "candidata", "base"]
    assert mr.orden_pares(5) == ["base", "candidata", "candidata", "base", "base", "candidata",
                                 "candidata", "base", "base", "candidata"]


def test_estado_global_de_pasos():
    util = {"estado": "util"}
    assert mr.estado_global({"directo": util, "reingreso": util}) == "util"
    assert mr.estado_global({"directo": util, "reingreso": {"estado": "fallo"}}) == "mixto"
    assert mr.estado_global({"directo": {"estado": "fallo"}, "reingreso": {"estado": "fallo"}}) == "fallo"
    assert mr.estado_global({"directo": util, "reingreso": {"estado": "timeout"}}) == "timeout"
    assert mr.estado_global({}) == "fallo"


# ------------------------------------------------------------------ resumen, errores y validez

def test_resumen_medianas_solo_con_muestras_completas():
    muestras = [muestra(100), muestra(120), muestra(140), muestra(200, estado="timeout")]
    res = mr.resumir_muestras(muestras)
    assert res["n"] == 4 and res["nCompletas"] == 3 and res["nIncompletas"] == 1
    assert res["pasos"]["directo"]["medianaMs"] == 120.0
    assert res["pasos"]["directo"]["peorMs"] == 140.0
    assert res["porEstado"].get("timeout") == 1
    assert res["porEstado"].get("util") == 3


def test_muestra_incompleta_no_contamina_documento_bytes_ni_pasos_utiles():
    completa = muestra(100, fcp=50, lcp=70, bytes_red=1000)
    parcial = muestra(999, fcp=900, lcp=1000, bytes_red=9000,
                      pasos_extra={"reingreso": {"estado": "timeout", "ms": 90000}})
    res = mr.resumir_muestras([completa, parcial])
    assert res["pasos"]["directo"]["medianaMs"] == 100
    assert res["documento"]["lcpMedianaMs"] == 70
    assert res["bytes"]["bytesRedMediana"] == 1000
    assert res["nIncompletas"] == 1


def test_resumen_conserva_y_clasifica_errores():
    errores = [{"clase": "producto", "tipo": "http", "url": "/api/risk", "estado": 500},
               {"clase": "externo", "tipo": "js"},
               {"clase": "bloqueado", "tipo": "red"},
               {"clase": "esperado", "tipo": "http"}]
    res = mr.resumir_muestras([muestra(100, errores=errores)])
    assert res["errores"] == {"producto": 1, "externo": 1, "bloqueado": 1, "esperado": 1, "medidor": 0}
    assert mr.codigo_salida(res) == 1  # los errores del producto hacen fallar la corrida
    solo_externo = mr.resumir_muestras([muestra(100, errores=[{"clase": "externo"}])])
    assert mr.codigo_salida(solo_externo) == 0  # los externos se distinguen y no fallan


def test_comparacion_valida_exige_minimo_y_cero_incompletas():
    bien = mr.resumir_muestras([muestra(100) for _ in range(5)])
    valida, motivos = mr.comparacion_valida(bien, bien)
    assert valida and motivos == []
    con_incompleta = mr.resumir_muestras([muestra(100) for _ in range(4)] + [muestra(999, estado="timeout")])
    valida, motivos = mr.comparacion_valida(bien, con_incompleta)
    assert not valida and any("incompletas" in m for m in motivos)
    pocas = mr.resumir_muestras([muestra(100) for _ in range(4)])
    valida, motivos = mr.comparacion_valida(pocas, pocas)
    assert not valida and any("completas" in m for m in motivos)


def test_resumen_red_separa_bytes_de_red_y_de_cache():
    pedidos = {
        "1": {"url": "https://a/x.js", "tipo": "Script", "bytes": 1000, "desdeCache": False, "desdeSw": False, "estado": 200},
        "2": {"url": "https://a/x.js", "tipo": "Script", "bytes": 1000, "desdeCache": False, "desdeSw": False, "estado": 200},
        "3": {"url": "https://a/api", "tipo": "Fetch", "bytes": 500, "desdeCache": True, "desdeSw": False, "estado": 200},
        "4": {"url": "https://a/y.css", "tipo": "Stylesheet", "bytes": 200, "desdeCache": False, "desdeSw": True, "estado": 200},
    }
    res = mr.resumen_red(pedidos)
    assert res["bytesRed"] == 2000  # lo servido por la red (encodedDataLength), no lo cacheado
    assert res["bytesCache"] == 700  # disco y service worker aparte
    assert res["pedidos"] == 4 and res["pedidosUnicos"] == 3 and res["duplicados"] == 1


def test_clasificacion_de_urls_y_textos():
    assert mr.es_externa("https://gibs.earthdata.nasa.gov/wmts/epsg3857/best")
    assert not mr.es_externa("https://brasa.example/web/js/app.js")
    assert mr.clasificar_url("https://tiles.openfreemap.org/x", "https://brasa.example", bloqueadas=True) == "bloqueado"
    assert mr.clasificar_url("https://tiles.openfreemap.org/x", "https://brasa.example", bloqueadas=False) == "externo"
    assert mr.clasificar_url("https://brasa.example/api/risk", "https://brasa.example") == "producto"
    assert mr.clasificar_url("https://otro.example/x", "https://brasa.example") == "externo"
    assert mr.clase_texto("Error loading tile https://tiles.openfreemap.org/planet/...") == "externo"
    assert mr.clase_texto("TypeError: no se puede leer 'map'") == "producto"
    assert mr.mismo_origen("https://a.example/x", "https://a.example")
    assert not mr.mismo_origen("http://a.example/x", "https://a.example")
    assert not mr.mismo_origen("http://a.example:8001/x", "http://a.example:8002")
    assert mr.mismo_origen("https://a.example:443/x", "https://a.example")


def test_criterio_inicial_unico_por_documento_y_transicion_sin_datos_viejos():
    js = mr.criterios_documento_js()
    assert "location.hash" in js and "location.pathname" in js
    assert mr.criterio_de("riesgo")["hash"] == "#/riesgo"
    assert "P.ruta.anterior" in mr.RECOLECTOR_JS
    assert "const inicioDoc = 0" in mr.RECOLECTOR_JS


# ------------------------------------------------------------------ reinicio de transición e informe

def test_recolector_reinicia_el_marco_por_transicion():
    js = mr.RECOLECTOR_JS
    assert "P.reset" in js
    assert "estado: 'pendiente'" in js  # el reset vuelve a poner la ruta en pendiente
    assert "cls: 0" in js  # y el CLS de la transición parte de cero
    assert "'longtask'" in js  # tareas largas del hilo principal (no «tiempo de parseo»)
    assert "parsetime" not in js.lower()
    assert "P.leer" in js and "largest-contentful-paint" in js and "'first-contentful-paint'" in js
    # El documento y la ruta usable se separan: leer() devuelve fcp/lcp del documento y ruta aparte.
    assert "fcp:" in js and "ruta:" in js


def test_import_perezoso_sin_playwright():
    assert not hasattr(mr, "sync_playwright"), "medir_rendimiento no debe importar Playwright al cargar"
    assert not hasattr(cr, "sync_playwright")
    assert mr.MIN_MUESTRAS == 5


def test_json_incremental_atomico(tmp_path):
    ruta = tmp_path / "medicion.json"
    mr.escribir_incremental(ruta, {"n": 1})
    mr.escribir_incremental(ruta, {"n": 2})
    assert json.loads(ruta.read_text(encoding="utf-8")) == {"n": 2}
    assert not list(tmp_path.glob("*.tmp")), "la escritura incremental no deja temporales"


def test_url_de_ruta_normaliza_la_base():
    assert mr.url_de_ruta("https://a.example/", "/#/mapa") == "https://a.example/#/mapa"
    assert mr.url_de_ruta("https://a.example", "/focos.html") == "https://a.example/focos.html"


def test_delta_porcentaje():
    assert mr.delta_porcentaje(100, 150) == 50.0
    assert mr.delta_porcentaje(100, 90) == -10.0
    assert mr.delta_porcentaje(None, 5) is None
    assert mr.delta_porcentaje(100, None) is None
    assert mr.delta_porcentaje(0, 5) is None


def test_informe_y_codigo_de_salida_de_la_comparacion():
    base = [muestra(100) for _ in range(5)]
    candidata = [muestra(150) for _ in range(5)]
    datos = {"metadatos": {}, "comparacion": cr.comparar(base, candidata, 5)}
    texto = cr.informe_markdown(datos)
    assert "mapa" in texto and "+50.0 %" in texto and "| sí |" in texto
    assert cr.codigo_salida(datos) == 0

    con_fallo = [muestra(100, errores=[{"clase": "producto", "tipo": "js"}])]
    datos_error = {"comparacion": cr.comparar(con_fallo, [muestra(150)], 1)}
    assert cr.codigo_salida(datos_error) == 1  # los errores del producto dominan el código de salida

    con_timeout = [muestra(150) for _ in range(4)] + [muestra(999, estado="timeout")]
    datos_invalida = {"comparacion": cr.comparar(base, con_timeout, 5)}
    texto_invalida = cr.informe_markdown(datos_invalida)
    assert "NO" in texto_invalida and "incompletas" in texto_invalida
    assert cr.codigo_salida(datos_invalida) == 2  # sin errores del producto, la comparación queda invalidada


# ------------------------------------------------------------------ REND-02 PR2: /api/config retrasada

class CtxFalso:
    """Contexto de Playwright de mentira: registra los patrones que se enrutan."""

    def __init__(self):
        self.patrones = []

    def route(self, patron, manejador):
        self.patrones.append((patron, manejador))


class RutaFalsa:
    """Ruta interceptada de mentira: guarda la acción que tomó el manejador."""

    def __init__(self, url):
        self.request = SimpleNamespace(url=url)
        self.accion = None

    def abort(self):
        self.accion = "abortar"

    def continue_(self):
        self.accion = "seguir"


def _manejador_de(ctx, patron):
    return next(manejador for p, manejador in ctx.patrones if p == patron)


def test_modo_servidor_el_navegador_no_retrasa_config(monkeypatch):
    """BRASA_BENCH_CONFIG_SERVER=1: el retraso lo pone perf_server; el cliente ni enruta /api/config."""
    monkeypatch.setenv("BRASA_BENCH_CONFIG_SERVER", "1")
    ctx = CtxFalso()
    mr.instalar_rutas(ctx, {"retrasoConfigMs": 3000, "integracionReal": False})
    patrones = [p for p, _ in ctx.patrones]
    assert patrones == [f"https://{host}/**" for host in mr.ORIGENES_EXTERNOS]
    assert not any("api/config" in p for p in patrones), \
        "con el retraso en el servidor, duplicarlo en el cliente mediría dos veces la espera"


def test_modo_standalone_el_navegador_retrasa_config(monkeypatch):
    monkeypatch.delenv("BRASA_BENCH_CONFIG_SERVER", raising=False)
    ctx = CtxFalso()
    mr.instalar_rutas(ctx, {"retrasoConfigMs": 3000, "integracionReal": False})
    manejador = _manejador_de(ctx, "**/api/config")
    dormidas = []
    monkeypatch.setattr(mr.time, "sleep", lambda segundos: dormidas.append(segundos))
    config = RutaFalsa("http://127.0.0.1:8002/api/config")
    manejador(config)
    assert dormidas == [3.0] and config.accion == "seguir"
    # solo el camino exacto de config duerme; el resto pasa
    otra = RutaFalsa("http://127.0.0.1:8002/api/risk")
    manejador(otra)
    assert dormidas == [3.0] and otra.accion == "seguir"


def test_los_bloqueos_externos_siguen_intactos(monkeypatch):
    monkeypatch.delenv("BRASA_BENCH_CONFIG_SERVER", raising=False)
    ctx = CtxFalso()
    mr.instalar_rutas(ctx, {"retrasoConfigMs": 3000, "integracionReal": False})
    manejador = _manejador_de(ctx, "https://tiles.openfreemap.org/**")
    tile = RutaFalsa("https://tiles.openfreemap.org/planet/3/4/5.png")
    manejador(tile)
    assert tile.accion == "abortar"
    # lo del propio despliegue nunca se aborta, aunque comparta manejador
    propia = RutaFalsa("http://127.0.0.1:8002/web/js/app.js")
    manejador(propia)
    assert propia.accion == "seguir"


def test_standalone_sin_retraso_no_enruta_config(monkeypatch):
    monkeypatch.delenv("BRASA_BENCH_CONFIG_SERVER", raising=False)
    ctx = CtxFalso()
    mr.instalar_rutas(ctx, {"retrasoConfigMs": 0, "integracionReal": False})
    assert [p for p, _ in ctx.patrones] == [f"https://{host}/**" for host in mr.ORIGENES_EXTERNOS]


def test_integracion_real_no_instala_bloqueos(monkeypatch):
    monkeypatch.delenv("BRASA_BENCH_CONFIG_SERVER", raising=False)
    ctx = CtxFalso()
    mr.instalar_rutas(ctx, {"retrasoConfigMs": 3000, "integracionReal": True})
    manejador = _manejador_de(ctx, "**/api/config")
    tile = RutaFalsa("https://gibs.earthdata.nasa.gov/wmts/x")
    manejador(tile)
    assert tile.accion == "seguir", "con --integracion-real el externo pasa (se registra aparte)"


def test_retraso_config_del_cli_y_opciones():
    args = mr.parsear_args(["https://a.example", "salida", "--retraso-config-ms", "3000"])
    assert args.retraso_config_ms == 3000
    assert mr.opciones_de(args)["retrasoConfigMs"] == 3000
    assert mr.parsear_args(["https://a.example", "salida"]).retraso_config_ms == 0
    # el negativo se rechaza (el tope de 10000 lo valida el orquestador del CI)
    with pytest.raises(SystemExit):
        mr.parsear_args(["https://a.example", "salida", "--retraso-config-ms", "-1"])

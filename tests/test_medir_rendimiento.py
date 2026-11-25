"""PR1 — medición integral de rendimiento: lo puro de medir_rendimiento y comparar_rendimiento.

Sin navegador: Playwright se importa perezosamente y estas pruebas ejercitan la lógica
que decide si una medición es comparable: la matriz de perfiles, el mínimo de 5 muestras,
el orden alterno por pares, el resumen con medianas solo de muestras completas (errores e
incompletas conservadas), la validez de una comparación, la clasificación de errores
(producto/externo/bloqueado/esperado), los bytes de red vs caché, el reinicio de cada
transición SPA y los filtros de CLI para jobs de CI.

REND-02 tanda 5 cubre además: el desglose de bytes por grupo de recurso (clasificación de
URLs, sumas, duplicados, red vs caché), las rutas mapa-capas (nombres públicos y orden de
capas, espera de red quieta tras el contenido usable) y la grilla de viento sintética del
servidor de rendimiento (forma exacta de backend/windgrid.py, determinista y
representativa en tamaño).

Esta continuación añade la ruta `mapa-capas-santiago` (mapa con capas acercado a una
ubicación real de Santiago con lat/lon/z), el límite estricto de las esperas (la encuesta
nunca sobrepasa el tope del paso) y sus timeouts explícitos: antes de la ventana de red
quieta se espera de forma verificable el encuadre (zoom objetivo con tolerancia y mapa
sin movimiento, vía getMap de /web/js/map.js desde la página), porque el contenido usable
llega mientras el vuelo animado sigue en curso y las teselas de infraestructura solo se
piden tras moveend. Si el encuadre o la red quieta no se confirman dentro del timeout,
la muestra queda incompleta como error del medidor, sin tocar el tiempo hasta el
contenido usable.

La medición en sí (navegador, CDP, contextos) la corren los scripts contra despliegues
reales; su cobertura está en docs/RENDIMIENTO_INTEGRAL.md.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "scripts" / "local"))
import medir_rendimiento as mr  # noqa: E402
import comparar_rendimiento as cr  # noqa: E402


def muestra(ms, estado="util", *, errores=None, fcp=None, lcp=None, bytes_red=1000, pasos_extra=None,
            por_grupo=None):
    """Muestra mínima con la forma real de medir_contexto."""
    pasos = {"directo": {"estado": estado, "ms": ms, "cls": 0.0, "tareasLargasMs": 10.0, "nTareasLargas": 1}}
    if pasos_extra:
        pasos.update(pasos_extra)
    return {
        "ruta": "mapa", "dispositivo": "movil", "red": "normal", "cpu": 1, "cache": "fria", "numero": 1,
        "pasos": pasos, "estado": mr.estado_global(pasos),
        "documento": {"fcpMs": fcp, "lcpMs": lcp, "clsMs": None, "loadMs": None, "dclMs": None},
        "errores": errores or [],
        "bytes": {"bytesRed": bytes_red, "bytesCache": 0, "pedidos": 2, "pedidosUnicos": 2, "duplicados": 0,
                  "porTipo": {}, "porGrupo": por_grupo or {}},
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


def test_ruta_mapa_capas_mide_el_costo_de_prender_capas():
    ruta = mr.RUTAS["mapa-capas"]
    assert ruta["url"] == "/#/mapa?capas=focos,viento,infraestructura"
    assert ruta["hash"] == "#/mapa?capas=focos,viento,infraestructura"
    assert ruta["tipo"] == "spa"
    # mismo criterio de contenido usable (y de fallo) que mapa
    assert ruta["listo"] == mr.RUTAS["mapa"]["listo"]
    assert ruta["fallo"] == mr.RUTAS["mapa"]["fallo"]
    # tras util, espera la red quieta de los grupos que mide
    assert set(ruta["redQuieta"]) == {"infraestructura", "viento"}
    assert all(grupo in mr.GRUPOS_RECURSOS for grupo in ruta["redQuieta"])
    # los nombres de capas son los públicos de web/js/capas.js (url: de CAPAS) y van en el
    # orden del control: capasToUrl reescribe la URL con ese orden y el hash queda estable
    capas_js = (RAIZ / "web" / "js" / "capas.js").read_text(encoding="utf-8")
    nombres = [n.strip() for n in ruta["url"].split("capas=")[1].split(",")]
    for nombre in nombres:
        assert f"url: '{nombre}'" in capas_js, f"{nombre} no es un nombre público de capa"
    posiciones = [capas_js.index(f"url: '{n}'") for n in nombres]
    assert posiciones == sorted(posiciones), "las capas deben ir en el orden del control (capasToUrl)"
    # el CLI la acepta; sin filtro, la matriz completa la incluye
    args = mr.parsear_args(["https://a.example", "salida", "--ruta", "mapa-capas"])
    assert args.rutas == ["mapa-capas"]
    assert "mapa-capas" in mr.parsear_args(["https://a.example", "salida"]).rutas
    # el criterio inicial del documento empareja el hash completo con capas
    js = mr.criterios_documento_js()
    assert "#/mapa?capas=focos,viento,infraestructura" in js


def test_ruta_mapa_capas_santiago_acercado_en_ubicacion_real():
    import math

    ruta = mr.RUTAS["mapa-capas-santiago"]
    # URL profunda real: la vista interpreta lat/lon/z al montar (fly al encuadre) y con
    # lat/lon no reencuadra a los focos, así que el encuadre medido es siempre Santiago
    assert ruta["url"].startswith("/#/mapa?capas=")
    params = dict(p.split("=") for p in ruta["url"].split("?")[1].split("&"))
    assert params["lat"] == "-33.45" and params["lon"] == "-70.66"
    # z 11 supera INFRA_MINZOOM (10): las teselas de infraestructura del encuadre se piden
    assert params["z"] == "11" and int(params["z"]) >= 10
    # mismo criterio de contenido usable (y de fallo) que mapa y mapa-capas
    assert ruta["listo"] == mr.RUTAS["mapa"]["listo"]
    assert ruta["fallo"] == mr.RUTAS["mapa"]["fallo"]
    assert set(ruta["redQuieta"]) == {"infraestructura", "viento"}
    assert ruta["tipo"] == "spa"
    # el hash completo (capas + lat/lon/z) es el criterio de la muestra: updateCapasUrl de
    # la vista conserva los parámetros que no son `capas` y reescribe `capas` con el orden
    # del control, así que el hash queda estable durante toda la muestra
    assert ruta["hash"] == ruta["url"].lstrip("/")
    # el encuadre esperado se declara con el zoom de la URL: la medición lo verifica contra
    # el mapa real antes de cerrar los bytes (el contenido usable llega antes del fin del vuelo)
    assert ruta["encuadre"] == {"zoom": 11} and int(params["z"]) == ruta["encuadre"]["zoom"]
    assert 0 < mr.ENCUADRE_TOLERANCIA_ZOOM <= 0.5
    capas_js = (RAIZ / "web" / "js" / "capas.js").read_text(encoding="utf-8")
    nombres = [n.strip() for n in params["capas"].split(",")]
    posiciones = [capas_js.index(f"url: '{n}'") for n in nombres]
    assert posiciones == sorted(posiciones), "las capas van en el orden del control (capasToUrl)"
    # los comportamientos de la vista que sostienen ese hash estable (solo lectura: si la
    # vista cambia, este check obliga a revisar el criterio de la ruta)
    mapa_js = (RAIZ / "web" / "js" / "views" / "mapa.js").read_text(encoding="utf-8")
    assert "const params = new URLSearchParams(query);" in mapa_js
    assert "params.set('capas', capasToUrl(layers));" in mapa_js
    assert "history.replaceState" in mapa_js  # reescribir el hash no remonta la vista
    assert "fly(Number(params.lon), Number(params.lat), Number(params.z) || 11)" in mapa_js
    # la espera del encuadre consulta la API pública del mapa real de la página
    map_js = (RAIZ / "web" / "js" / "map.js").read_text(encoding="utf-8")
    assert "export function getMap" in map_js
    # ubicación real representativa: ambos encuadres (móvil y escritorio) caen en la tesela
    # -34_-71, la más grande del catastro (centro de Chile metropolitano)
    assert math.floor(float(params["lat"])) == -34 and math.floor(float(params["lon"])) == -71
    indice = json.loads((RAIZ / "web" / "data" / "infraestructura" / "indice.json").read_text(encoding="utf-8"))
    assert indice["teselas"]["-34_-71"]["rows"] > 1000
    assert (RAIZ / "web" / "data" / "infraestructura" / "t" / "-34_-71.json").exists()
    # el CLI la acepta; sin filtro, la matriz completa la incluye
    args = mr.parsear_args(["https://a.example", "salida", "--ruta", "mapa-capas-santiago"])
    assert args.rutas == ["mapa-capas-santiago"]
    assert "mapa-capas-santiago" in mr.parsear_args(["https://a.example", "salida"]).rutas
    # el criterio inicial del documento empareja el hash completo, parámetros incluidos
    assert ruta["hash"] in mr.criterios_documento_js()


def test_ci_por_defecto_mide_mapa_capas_acercado():
    import ejecutar_rendimiento_ci as eci

    rutas = eci.RUTAS_CI_PREDETERMINADAS.split(",")
    assert len(rutas) == len(set(rutas)), "el CI no mide rutas repetidas"
    assert "mapa-capas" in rutas and "mapa-capas-santiago" in rutas
    # el CI solo puede medir rutas que existen y cada una con criterio de contenido usable
    assert all(r in mr.RUTAS for r in rutas)
    assert all(mr.RUTAS[r]["listo"] for r in rutas)


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
    res = mr.resumen_red(pedidos, "https://a")
    assert res["bytesRed"] == 2000  # lo servido por la red (encodedDataLength), no lo cacheado
    assert res["bytesCache"] == 700  # disco y service worker aparte
    assert res["pedidos"] == 4 and res["pedidosUnicos"] == 3 and res["duplicados"] == 1


# ------------------------------------------- REND-02 tanda 5: desglose por grupo de recurso

def test_grupo_de_url_clasifica_por_grupo_de_recurso():
    base = "https://brasa.example"
    assert mr.grupo_de_url(f"{base}/web/data/infraestructura/indice.json", base) == "infraestructura"
    # las teselas de 1° de la infraestructura particionada también son del grupo
    assert mr.grupo_de_url(f"{base}/web/data/infraestructura/t/-33_-71.json", base) == "infraestructura"
    assert mr.grupo_de_url(f"{base}/api/wind/grid", base) == "viento"
    assert mr.grupo_de_url(f"{base}/web/data/cases.json", base) == "datosEstaticos"
    assert mr.grupo_de_url(f"{base}/api/risk", base) == "api"
    assert mr.grupo_de_url(f"{base}/web/js/app.js", base) == "app"
    assert mr.grupo_de_url(f"{base}/", base) == "app"
    # las fuentes externas del mapa (bloqueadas por defecto) son su propio grupo
    assert mr.grupo_de_url("https://tiles.openfreemap.org/planet/3/4/5.png", base) == "teselasMapa"
    assert mr.grupo_de_url("https://gibs.earthdata.nasa.gov/wmts/x", base) == "teselasMapa"
    # un tercero que no es teselas: inesperado, se informa aparte
    assert mr.grupo_de_url("https://otro.example/datos.json", base) == "otros"
    # los prefijos específicos ganan a los genéricos
    assert mr.grupo_de_url(f"{base}/web/data/infraestructura/otro.json", base) == "infraestructura"
    assert set(mr.GRUPOS_RECURSOS) >= {"infraestructura", "viento", "teselasMapa", "datosEstaticos", "api"}
    assert mr.grupo_de_url(f"{base}/web/data/infraestructura/indice.json", "https://otro.example") == "otros"


def test_resumen_red_desglosa_bytes_por_grupo():
    base = "https://brasa.example"
    pedidos = {
        "1": {"url": f"{base}/web/data/infraestructura/indice.json", "tipo": "Fetch", "bytes": 40000,
              "desdeCache": False, "desdeSw": False, "estado": 200},
        "2": {"url": f"{base}/web/data/infraestructura/indice.json", "tipo": "Fetch", "bytes": 40000,
              "desdeCache": True, "desdeSw": False, "estado": 200},
        "3": {"url": f"{base}/api/wind/grid", "tipo": "Fetch", "bytes": 60000,
              "desdeCache": False, "desdeSw": False, "estado": 200},
        "4": {"url": f"{base}/web/data/cases.json", "tipo": "Fetch", "bytes": 9000,
              "desdeCache": False, "desdeSw": True, "estado": 200},
        "5": {"url": f"{base}/api/risk", "tipo": "Fetch", "bytes": 7000,
              "desdeCache": False, "desdeSw": False, "estado": 200},
        "6": {"url": f"{base}/web/js/app.js", "tipo": "Script", "bytes": 50000,
              "desdeCache": False, "desdeSw": False, "estado": 200},
        "7": {"url": "https://tiles.openfreemap.org/planet/3/4/5.png", "tipo": "Image", "bytes": 0,
              "desdeCache": False, "desdeSw": False, "estado": None},
    }
    res = mr.resumen_red(pedidos, base)
    g = res["porGrupo"]
    # por grupo: n pedidos, bytesRed, bytesCache y duplicados (la misma URL dos veces)
    assert g["infraestructura"] == {"n": 2, "bytesRed": 40000, "bytesCache": 40000, "duplicados": 1}
    assert g["viento"] == {"n": 1, "bytesRed": 60000, "bytesCache": 0, "duplicados": 0}
    assert g["datosEstaticos"] == {"n": 1, "bytesRed": 0, "bytesCache": 9000, "duplicados": 0}
    assert g["api"] == {"n": 1, "bytesRed": 7000, "bytesCache": 0, "duplicados": 0}
    assert g["app"] == {"n": 1, "bytesRed": 50000, "bytesCache": 0, "duplicados": 0}
    # teselas bloqueadas: cuentan pedidos, sin bytes (por defecto se abortan)
    assert g["teselasMapa"] == {"n": 1, "bytesRed": 0, "bytesCache": 0, "duplicados": 0}
    assert g["otros"] == {"n": 0, "bytesRed": 0, "bytesCache": 0, "duplicados": 0}
    # los grupos siempre están todos y suman exactamente los totales del resumen
    assert set(g) == set(mr.GRUPOS_RECURSOS)
    assert sum(x["n"] for x in g.values()) == res["pedidos"]
    assert sum(x["bytesRed"] for x in g.values()) == res["bytesRed"]
    assert sum(x["bytesCache"] for x in g.values()) == res["bytesCache"]
    assert sum(x["duplicados"] for x in g.values()) == res["duplicados"]


def test_resumen_mediana_por_grupo_solo_con_muestras_completas():
    grupos = {"infraestructura": {"n": 1, "bytesRed": 40000, "bytesCache": 0, "duplicados": 0},
              "viento": {"n": 1, "bytesRed": 60000, "bytesCache": 0, "duplicados": 0}}
    completas = [muestra(100, bytes_red=100000, por_grupo=grupos) for _ in range(5)]
    # la incompleta trae bytes desaforados: no debe contaminar ninguna mediana
    incompleta = muestra(999, estado="timeout", bytes_red=999999, por_grupo={
        "infraestructura": {"n": 1, "bytesRed": 999999, "bytesCache": 0, "duplicados": 0}})
    res = mr.resumir_muestras(completas + [incompleta])
    pg = res["bytes"]["porGrupo"]
    assert pg["infraestructura"]["bytesRedMediana"] == 40000.0
    assert pg["infraestructura"]["bytesRedPeor"] == 40000.0
    assert pg["viento"]["bytesRedMediana"] == 60000.0
    assert pg["viento"]["nMediana"] == 1.0
    assert pg["teselasMapa"]["bytesRedMediana"] is None  # grupo sin pedidos en ninguna completa
    assert set(pg) == set(mr.GRUPOS_RECURSOS)
    assert res["bytes"]["bytesRedMediana"] == 100000  # el total no cambia


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


def test_informes_incluyen_el_desglose_por_grupo():
    grupos_base = {"viento": {"n": 1, "bytesRed": 60000, "bytesCache": 0, "duplicados": 0}}
    grupos_cand = {"viento": {"n": 1, "bytesRed": 90000, "bytesCache": 0, "duplicados": 0}}
    base = [muestra(100, bytes_red=60000, por_grupo=grupos_base) for _ in range(5)]
    candidata = [muestra(150, bytes_red=90000, por_grupo=grupos_cand) for _ in range(5)]
    datos = {"metadatos": {}, "comparacion": cr.comparar(base, candidata, 5)}
    texto = cr.informe_markdown(datos)
    assert "## Bytes por grupo de recurso" in texto
    assert "viento" in texto and "+50.0 %" in texto  # 60 000 → 90 000 B por la grilla
    # los grupos sin pedidos en ningún lado no generan filas
    assert "infraestructura" not in texto
    # el informe de un despliegue solo también desglosa
    datos_medicion = {"metadatos": {}, "muestras": base, "resumen": mr.resumir_por_escenario(base)}
    texto_medicion = mr.informe_markdown(datos_medicion)
    assert "## Bytes por grupo de recurso" in texto_medicion
    assert "viento" in texto_medicion and "60000" in texto_medicion


# ------------------------------------- REND-02 tanda 5: red quieta y grilla sintética

class SeguimientoFalso:
    """Seguimiento de mentira: solo los pedidos acumulados."""

    def __init__(self, pedidos):
        self.pedidos = pedidos


class SeguimientoConErrores(SeguimientoFalso):
    """Seguimiento de mentira que también registra los errores, como el real."""

    def __init__(self, pedidos):
        super().__init__(pedidos)
        self.errores = []

    def error(self, entrada):
        self.errores.append(entrada)


class PaginaQuieta:
    """Página de mentira: espera de verdad los ms que le piden (como page.wait_for_timeout)."""

    def wait_for_timeout(self, ms):
        time.sleep(ms / 1000)


def test_esperar_red_quieta_confirma_la_ventana_sin_pedidos():
    base = "https://brasa.example"
    pedidos = {
        "1": {"url": f"{base}/api/wind/grid", "fin": True, "fallo": ""},
        "2": {"url": f"{base}/web/data/infraestructura/indice.json", "fin": False, "fallo": ""},
    }
    seg = SeguimientoFalso(pedidos)
    # la infraestructura nunca termina: el tope vence sin confirmar la ventana (mejor esfuerzo)
    assert mr.esperar_red_quieta(seg, PaginaQuieta(), base, ("infraestructura", "viento"), 400,
                                ventana_ms=150) is False
    assert mr.pedidos_en_vuelo(seg.pedidos, base, ("infraestructura", "viento")) == \
        [f"{base}/web/data/infraestructura/indice.json"]
    # al terminar el pedido, la ventana de silencio se confirma dentro del tope
    pedidos["2"]["fin"] = True
    inicio = time.monotonic()
    assert mr.esperar_red_quieta(seg, PaginaQuieta(), base, ("infraestructura", "viento"), 2000,
                                ventana_ms=150) is True
    assert time.monotonic() - inicio >= 0.15
    # un fallo de red también saca el pedido de «en vuelo» (tesela abortada, 503, sin señal)
    pedidos["2"]["fin"] = False
    pedidos["2"]["fallo"] = "net::ERR_FAILED"
    assert mr.pedidos_en_vuelo(seg.pedidos, base, ("infraestructura", "viento")) == []
    # los pedidos de otros grupos no estorban: la red de infraestructura/viento está quieta
    pedidos["3"] = {"url": f"{base}/web/js/app.js", "fin": False, "fallo": ""}
    assert mr.esperar_red_quieta(seg, PaginaQuieta(), base, ("infraestructura", "viento"), 2000,
                                ventana_ms=150) is True


def test_calmar_red_de_ruta_solo_tras_util_y_con_tope_del_paso(monkeypatch):
    base = "https://brasa.example"
    seg = SeguimientoConErrores({})
    opciones = {"timeoutMs": 2000}
    inicio = time.monotonic()
    # sin redQuieta ni sin util: no espera nada ni devuelve confirmación
    assert mr.calmar_red_de_ruta({"listo": "#x"}, seg, PaginaQuieta(), base, "util", inicio, opciones) is None
    assert mr.calmar_red_de_ruta(mr.RUTAS["mapa-capas"], seg, PaginaQuieta(), base, "timeout", inicio, opciones) is None
    assert time.monotonic() - inicio < 0.1
    assert seg.errores == []
    # con util, delega en esperar_red_quieta con los grupos de la ruta y tope dentro del paso
    llamadas = []
    monkeypatch.setattr(mr, "esperar_red_quieta",
                        lambda seg_, page, base_, grupos, tope: llamadas.append((grupos, tope)) or True)
    assert mr.calmar_red_de_ruta(mr.RUTAS["mapa-capas"], seg, PaginaQuieta(), base, "util",
                                inicio, opciones, paso="directo") is True
    assert len(llamadas) == 1
    grupos, tope = llamadas[0]
    assert tuple(grupos) == ("infraestructura", "viento")
    assert 0 < tope <= opciones["timeoutMs"]
    assert seg.errores == []  # la red quieta confirmada no registra nada


def test_calmar_red_de_ruta_registra_el_timeout_de_red_quieta_como_medidor(monkeypatch):
    """El False de esperar_red_quieta no se ignora: timeout explícito, muestra incompleta,
    tiempo util del paso intacto (los bytes de esos grupos pueden estar truncados)."""
    base = "https://brasa.example"
    seg = SeguimientoConErrores({})
    opciones = {"timeoutMs": 2000}
    # el encuadre sí llega: el fallo acá es de la red, no del vuelo
    monkeypatch.setattr(mr, "esperar_encuadre", lambda *a, **k: True)
    monkeypatch.setattr(mr, "esperar_red_quieta", lambda *a, **k: False)
    inicio = time.monotonic()
    assert mr.calmar_red_de_ruta(mr.RUTAS["mapa-capas-santiago"], seg, PaginaQuieta(), base, "util",
                                inicio, opciones, paso="directo") is False
    assert len(seg.errores) == 1
    error = seg.errores[0]
    assert error["tipo"] == "redQuieta" and error["clase"] == "medidor" and error["paso"] == "directo"
    assert "truncados" in error["texto"] and "infraestructura" in error["texto"]
    # sin nombre de paso no registra (lo llama quien sabe qué paso medir)
    assert mr.calmar_red_de_ruta(mr.RUTAS["mapa-capas-santiago"], seg, PaginaQuieta(), base, "util",
                                inicio, opciones) is False
    assert len(seg.errores) == 1
    # la regla de medir_contexto: el error del medidor deja la muestra incompleta aunque el
    # paso haya llegado a util; el conteo invalida la comparación sin errores del producto
    paso_util = {"directo": {"estado": "util", "ms": 1200, "cls": 0.0, "tareasLargasMs": 5.0, "nTareasLargas": 1}}
    completas = [muestra(100) for _ in range(5)]
    truncada = muestra(1200, errores=[error])
    truncada["pasos"] = paso_util
    truncada["completa"] = all(p["estado"] == "util" for p in paso_util.values()) and \
        not any(e.get("clase") == "medidor" for e in truncada["errores"])
    assert truncada["completa"] is False
    res = mr.resumir_muestras(completas + [truncada])
    assert res["nCompletas"] == 5 and res["nIncompletas"] == 1
    assert res["errores"]["medidor"] == 1 and res["errores"]["producto"] == 0
    assert res["pasos"]["directo"]["medianaMs"] == 100  # el tiempo util no se contamina
    valida, motivos = mr.comparacion_valida(res, res, 5)
    assert not valida and any("incompletas" in m for m in motivos)
    assert mr.codigo_salida(res) == 0  # no es un error del producto: la comparación queda invalidada


class PaginaReloj:
    """Página de mentira con reloj propio: wait_for_timeout avanza el reloj en vez de dormir."""

    def __init__(self):
        self.reloj = 0.0
        self.esperas = []

    def wait_for_timeout(self, ms):
        self.esperas.append(ms)
        self.reloj += ms / 1000


def test_esperar_red_quieta_no_supera_el_tope_del_paso(monkeypatch):
    """Límite estricto: la encuesta de 100 ms se recorta a lo que queda del tope y la espera
    total nunca lo sobrepasa (antes la última encuesta dormía 100 ms completos)."""
    base = "https://brasa.example"
    pedidos = {"1": {"url": f"{base}/web/data/infraestructura/t/-34_-71.json", "fin": False, "fallo": ""}}
    seg = SeguimientoFalso(pedidos)
    pagina = PaginaReloj()
    monkeypatch.setattr(mr.time, "monotonic", lambda: pagina.reloj)
    # la tesela nunca termina: el tope vence exacto, con la última encuesta recortada
    assert mr.esperar_red_quieta(seg, pagina, base, ("infraestructura", "viento"), 350) is False
    assert pagina.esperas == [100, 100, 100, 50]
    assert pagina.reloj == pytest.approx(0.35)  # ni un milisegundo por encima del tope del paso
    # con la red quieta, la ventana de silencio se confirma dentro del tope
    pedidos["1"]["fin"] = True
    pagina_quieta = PaginaReloj()
    monkeypatch.setattr(mr.time, "monotonic", lambda: pagina_quieta.reloj)
    assert mr.esperar_red_quieta(seg, pagina_quieta, base, ("infraestructura", "viento"), 350,
                                ventana_ms=150) is True
    assert pagina_quieta.esperas == [100, 100]
    assert pagina_quieta.reloj == pytest.approx(0.2)


# ------------------------------------------- REND-02: espera verificable del encuadre (zoom + fin del vuelo)

def test_js_estado_encuadre_consulta_el_mapa_real_de_la_pagina():
    js = mr.js_estado_encuadre()
    # el módulo real de la app, el mismo que carga la vista del mapa
    assert "import('/web/js/map.js')" in js
    # la API pública de map.js y MapLibre: getMap, getZoom e isMoving
    assert "getMap()" in js and "getZoom()" in js and "isMoving()" in js
    # el import() dinámico de módulos propios ya lo usa la vista: la CSP de la app lo permite
    mapa_js = (RAIZ / "web" / "js" / "views" / "mapa.js").read_text(encoding="utf-8")
    assert "import('../viento.js')" in mapa_js
    # el veredicto lo decide Python (tolerancia en una sola fuente), el JS solo reporta
    assert "listo" not in js


def test_encuadre_listo_exige_zoom_con_tolerancia_y_fin_del_movimiento():
    encuadre = {"zoom": 11}
    assert mr.encuadre_listo({"zoom": 11.0, "moviendo": False}, encuadre) is True
    assert mr.encuadre_listo({"zoom": 11.0 - mr.ENCUADRE_TOLERANCIA_ZOOM, "moviendo": False},
                             encuadre) is True, "el borde de la tolerancia acepta"
    assert mr.encuadre_listo({"zoom": 10.4, "moviendo": False}, encuadre) is False, "zoom bajo la tolerancia"
    assert mr.encuadre_listo({"zoom": 12.0, "moviendo": True}, encuadre) is False, "zoom de más pero el vuelo sigue"
    assert mr.encuadre_listo({"razon": "sin-mapa"}, encuadre) is False
    assert mr.encuadre_listo({"razon": "sin-modulo"}, encuadre) is False
    assert mr.encuadre_listo(None, encuadre) is False


class PaginaEncuadre:
    """Página de mentira con reloj propio: evaluate devuelve los estados del mapa en orden."""

    def __init__(self, estados):
        self.estados = list(estados)
        self.reloj = 0.0
        self.esperas = []
        self.consultas = 0

    def evaluate(self, expr):
        self.consultas += 1
        return self.estados.pop(0) if len(self.estados) > 1 else self.estados[0]

    def wait_for_timeout(self, ms):
        self.esperas.append(ms)
        self.reloj += ms / 1000


def test_esperar_encuadre_confirma_el_fin_del_vuelo_antes_de_cerrar_bytes(monkeypatch):
    """El contenido usable llega mientras el vuelo animado sigue en curso: la confirmación
    exige zoom objetivo con tolerancia y mapa sin movimiento, nada antes."""
    encuadre = mr.RUTAS["mapa-capas-santiago"]["encuadre"]
    pagina = PaginaEncuadre([
        {"zoom": 4.6, "moviendo": True},   # arranque del vuelo
        {"zoom": 9.8, "moviendo": True},  # a medio camino
        {"zoom": 10.5, "moviendo": True},  # cerca, aún volando (y bajo la tolerancia)
        {"zoom": 11.0, "moviendo": False},  # vuelo terminado: recién ahora listo
    ])
    monkeypatch.setattr(mr.time, "monotonic", lambda: pagina.reloj)
    assert mr.esperar_encuadre(pagina, encuadre, 3000) is True
    assert pagina.consultas == 4
    assert pagina.esperas == [100, 100, 100]


def test_esperar_encuadre_no_supera_el_tope_del_paso(monkeypatch):
    encuadre = mr.RUTAS["mapa-capas-santiago"]["encuadre"]
    # sin mapa (o sin módulo): el tope vence exacto, con la última encuesta recortada
    pagina = PaginaEncuadre([{"razon": "sin-mapa"}])
    monkeypatch.setattr(mr.time, "monotonic", lambda: pagina.reloj)
    assert mr.esperar_encuadre(pagina, encuadre, 350) is False
    assert pagina.esperas == [100, 100, 100, 50]
    assert pagina.reloj == pytest.approx(0.35)  # ni un milisegundo por encima del tope
    assert pagina.consultas == 5


def test_calmar_red_de_ruta_espera_el_encuadre_antes_de_la_red_quieta(monkeypatch):
    """Sin el encuadre confirmado, la ventana de red quieta podría cerrar los bytes antes
    del pedido real de teselas: primero el vuelo, después la red."""
    base = "https://brasa.example"
    seg = SeguimientoConErrores({})
    opciones = {"timeoutMs": 5000}
    orden = []
    monkeypatch.setattr(mr, "esperar_encuadre",
                        lambda page, encuadre, tope: orden.append(("encuadre", encuadre, tope)) or True)
    monkeypatch.setattr(mr, "esperar_red_quieta",
                        lambda seg_, page, base_, grupos, tope: orden.append(("red", tuple(grupos), tope)) or True)
    inicio = time.monotonic()
    assert mr.calmar_red_de_ruta(mr.RUTAS["mapa-capas-santiago"], seg, PaginaQuieta(), base, "util",
                                inicio, opciones, paso="directo") is True
    assert [paso for paso, *_ in orden] == ["encuadre", "red"]
    assert orden[0][1] == {"zoom": 11}
    assert orden[1][1] == ("infraestructura", "viento")
    assert all(0 < p[2] <= opciones["timeoutMs"] for p in orden), "cada espera dentro del paso"
    assert seg.errores == []
    # mapa-capas (encuadre de país) no declara encuadre: solo espera la red quieta
    orden.clear()
    assert mr.calmar_red_de_ruta(mr.RUTAS["mapa-capas"], seg, PaginaQuieta(), base, "util",
                                inicio, opciones, paso="directo") is True
    assert [paso for paso, *_ in orden] == ["red"]


def test_calmar_red_de_ruta_registra_timeout_de_encuadre_como_medidor(monkeypatch):
    """El encuadre que no llega tampoco se ignora: timeout explícito del medidor, muestra
    incompleta, tiempo util intacto (los bytes del encuadre pueden estar truncados)."""
    base = "https://brasa.example"
    seg = SeguimientoConErrores({})
    opciones = {"timeoutMs": 2000}
    red = []
    monkeypatch.setattr(mr, "esperar_encuadre", lambda *a, **k: False)
    monkeypatch.setattr(mr, "esperar_red_quieta", lambda *a, **k: red.append(1) or True)
    inicio = time.monotonic()
    assert mr.calmar_red_de_ruta(mr.RUTAS["mapa-capas-santiago"], seg, PaginaQuieta(), base, "util",
                                inicio, opciones, paso="directo") is False
    assert red == [], "sin encuadre confirmado no se cierra la red: los bytes aún no se pidieron"
    assert len(seg.errores) == 1
    error = seg.errores[0]
    assert error["tipo"] == "encuadre" and error["clase"] == "medidor" and error["paso"] == "directo"
    assert "encuadre" in error["texto"] and "truncados" in error["texto"]
    # sin nombre de paso no registra (lo llama quien sabe qué paso medir)
    assert mr.calmar_red_de_ruta(mr.RUTAS["mapa-capas-santiago"], seg, PaginaQuieta(), base, "util",
                                inicio, opciones) is False
    assert len(seg.errores) == 1


class PaginaPreparar:
    """Página de mentira para preparar(): registra lo que se calienta, sin navegador."""

    def goto(self, url, wait_until=None, timeout=None):
        self.url = url

    def wait_for_function(self, criterio, timeout=None, arg=None):
        pass

    def wait_for_timeout(self, ms):
        pass


def test_preparar_calienta_tambien_el_encuadre_y_la_red_de_las_capas(monkeypatch):
    """La preparación de caché caliente/offline espera primero el encuadre y después la red
    quieta de las capas: sin eso mediría sin los bytes que aún viajaban y, en offline, la
    capa de infraestructura fallaría al montar (y su reversión reescribe el hash del criterio)."""
    base = "https://brasa.example"
    llamadas = []
    monkeypatch.setattr(mr, "esperar_encuadre",
                        lambda page, encuadre, tope: llamadas.append(("encuadre", encuadre, tope)) or True)
    monkeypatch.setattr(mr, "esperar_red_quieta",
                        lambda seg, page, b, grupos, tope: llamadas.append(("red", tuple(grupos), tope)) or True)
    opciones = {"timeoutMs": 5000}
    assert mr.preparar(object(), PaginaPreparar(), base, "mapa-capas-santiago", opciones,
                       SeguimientoFalso({})) is True
    assert [paso for paso, *_ in llamadas] == ["encuadre", "red"]
    assert llamadas[0][1] == {"zoom": 11}
    assert llamadas[1][1] == ("infraestructura", "viento")
    assert all(0 < p[2] <= opciones["timeoutMs"] for p in llamadas)
    # el encuadre que no llega no da por buena la preparación: se reporta, no se disimula
    monkeypatch.setattr(mr, "esperar_encuadre", lambda *a, **k: False)
    assert mr.preparar(object(), PaginaPreparar(), base, "mapa-capas-santiago", opciones,
                       SeguimientoFalso({})) is False
    # la red que no queda quieta tampoco
    monkeypatch.setattr(mr, "esperar_encuadre", lambda *a, **k: True)
    monkeypatch.setattr(mr, "esperar_red_quieta", lambda *a, **k: False)
    assert mr.preparar(object(), PaginaPreparar(), base, "mapa-capas-santiago", opciones,
                       SeguimientoFalso({})) is False
    # una ruta sin encuadre ni redQuieta no espera nada de esto en la preparación
    llamadas.clear()
    monkeypatch.setattr(mr, "esperar_encuadre", lambda *a, **k: llamadas.append(1) or True)
    monkeypatch.setattr(mr, "esperar_red_quieta", lambda *a, **k: llamadas.append(1) or True)
    assert mr.preparar(object(), PaginaPreparar(), base, "mapa", opciones, SeguimientoFalso({})) is True
    assert llamadas == []


def test_grilla_viento_sintetica_forma_exacta_y_representativa():
    from datetime import datetime, timezone

    from backend import windgrid

    import perf_server as ps

    ahora = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
    grilla = ps.grilla_viento_sintetica(ahora, windgrid)
    # forma exacta de backend/windgrid.py: grilla 1° regular completa con forma compacta
    assert grilla["computed_at"] == "2026-11-01T12:00:00Z"
    assert grilla["step"] == windgrid.STEP_DEG
    forma = windgrid.grid_shape(windgrid.grid_points(), windgrid.STEP_DEG)
    assert (grilla["lat0"], grilla["lon0"], grilla["rows"], grilla["cols"]) == forma
    assert grilla["source"] == windgrid.WIND_SOURCE
    n = len(grilla["points"])
    assert n == len(grilla["speed"]) == len(grilla["dir"]) == len(grilla["gust"])
    # pasos +0/+3/+6/+12 h completos: sin huecos, el tamaño medido es el real
    assert list(grilla["steps"]) == ["0", "3", "6", "12"]
    for paso in grilla["steps"].values():
        assert len(paso["speed"]) == n and paso["at"].endswith("Z")
        assert all(v is not None for v in paso["speed"]), "la grilla sintética no deja huecos"
    # subgrilla fina de 0,25° (misma forma, sin points) y sin NaN
    fina = grilla["fine"]
    assert fina["step"] == windgrid.FINE_STEP_DEG and fina["bbox"] == list(windgrid.FINE_BBOX)
    forma_fina = windgrid.grid_shape(windgrid.fine_grid_points(), windgrid.FINE_STEP_DEG)
    assert (fina["lat0"], fina["lon0"], fina["rows"], fina["cols"]) == forma_fina
    assert len(fina["speed"]) == fina["rows"] * fina["cols"]
    texto = json.dumps(grilla, allow_nan=False)
    # representativa: no la grilla mínima de 3 puntos que siembra el benchmark
    assert len(texto) > 20000, "el tamaño debe representar la grilla real, no tres puntos"
    # determinista: mismo epoch ⇒ misma grilla byte a byte (base y candidata idénticas)
    assert json.dumps(ps.grilla_viento_sintetica(ahora, windgrid), allow_nan=False) == texto


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

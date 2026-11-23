"""OFI-10: el MP2,5 medido por la estación SINCA más cercana a un lugar, sin clave.

`listadomapa2k19` se baja una vez, se destila y se comparte en caché 30 min; cada lugar
solo consulta cuál le queda más cerca. La hora de `tableRow` es hora de Chile y el valor
es preliminar (así lo declara el portal). Nada se inventa: sin estación a ≤60 km, lectura
atrasada o fuente caída, la respuesta es null.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
import pytest

from backend.providers import sinca
from tests.conftest import json_response

CHILE = ZoneInfo("America/Santiago")
NOW = datetime(2026, 10, 24, 4, 0, tzinfo=timezone.utc)   # 01:00 en Chile (UTC-3, DST)


@pytest.fixture(autouse=True)
def sin_respaldo_de_borde(monkeypatch):
    """Estas pruebas ejercitan la red simulada, sin proxy ni snapshot del entorno."""
    for key in ("SINCA_PROXY_URL", "SINCA_SNAPSHOT_PATH", "SINCA_MAX_SNAPSHOT_AGE_HOURS"):
        monkeypatch.delenv(key, raising=False)


def fresco_ahora() -> str:
    """Los tests del endpoint usan el reloj real del servidor: el momento se ancla al ahora
    de Chile para que la lectura siga «fresca» sin importar cuándo corra la suite."""
    return (datetime.now(CHILE) - timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M")


def estacion(lat, lon, nombre="Estación", momento=None, **extra):
    """Una estación del listadomapa2k19 con su resumen PM2,5 vigente en `tableRow`."""
    momento = momento or "2026-10-23 22:00"   # 01:00 UTC del 24-10: fresco para NOW
    pm25 = {"code": "PM25", "name": "MP-2,5",
            "tableRow": {"datetime": momento, "parameter": "MP 2,5",
                         "movil": "media móvil 24 h", "value": 5, "icap": 10,
                         "status": "bueno", "statuscode": 1}}
    return {"nombre": nombre, "key": "999", "latitud": lat, "longitud": lon,
            "comuna": extra.pop("comuna", "Ciudad"), "realtime": [pm25], **extra}


# --- parsing: solo estaciones con PM2,5 vigente; hora local de Chile → UTC ---

def test_latest_network_destila_una_fila_por_estacion():
    filas = sinca.latest_network([
        estacion(-33.44, -70.68, "Cerro Navia", comuna="Cerro Navia"),
        {"nombre": "Sin coords", "latitud": None, "longitud": None, "realtime": []},
        {"nombre": "Sin PM25", "latitud": -33.0, "longitud": -70.0,
         "realtime": [{"code": "PM10", "tableRow": {"value": 40}}]},
        {"nombre": "Sin valor", "latitud": -33.0, "longitud": -70.0,
         "realtime": [{"code": "PM25", "tableRow": {"value": None}}]},
    ])
    assert len(filas) == 1
    st = filas[0]
    assert st["name"] == "Cerro Navia" and st["comuna"] == "Cerro Navia"
    assert st["pm25"] == 5.0 and st["icap"] == 10 and st["status"] == "bueno"
    assert st["observed_at"] == "2026-10-24T01:00:00Z"   # 22:00 UTC-3 → UTC


def test_latest_network_respuesta_que_no_es_lista_sale_vacia():
    assert sinca.latest_network({"mensaje": "bloqueado"}) == []
    assert sinca.latest_network(None) == []


# --- nearest: distancia, frescura y un solo ganador ---

def test_nearest_elige_la_mas_cercana_con_lectura_fresca():
    stns = sinca.latest_network([
        estacion(-33.44, -70.68, "Cerro Navia"),
        estacion(-35.43, -71.67, "Talca"),
        estacion(-33.30, -70.55, "Atrasada", momento="2026-10-23 10:00"),  # >6 h
    ])
    cerca = sinca.nearest(stns, -33.45, -70.66, now=NOW)
    assert cerca["name"] == "Cerro Navia" and cerca["distance_km"] == pytest.approx(2.4, abs=0.6)
    assert cerca["observed_at"] == "2026-10-24T01:00:00Z" and cerca["pm25"] == 5.0


def test_nearest_sin_estacion_a_60_km_devuelve_none():
    stns = sinca.latest_network([estacion(-35.43, -71.67, "Talca")])
    assert sinca.nearest(stns, -33.45, -70.66, now=NOW) is None


def test_nearest_lectura_atrasada_devuelve_none():
    stns = sinca.latest_network([estacion(-33.44, -70.68, "Vieja", momento="2026-10-23 10:00")])
    assert sinca.nearest(stns, -33.45, -70.66, now=NOW) is None


# --- fetch_network: sin credenciales, errores explícitos ---

def test_fetch_network_destila_el_listado():
    async def run():
        async with httpx.AsyncClient(
                transport=httpx.MockTransport(lambda r: json_response([estacion(-33, -70)]))) as http:
            return await sinca.fetch_network(http)

    filas = asyncio.run(run())
    assert len(filas) == 1 and filas[0]["pm25"] == 5.0


def test_fetch_network_respuesta_no_lista_es_error():
    async def run():
        async with httpx.AsyncClient(
                transport=httpx.MockTransport(lambda r: json_response({"error": 1}))) as http:
            await sinca.fetch_network(http)

    with pytest.raises(sinca.SincaError):
        asyncio.run(run())


def test_fetch_network_portal_caido_es_error():
    async def run():
        async with httpx.AsyncClient(
                transport=httpx.MockTransport(lambda r: httpx.Response(503))) as http:
            await sinca.fetch_network(http)

    with pytest.raises(sinca.SincaError):
        asyncio.run(run())


# --- el endpoint ---

def test_endpoint_devuelve_la_estacion_mas_cercana(make_client, web):
    web.add(lambda r: "sinca.mma.gob.cl" in r.url.host,
            lambda r: json_response([
                estacion(-33.44, -70.68, "Cerro Navia", momento=fresco_ahora()),
                estacion(-35.43, -71.67, "Talca", momento=fresco_ahora()),
            ]))
    with make_client() as client:
        body = client.get("/api/climate/air?lat=-33.45&lon=-70.66").json()
    a = body["air"]
    assert a["name"] == "Cerro Navia" and a["distance_km"] < 60
    assert a["pm25"] == 5.0 and a["icap"] == 10 and a["observed_at"].endswith("Z")
    assert "SINCA" in body["source"] and "sinca.mma.gob.cl" in body["source_url"]
    assert "preliminar" in body["note"]


def test_endpoint_red_cacheada_sirve_a_otro_punto(make_client, web):
    llamadas = []
    momento = fresco_ahora()
    web.add(lambda r: "sinca.mma.gob.cl" in r.url.host,
            lambda r: (llamadas.append(r), json_response([
                estacion(-33.44, -70.68, "Cerro Navia", momento=momento),
                estacion(-33.65, -70.58, "Puente Alto", momento=momento),]))[1])
    with make_client() as client:
        a = client.get("/api/climate/air?lat=-33.45&lon=-70.66").json()
        b = client.get("/api/climate/air?lat=-33.64&lon=-70.57").json()
    assert len(llamadas) == 1, "la segunda consulta no vuelve a llamar a SINCA"
    assert a["air"]["name"] == "Cerro Navia" and b["air"]["name"] == "Puente Alto"


def test_endpoint_fuera_de_rango_devuelve_null(make_client, web):
    web.add(lambda r: "sinca.mma.gob.cl" in r.url.host,
            lambda r: json_response([estacion(-35.43, -71.67, "Talca", momento=fresco_ahora())]))
    with make_client() as client:
        body = client.get("/api/climate/air?lat=-33.45&lon=-70.66").json()
    assert body["air"] is None


def test_endpoint_fuente_caida_no_inventa(make_client, web):
    web.add(lambda r: "sinca.mma.gob.cl" in r.url.host, lambda r: httpx.Response(503))
    with make_client() as client:
        body = client.get("/api/climate/air?lat=-33.45&lon=-70.66").json()
    assert body["air"] is None and body["source"]


# --- OFI-35: lectura horaria, PM10 y CO ---

UG = "\u00b5g/m\u00b3"


def fila_dt(momento, valor, tooltip=""):
    """Fila de DataTable de Google Charts: [fecha-hora local, valor, color, tooltip]."""
    return {"c": [{"v": momento}, {"v": valor}, {"v": "#8bc34a"}, {"v": tooltip}]}


def realtime(code, filas=None, valor=None, momento="2026-10-23 22:00", unit=None):
    rt = {"code": code, "tableRow": {"datetime": momento, "value": valor, "icap": 10,
                                     "status": "bueno", "statuscode": 1}}
    if unit:
        rt["tableRow"]["unit"] = unit
    if filas is not None:
        rt["info"] = {"rows": filas}
    return rt


def estacion_multi(lat, lon, *rts, nombre="Multi"):
    return {"nombre": nombre, "key": "777", "latitud": lat, "longitud": lon,
            "comuna": "Ciudad", "realtime": list(rts)}


def test_info_rows_prefiere_el_tooltip_al_valor_desfasado_de_la_columna():
    """INV-26: c[1] llega corrido respecto del tooltip; el valor real es el del tooltip."""
    filas = [fila_dt("2026-10-23 21:00", 20, "9 " + UG), fila_dt("2026-10-23 22:00", 18, "8 " + UG)]
    st = sinca.latest_network([estacion_multi(-33.44, -70.68, realtime("PM25", filas, valor=5))])[0]
    assert st["pm25"] == 8.0 and st["mp25"] == 8.0
    assert st["pm25_period"] == "horario" and st["pm25_24h"] == 5.0
    assert st["observed_at"] == "2026-10-24T01:00:00Z"
    assert st["icap"] == 10 and st["status"] == "bueno"


def test_info_rows_sin_tooltip_usa_la_columna_y_acepta_filas_planas():
    filas = [["2026-10-23 21:00", 7, "#fff", ""], ["2026-10-23 22:00", "12,5", "#fff", None]]
    st = sinca.latest_network([estacion_multi(-33.44, -70.68, realtime("PM25", filas, valor=5))])[0]
    assert st["pm25"] == 12.5 and st["pm25_period"] == "horario"


def test_info_rows_tooltip_con_unidad_ajena_descarta_la_fila():
    filas = [fila_dt("2026-10-23 21:00", 9, "9 " + UG), fila_dt("2026-10-23 22:00", 99, "99 ppm")]
    st = sinca.latest_network([estacion_multi(-33.44, -70.68, realtime("PM25", filas, valor=5))])[0]
    assert st["pm25"] == 9.0 and st["observed_at"] == "2026-10-24T00:00:00Z"


def test_info_rows_sin_filas_validas_degrada_a_la_media_de_24h():
    filas = [fila_dt("sin fecha", 5, "5 " + UG), fila_dt("2026-10-23 22:00", -3, "-3 " + UG),
             fila_dt("2026-10-23 22:00", 99999, "99999 " + UG), fila_dt("2026-10-23 22:00", None, "")]
    st = sinca.latest_network([estacion_multi(-33.44, -70.68, realtime("PM25", filas, valor=5))])[0]
    assert st["pm25"] == 5.0 and st["pm25_period"] == "24h" and st["pm25_24h"] == 5.0
    assert st["observed_at"] == "2026-10-24T01:00:00Z"


def test_estacion_solo_con_table_row_conserva_el_comportamiento_antiguo():
    st = sinca.latest_network([estacion(-33.44, -70.68)])[0]
    assert st["pm25"] == 5.0 and st["pm25_period"] == "24h" and st["pm25_24h"] == 5.0
    assert st["pm10"] is None and st["co"] is None and st["pm10_unit"] is None and st["co_unit"] is None


def test_hora_local_usa_el_offset_real_de_cada_epoca():
    """Verano UTC-3 e invierno UTC-4: no hay offset fijo."""
    verano = sinca.latest_network([estacion_multi(
        -33.44, -70.68, realtime("PM25", [fila_dt("2026-01-15 12:00", 1, "1 " + UG)], valor=1))])[0]
    invierno = sinca.latest_network([estacion_multi(
        -33.44, -70.68, realtime("PM25", [fila_dt("2026-07-15 12:00", 1, "1 " + UG)], valor=1))])[0]
    assert verano["observed_at"] == "2026-01-15T15:00:00Z"
    assert invierno["observed_at"] == "2026-07-15T16:00:00Z"


def test_extrae_pm10_y_co_de_la_misma_estacion():
    st = sinca.latest_network([estacion_multi(
        -33.44, -70.68,
        realtime("PM25", [fila_dt("2026-10-23 22:00", 30, "30 " + UG)], valor=20),
        realtime("PM10", [fila_dt("2026-10-23 22:00", 41, "40,5 " + UG)], valor=35),
        realtime("0004", [fila_dt("2026-10-23 21:00", 9, "0,8 ppm")], valor=0.6, unit="ppm"),
    )])[0]
    assert st["pm10"] == 40.5 and st["pm10_unit"] == UG
    assert st["pm10_observed_at"] == "2026-10-24T01:00:00Z" and st["pm10_period"] == "horario"
    assert st["co"] == 0.8 and st["co_unit"] == "ppm"
    assert st["co_observed_at"] == "2026-10-24T00:00:00Z"


def test_co_en_ppb_se_convierte_a_ppm_y_nunca_se_mezclan():
    st = sinca.latest_network([estacion_multi(
        -33.44, -70.68, realtime("PM25", valor=20),
        realtime("CO", valor=350, unit="ppbv"))])[0]
    assert st["co"] == 0.35 and st["co_unit"] == "ppm" and st["co_period"] == "24h"
    mg = sinca.latest_network([estacion_multi(
        -33.44, -70.68, realtime("PM25", valor=20), realtime("CO", valor=1.3, unit="mg/m3"))])[0]
    assert mg["co"] == 1.3 and mg["co_unit"] == "mg/m\u00b3"


def test_co_sin_unidad_es_ambiguo_y_sale_null():
    st = sinca.latest_network([estacion_multi(
        -33.44, -70.68, realtime("PM25", valor=20), realtime("0004", valor=0.5))])[0]
    assert st["co"] is None and st["co_unit"] is None and st["pm25"] == 20.0


def test_co_y_pm10_fuera_de_rango_fisico_se_descartan():
    st = sinca.latest_network([estacion_multi(
        -33.44, -70.68, realtime("PM25", valor=20),
        realtime("PM10", valor=-1), realtime("CO", valor=900, unit="ppm"))])[0]
    assert st["pm10"] is None and st["co"] is None


def test_nearest_expone_los_campos_nuevos_y_la_senal():
    stns = sinca.latest_network([estacion_multi(
        -33.44, -70.68,
        realtime("PM25", [fila_dt("2026-10-23 22:00", 40, "40 " + UG)], valor=20),
        realtime("PM10", [fila_dt("2026-10-23 22:00", 50, "50 " + UG)], valor=35),
        realtime("0004", [fila_dt("2026-10-23 22:00", 1.4, "1,4 ppm")], valor=0.6, unit="ppm"))])
    a = sinca.nearest(stns, -33.45, -70.66, now=NOW)
    assert a["pm25"] == 40.0 and a["pm25_period"] == "horario" and a["pm25_24h"] == 20.0
    assert a["pm10"] == 50.0 and a["pm10_unit"] == UG and a["pm10_observed_at"] == "2026-10-24T01:00:00Z"
    assert a["co"] == 1.4 and a["co_unit"] == "ppm" and a["co_observed_at"] == "2026-10-24T01:00:00Z"
    assert a["signal"] == "humo" and a["preliminar"] is True
    for campo in ("name", "code", "comuna", "distance_km", "lat", "lon", "observed_at", "icap", "status"):
        assert campo in a


def test_nearest_estacion_solo_pm25_deja_pm10_y_co_en_null():
    a = sinca.nearest(sinca.latest_network([estacion(-33.44, -70.68)]), -33.45, -70.66, now=NOW)
    assert a["pm10"] is None and a["pm10_unit"] is None and a["pm10_observed_at"] is None
    assert a["co"] is None and a["co_unit"] is None and a["co_observed_at"] is None
    assert a["signal"] is None and a["preliminar"] is True and a["pm25_period"] == "24h"


def test_nearest_descarta_pm10_y_co_vencidos_aunque_el_pm25_sea_fresco():
    stns = sinca.latest_network([estacion_multi(
        -33.44, -70.68,
        realtime("PM25", [fila_dt("2026-10-23 22:00", 30, "30 " + UG)], valor=20),
        realtime("PM10", [fila_dt("2026-10-23 12:00", 90, "90 " + UG)], valor=35),   # 15:00 UTC: >6 h
        realtime("CO", [fila_dt("2026-10-23 12:00", 2, "2 ppm")], valor=1, unit="ppm"))])
    a = sinca.nearest(stns, -33.45, -70.66, now=NOW)
    assert a["pm25"] == 30.0
    assert a["pm10"] is None and a["pm10_observed_at"] is None
    assert a["co"] is None and a["co_unit"] is None and a["signal"] is None


def test_nearest_no_cruza_pm10_de_24h_con_pm25_horario():
    stns = sinca.latest_network([estacion_multi(
        -33.44, -70.68,
        realtime("PM25", [fila_dt("2026-10-23 22:00", 40, "40 " + UG)], valor=20),
        realtime("PM10", valor=45))])
    a = sinca.nearest(stns, -33.45, -70.66, now=NOW)
    assert a["pm10"] == 45.0 and a["pm10_period"] == "24h" and a["signal"] is None


# --- clasificar_senal_aire ---

def test_senal_humo_por_cociente_o_por_co_alto():
    assert sinca.clasificar_senal_aire(40, 50, None, None) == "humo"          # 0,8 >= 0,65
    assert sinca.clasificar_senal_aire(30, 200, 1.0, "ppm") == "humo"          # CO alto
    assert sinca.clasificar_senal_aire(30, None, 1.15, "mg/m\u00b3") == "humo"
    assert sinca.clasificar_senal_aire(30, None, 0.99, "ppm") is None


def test_senal_polvo_y_mixto():
    assert sinca.clasificar_senal_aire(20, 100, 0.2, "ppm") == "polvo"         # 0,2 < 0,35
    assert sinca.clasificar_senal_aire(40, 100, 0.2, "ppm") == "mixto"         # 0,4
    assert sinca.clasificar_senal_aire(40, 100, 1.5, "ppm") == "humo"          # CO alto manda
    assert sinca.clasificar_senal_aire(20, 100, 1.5, "ppm") is None            # polvo exige CO no alto


def test_senal_sin_datos_suficientes_es_none():
    assert sinca.clasificar_senal_aire(None, 100, None, None) is None
    assert sinca.clasificar_senal_aire(30, 0, None, None) is None              # sin división por cero
    assert sinca.clasificar_senal_aire(30, None, 5.0, None) is None            # unidad de CO desconocida
    assert sinca.clasificar_senal_aire(30, None, 5.0, "ppb") is None
    assert sinca.clasificar_senal_aire(10, 20, None, None) is None


# --- parse_cgi_hourly ---

CGI = ("FECHA (YYMMDD);HORA (HHMM);Registros validados;Registros preliminares;"
       "Registros no validados;\n")


def test_parse_cgi_hourly_prioriza_validado_y_convierte_a_utc():
    r = sinca.parse_cgi_hourly(CGI + "261023;2100;12,5;;;\n261023;2200;12,5;14,2;16,0;\n")
    assert r == {"value": 12.5, "observed_at": "2026-10-24T01:00:00Z", "quality": "validado", "unit": UG}


def test_parse_cgi_hourly_preliminar_y_no_validado_con_comas_chilenas():
    prelim = sinca.parse_cgi_hourly(CGI + "261023;2200;;14,2;;\n")
    assert prelim["value"] == 14.2 and prelim["quality"] == "preliminar"
    nv = sinca.parse_cgi_hourly(CGI + "261023;2200;;14,2;;\n261023;2300;;;1.018,5;\n")
    assert nv["value"] == 1018.5 and nv["quality"] == "no_validado"
    assert nv["observed_at"] == "2026-10-24T02:00:00Z"


def test_parse_cgi_hourly_hora_2400_es_la_medianoche_siguiente():
    r = sinca.parse_cgi_hourly(CGI + "261023;2400;;;9,5;\n")
    assert r["observed_at"] == "2026-10-24T03:00:00Z"   # 00:00 del 24-10 en UTC-3


def test_parse_cgi_hourly_usa_el_offset_de_invierno():
    r = sinca.parse_cgi_hourly(CGI + "260715;1200;10;;;\n")
    assert r["observed_at"] == "2026-07-15T16:00:00Z"    # UTC-4


def test_parse_cgi_hourly_ignora_filas_invalidas_y_toma_la_ultima_valida():
    csv = (CGI + "261023;2100;8;;;\n261023;2200;-9999;;;\n261024;0100;;;;\n"
           "basura;xx;1;;;\n261023;2560;7;;;\n")
    r = sinca.parse_cgi_hourly(csv)
    assert r["value"] == 8.0 and r["observed_at"] == "2026-10-24T00:00:00Z"
    assert sinca.parse_cgi_hourly("") is None and sinca.parse_cgi_hourly(CGI) is None


def test_parse_cgi_hourly_convierte_ppb_a_ppm():
    r = sinca.parse_cgi_hourly(CGI + "261023;2200;350;;;\n", unit="ppb")
    assert r["value"] == 0.35 and r["unit"] == "ppm"
    assert sinca.parse_cgi_hourly(CGI + "261023;2200;1;;;\n", unit="furlongs") is None


# --- endpoint ---

def test_endpoint_horario_expone_campos_nuevos_y_nota(make_client, web):
    ahora = fresco_ahora()
    web.add(lambda r: "sinca.mma.gob.cl" in r.url.host,
            lambda r: json_response([estacion_multi(
                -33.44, -70.68,
                realtime("PM25", [fila_dt(ahora, 18, "8 " + UG)], valor=5, momento=ahora),
                realtime("PM10", [fila_dt(ahora, 30, "30 " + UG)], valor=20, momento=ahora))]))
    with make_client() as client:
        body = client.get("/api/climate/air?lat=-33.45&lon=-70.66").json()
    a = body["air"]
    assert a["pm25"] == 8.0 and a["pm25_period"] == "horario" and a["pm25_24h"] == 5.0
    assert a["pm10"] == 30.0 and a["pm10_unit"] == UG and a["co"] is None
    assert a["preliminar"] is True and a["signal"] is None
    assert "última hora" in body["note"] and "preliminar" in body["note"]


def test_endpoint_24h_aclara_la_media_movil_en_la_nota(make_client, web):
    web.add(lambda r: "sinca.mma.gob.cl" in r.url.host,
            lambda r: json_response([estacion(-33.44, -70.68, momento=fresco_ahora())]))
    with make_client() as client:
        body = client.get("/api/climate/air?lat=-33.45&lon=-70.66").json()
    assert body["air"]["pm25_period"] == "24h"
    assert "24 h" in body["note"] and "preliminar" in body["note"]


def test_tooltip_miles_chilenos_y_numero_sin_unidad_no_caen_a_columna_desfasada():
    st = sinca.latest_network([estacion_multi(
        -33.44, -70.68,
        realtime("PM25", [fila_dt("2026-10-23 22:00", 0, "1.018,5 " + UG)], valor=50),
        realtime("0004", [fila_dt("2026-10-23 22:00", 0, "1.200 ppb")], valor=1.0, unit="ppb"),
    )])[0]
    assert st["pm25"] == 1018.5
    assert st["co"] == 1.2 and st["co_unit"] == "ppm"
    st_sin_u = sinca.latest_network([estacion_multi(
        -33.44, -70.68,
        realtime("PM25", [fila_dt("2026-10-23 22:00", 18, "8")], valor=12),
    )])[0]
    assert st_sin_u["pm25"] == 8.0


def test_nearest_no_cruza_horas_distintas_ni_expone_24h_vencido_ni_falla_con_iso_naive():
    stns = sinca.latest_network([estacion_multi(
        -33.44, -70.68,
        realtime("PM25", [fila_dt("2026-10-23 22:00", 40, "40 " + UG)], valor=20, momento="2026-10-23 10:00"),
        realtime("PM10", [fila_dt("2026-10-23 18:00", 50, "50 " + UG)], valor=45, momento="2026-10-23 18:00"),
        realtime("0004", [fila_dt("2026-10-23 18:00", 2, "2 ppm")], valor=1, unit="ppm", momento="2026-10-23 18:00"),
    )])
    a = sinca.nearest(stns, -33.45, -70.66, now=NOW)
    assert a["pm25"] == 40.0 and a["pm25_period"] == "horario"
    assert a["pm25_24h"] is None and a["icap"] is None and a["status"] == ""
    assert a["signal"] is None  # PM10 y CO son de hace 4 h respecto de PM2,5
    # Snapshot con observed_at naive no debe lanzar TypeError en nearest().
    naive_st = sinca._normalizar_estacion_snapshot({
        "code": "N1", "name": "Naive", "comuna": "Santiago",
        "lat": -33.44, "lon": -70.68, "observed_at": "2026-10-24T01:00:00", "pm25": 15.0,
    })
    assert naive_st["observed_at"] == "2026-10-24T01:00:00Z"
    assert sinca.nearest([naive_st], -33.45, -70.66, now=NOW)["pm25"] == 15.0

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

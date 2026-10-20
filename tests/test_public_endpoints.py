"""QA-44: contrato de los endpoints públicos sin cobertura previa.

Cubre /api/weather, /api/locate, /api/priority-comunas y /api/nearby-services,
los endpoints que alimentan «Mi zona» y «Prepárate». Sin red: todo pasa por el
FakeWeb de conftest (httpx.MockTransport).
"""
from __future__ import annotations

import json

import httpx
import pytest

from backend.providers import overpass
from backend.settings import ROOT
from tests.conftest import json_response

OPEN_METEO_HOST = "api.open-meteo.com"
OVERPASS_HOST = "overpass-api.de"

CURRENT = {"temperature_2m": 21.5, "relative_humidity_2m": 38, "wind_speed_10m": 12.0}
CURRENT_UNITS = {"temperature_2m": "°C", "relative_humidity_2m": "%", "wind_speed_10m": "km/h"}

OVERPASS_BODY = {"elements": [
    {"type": "node", "id": 10, "lat": -35.41, "lon": -71.60,
     "tags": {"amenity": "hospital", "name": "Hospital de Talca"}},
    {"type": "way", "id": 20, "center": {"lat": -35.50, "lon": -71.70},
     "tags": {"emergency": "assembly_point"}},
]}


def _host(host: str):
    return lambda request: request.url.host == host


# /api/weather ----------------------------------------------------------------

def test_weather_devuelve_contrato_cuando_el_proveedor_responde(make_client, web):
    web.add(_host(OPEN_METEO_HOST), lambda r: json_response({"current": CURRENT, "current_units": CURRENT_UNITS}))
    with make_client() as app:
        r = app.get("/api/weather", params={"lat": -35.42, "lon": -71.60})
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "Open-Meteo"
    assert body["kind"] == "modelled_current_weather"
    assert body["coordinates"] == [-71.60, -35.42]
    assert body["data"] == CURRENT and body["units"] == CURRENT_UNITS


def test_weather_502_cuando_el_proveedor_falla(make_client, web):
    web.add(_host(OPEN_METEO_HOST), lambda r: httpx.Response(503))
    with make_client() as app:
        r = app.get("/api/weather", params={"lat": -35.42, "lon": -71.60})
    assert r.status_code == 502
    assert r.json()["detail"]


def test_weather_segunda_llamada_identica_sale_de_la_cache(make_client, web):
    web.add(_host(OPEN_METEO_HOST), lambda r: json_response({"current": CURRENT, "current_units": CURRENT_UNITS}))
    with make_client() as app:
        params = {"lat": -35.42, "lon": -71.60}
        first = app.get("/api/weather", params=params)
        second = app.get("/api/weather", params=params)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    al_proveedor = [r for r in web.requests if r.url.host == OPEN_METEO_HOST]
    assert len(al_proveedor) == 1, "la segunda llamada no debió llegar a Open-Meteo"


# /api/locate -----------------------------------------------------------------

def test_locate_devuelve_comuna_y_riesgo_en_punto_conocido(make_client):
    with make_client() as app:
        r = app.get("/api/locate", params={"lat": -35.4211, "lon": -71.6035})  # centro de Talca
    assert r.status_code == 200
    body = r.json()
    assert body["comuna"]["name"] == "Talca" and body["comuna"]["code"] == 7101
    assert "risk_today" in body  # None si hoy no hay pronóstico cargado


def test_locate_devuelve_comuna_nula_en_mitad_del_oceano(make_client):
    with make_client() as app:
        r = app.get("/api/locate", params={"lat": -35.0, "lon": -80.0})
    assert r.status_code == 200
    assert r.json()["comuna"] is None


@pytest.mark.parametrize("params", [{"lat": 999, "lon": -71.6}, {"lat": -35.4, "lon": 999}])
def test_locate_rechaza_coordenadas_fuera_de_rango(make_client, params):
    with make_client() as app:
        r = app.get("/api/locate", params=params)
    assert r.status_code == 422


# /api/priority-comunas --------------------------------------------------------

def test_priority_comunas_devuelve_el_archivo_publicado(make_client):
    esperado = json.loads((ROOT / "web" / "data" / "prioritarias.json").read_text(encoding="utf-8"))
    with make_client() as app:
        r = app.get("/api/priority-comunas")
    assert r.status_code == 200
    assert r.json() == esperado
    assert "comunas" in r.json()


@pytest.mark.xfail(reason="QA-44 hallazgo: sin el archivo el endpoint levanta FileNotFoundError y devuelve 500, "
                          "no 200 con lista vacía. Corregir en public.py requiere un ítem aparte.",
                   strict=False)
def test_priority_comunas_sin_archivo_responde_lista_vacia(make_client, monkeypatch, tmp_path):
    (tmp_path / "web" / "data").mkdir(parents=True)  # árbol sin prioritarias.json
    monkeypatch.setattr("backend.settings.ROOT", tmp_path)
    with make_client() as app:
        r = app.get("/api/priority-comunas")
    assert r.status_code == 200 and r.json() == []


# /api/nearby-services ---------------------------------------------------------

def test_nearby_services_devuelve_items_ordenados_por_distancia(make_client, web):
    web.add(_host(OVERPASS_HOST), lambda r: json_response(OVERPASS_BODY))
    with make_client() as app:
        r = app.get("/api/nearby-services", params={"lat": -35.42, "lon": -71.60})
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "OpenStreetMap (Overpass)"
    assert len(body["items"]) >= 2
    distancias = [i["distance_km"] for i in body["items"]]
    assert distancias == sorted(distancias)
    assert all("direction" in i for i in body["items"])


def test_nearby_services_502_cuando_overpass_falla(make_client, web, monkeypatch):
    monkeypatch.setattr(overpass, "WAITS_S", (0, 0))
    web.add(_host(OVERPASS_HOST), lambda r: httpx.Response(503))
    with make_client() as app:
        r = app.get("/api/nearby-services", params={"lat": -35.42, "lon": -71.60})
    assert r.status_code == 502
    assert r.json()["detail"]


def test_nearby_services_lat_fuera_de_rango_documenta_comportamiento_actual(make_client, web):
    """QA-44 hallazgo: lat/lon no tienen cotas (a diferencia de /api/weather y /api/locate).

    lat=999 no lo rechaza FastAPI: la consulta sale a Overpass y responde lo que
    el proveedor devuelva. Aquí Overpass contesta vacío y el endpoint responde 200.
    """
    web.add(_host(OVERPASS_HOST), lambda r: json_response({"elements": []}))
    with make_client() as app:
        r = app.get("/api/nearby-services", params={"lat": 999, "lon": -71.60})
    assert r.status_code == 200  # no hay 422: falta validación de rango
    assert r.json()["items"] == []

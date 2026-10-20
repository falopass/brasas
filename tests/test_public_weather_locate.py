"""QA-53: contrato de /api/weather y /api/locate, los dos públicos que faltaban.

/api/weather modela las condiciones actuales con Open-Meteo y las cachea 600 s;
/api/locate responde la comuna del territorio para un punto y su riesgo de hoy.
"""

from __future__ import annotations

import httpx

from backend.providers import weather
from tests.conftest import json_response

CURRENT = {"temperature_2m": 24.5, "relative_humidity_2m": 40, "wind_speed_10m": 12.0, "wind_gusts_10m": 30.0, "wind_direction_10m": 200}
UNITS = {"temperature_2m": "°C", "wind_speed_10m": "km/h"}

VINA = (-33.0245, -71.5518)  # Viña del Mar, comuna 5109
ARGENTINA = (-35.0, -60.0)  # fuera del territorio chileno


def es_open_meteo(request: httpx.Request) -> bool:
    return request.url.host == "api.open-meteo.com"


def test_weather_responde_con_el_contrato_documentado(make_client, web):
    web.add(es_open_meteo, lambda r: json_response({"current": CURRENT, "current_units": UNITS}))
    with make_client() as app:
        r = app.get("/api/weather", params={"lat": -35.4, "lon": -71.6})
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "Open-Meteo"
    assert body["kind"] == "modelled_current_weather"
    assert body["coordinates"] == [-71.6, -35.4], "el orden es [lon, lat]"
    assert body["data"] == CURRENT and body["units"] == UNITS


def test_weather_segunda_llamada_sale_de_la_cache(make_client, web):
    web.add(es_open_meteo, lambda r: json_response({"current": CURRENT, "current_units": UNITS}))
    with make_client() as app:
        params = {"lat": -35.4, "lon": -71.6}
        assert app.get("/api/weather", params=params).status_code == 200
        assert app.get("/api/weather", params=params).status_code == 200
    llamadas = [r for r in web.requests if es_open_meteo(r)]
    assert len(llamadas) == 1, "la segunda respuesta la sirvió la caché, no el proveedor"


def test_weather_502_cuando_el_proveedor_falla(make_client, web):
    web.add(es_open_meteo, lambda r: httpx.Response(500))
    with make_client() as app:
        r = app.get("/api/weather", params={"lat": -35.4, "lon": -71.6})
    assert r.status_code == 502


def test_weather_rechaza_coordenadas_fuera_de_rango(make_client):
    with make_client() as app:
        assert app.get("/api/weather", params={"lat": 91, "lon": 0}).status_code == 422
        assert app.get("/api/weather", params={"lat": 0, "lon": -181}).status_code == 422


def test_locate_devuelve_la_comuna_y_su_riesgo_de_hoy(make_client):
    with make_client() as app:
        svc = app.app.state.services
        today = weather._today().isoformat()
        svc.db.execute(
            "INSERT INTO risk_daily(comuna_code, date, level, score, hours_3of3, hours_2of3, "
            "tmax, rhmin, windmax, gustmax, computed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (5109, today, "alto", 80, 0, 1, 33.0, 20.0, 35.0, 50.0, f"{today}T00:00:00Z"),
        )
        r = app.get("/api/locate", params={"lat": VINA[0], "lon": VINA[1]})
    assert r.status_code == 200
    body = r.json()
    assert body["comuna"]["code"] == 5109 and body["comuna"]["name"] == "Viña del Mar"
    assert body["risk_today"]["level"] == "alto" and body["risk_today"]["score"] == 80


def test_locate_sin_fila_de_hoy_reporta_riesgo_nulo(make_client):
    with make_client() as app:
        r = app.get("/api/locate", params={"lat": VINA[0], "lon": VINA[1]})
    assert r.status_code == 200
    body = r.json()
    assert body["comuna"]["code"] == 5109 and body["risk_today"] is None


def test_locate_fuera_de_chile_no_inventa_comuna(make_client):
    with make_client() as app:
        r = app.get("/api/locate", params={"lat": ARGENTINA[0], "lon": ARGENTINA[1]})
    assert r.status_code == 200 and r.json() == {"comuna": None}


def test_locate_rechaza_coordenadas_fuera_de_rango(make_client):
    with make_client() as app:
        assert app.get("/api/locate", params={"lat": -91, "lon": 0}).status_code == 422
        assert app.get("/api/locate", params={"lat": 0, "lon": 181}).status_code == 422

"""AGUA-05: pronóstico de humo (PM2,5/PM10) vía Open-Meteo Air Quality en `GET /api/air`.

El fixture replica la respuesta real del endpoint (consultada el 19-10-2026): `hourly.time`
con horas locales «AAAA-MM-DDTHH:MM» y `pm2_5`/`pm10` en µg/m³, que pueden venir en null.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import httpx
import pytest

from backend.providers import air, weather
from tests.conftest import json_response


def _payload(times, pm25, pm10):
    return {
        "latitude": -35.4,
        "longitude": -71.65,
        "timezone": "America/Santiago",
        "hourly_units": {"time": "iso8601", "pm2_5": "µg/m³", "pm10": "µg/m³"},
        "hourly": {"time": times, "pm2_5": pm25, "pm10": pm10},
    }


def _series(hours=48, start=None):
    """Serie realista: 2 días de horas con valores ascendentes, centrada en «ahora»."""
    start = start or (datetime.now(weather.CHILE_TZ).replace(minute=0, second=0, microsecond=0, tzinfo=None) - timedelta(hours=6))
    times, pm25, pm10 = [], [], []
    for i in range(hours):
        times.append((start + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M"))
        pm25.append(10.0 + i)
        pm10.append(15.0 + i)
    return _payload(times, pm25, pm10)


def _http(payload):
    return httpx.AsyncClient(transport=httpx.MockTransport(lambda r: json_response(payload)))


def test_hourly_normaliza_la_serie():
    payload = _series(hours=4)
    payload["hourly"]["pm2_5"][2] = None  # un valor ausente queda None, nunca 0
    payload["hourly"]["pm10"][2] = None

    async def run():
        async with _http(payload) as client:
            return await air.hourly(client, -35.4, -71.65)

    series = asyncio.run(run())
    assert series[0] == {"t": payload["hourly"]["time"][0], "pm2_5": 10.0, "pm10": 15.0}
    assert series[2] == {"t": payload["hourly"]["time"][2], "pm2_5": None, "pm10": None}
    assert len(series) == 4


def test_hourly_sin_serie_es_error():
    async def run():
        async with _http({"hourly": {"time": []}}) as client:
            await air.hourly(client, -35.4, -71.65)

    with pytest.raises(air.AirError):
        asyncio.run(run())


def test_next_24h_recorta_desde_la_hora_actual():
    series = [{"t": t, "pm2_5": p, "pm10": p10} for t, p, p10 in zip(_series()["hourly"]["time"], range(48), range(48))]
    now = datetime.now(weather.CHILE_TZ)
    out = air.next_24h(series, now)
    assert len(out) == 24
    mark = now.replace(minute=0, second=0, microsecond=0, tzinfo=None)
    assert all(datetime.fromisoformat(r["t"]) >= mark for r in out)


def test_endpoint_devuelve_el_pronostico(make_client, web):
    web.add(lambda r: r.url.host == "air-quality-api.open-meteo.com", lambda r: json_response(_series()))
    with make_client() as client:
        res = client.get("/api/air?lat=-35.4266&lon=-71.6554")
    assert res.status_code == 200
    body = res.json()
    assert body["available"] is True and body["stamp"]
    assert body["source"] == "CAMS vía Open-Meteo" and body["license"] == "CC BY 4.0"
    assert 0 < len(body["hourly"]) <= 24
    assert {"t", "pm2_5", "pm10"} <= set(body["hourly"][0])


def test_endpoint_sin_proveedor_responde_available_false(make_client):
    # Sin ruta simulada, la web falsa responde 503: la API no inventa ni deja caer la vista.
    with make_client() as client:
        res = client.get("/api/air?lat=-35.4266&lon=-71.6554")
    assert res.status_code == 200
    body = res.json()
    assert body["available"] is False and body["stamp"]


def test_endpoint_cachea_por_punto(make_client, web):
    web.add(lambda r: r.url.host == "air-quality-api.open-meteo.com", lambda r: json_response(_series()))
    with make_client() as client:
        client.get("/api/air?lat=-35.4266&lon=-71.6554")
        client.get("/api/air?lat=-35.44&lon=-71.67")  # mismo punto redondeado a 0,05°
    air_calls = [r for r in web.requests if r.url.host == "air-quality-api.open-meteo.com"]
    assert len(air_calls) == 1


def test_endpoint_valida_lat_lon(make_client):
    with make_client() as client:
        assert client.get("/api/air?lat=99&lon=-71.6").status_code == 422
        assert client.get("/api/air?lon=-71.6").status_code == 422

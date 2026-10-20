"""AGUA-05: MP2,5 pronosticado (CAMS vía Open-Meteo Air Quality) en la ficha de comuna."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import httpx

from backend.providers import weather
from backend.risk import CHILE_TZ
from tests.conftest import json_response


def local_stamp(day_offset: int, hour: int = 12) -> str:
    """Una hora del día local de Chile (hoy + `day_offset`) expresada en UTC, como la devuelve la API."""
    local = datetime.now(CHILE_TZ).replace(hour=hour, minute=0, second=0, microsecond=0) + timedelta(days=day_offset)
    return local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M")


def series(*pairs: tuple) -> dict:
    """Serie ya normalizada por `air_quality` ({time, pm25}), para probar `air_daily_max`."""
    return {"time": [t for t, _ in pairs], "pm25": [v for _, v in pairs]}


def air_payload(*pairs: tuple) -> httpx.Response:
    """Respuesta cruda de la API: el campo se llama `pm2_5`, no `pm25`."""
    return json_response({"hourly": {"time": [t for t, _ in pairs], "pm2_5": [v for _, v in pairs]}})


def test_air_quality_pide_pm25_de_hoy_y_manana_en_utc():
    seen = []

    async def run():
        transport = httpx.MockTransport(
            lambda r: seen.append(r) or json_response({"hourly": {"time": ["2026-10-19T12:00"], "pm2_5": [12.3]}}))
        async with httpx.AsyncClient(transport=transport) as http:
            return await weather.air_quality(http, -35.4, -71.6)

    assert asyncio.run(run()) == {"time": ["2026-10-19T12:00"], "pm25": [12.3]}
    params = seen[0].url.params
    assert seen[0].url.host == "air-quality-api.open-meteo.com"
    assert params["hourly"] == "pm2_5" and params["forecast_days"] == "2" and params["timezone"] == "GMT"


def test_air_daily_max_agrupa_por_dia_local_no_utc():
    # El cruce de medianoche: las 02:30 UTC del 20 de octubre son las 23:30 del 19 en Chile (UTC-3).
    out = weather.air_daily_max(series(
        ("2026-10-19T10:00", 5.0),   # 07:00 Chile del 19
        ("2026-10-20T02:30", 18.0),  # 23:30 Chile del 19: sigue siendo «hoy»
        ("2026-10-20T04:00", 9.5),   # 01:00 Chile del 20
        ("2026-10-20T10:00", None),  # sin dato no mueve el máximo
    ))
    assert out == {"2026-10-19": 18.0, "2026-10-20": 9.5}


def test_risk_comuna_publica_el_aire(make_client, web):
    web.add(lambda r: "air-quality" in r.url.host,
            lambda r: air_payload((local_stamp(0, 9), 11.0), (local_stamp(0, 18), 22.5), (local_stamp(1), 8.0)))
    with make_client() as client:
        air = client.get("/api/risk/5109").json()["air"]
    assert air["pm25_today_max"] == 22.5 and air["pm25_tomorrow_max"] == 8.0
    assert air["unit"] == "µg/m³"
    assert air["source"]["name"] == "CAMS vía Open-Meteo" and air["source"]["url"]
    assert air["guideline"]["pm25_24h"] == 15
    assert air["fetched_at"]


def test_risk_comuna_sin_aire_cuando_el_proveedor_falla(make_client, monkeypatch):
    async def boom(client, lat, lon):
        raise weather.WeatherError("sin servicio")

    monkeypatch.setattr(weather, "air_quality", boom)
    with make_client() as client:
        response = client.get("/api/risk/5109")
    assert response.status_code == 200
    assert response.json()["air"] is None


def test_el_aire_se_cachea_tres_horas_por_comuna(make_client, web):
    calls = []
    web.add(lambda r: "air-quality" in r.url.host,
            lambda r: calls.append(r) or air_payload((local_stamp(0), 7.0)))
    with make_client() as client:
        first = client.get("/api/risk/5109").json()["air"]
        second = client.get("/api/risk/5109").json()["air"]
    assert len(calls) == 1 and first == second and first["pm25_today_max"] == 7.0

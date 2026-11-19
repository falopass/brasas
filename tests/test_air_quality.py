"""AGUA-05: aire pronosticado (CAMS vía Open-Meteo Air Quality) en la ficha de comuna."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import httpx
import pytest

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
    """Respuesta cruda de la API con las variables CAMS que pide `air_quality`."""
    times = [t for t, _ in pairs]
    pm25 = [v for _, v in pairs]
    return json_response({
        "hourly": {
            "time": times,
            "pm2_5": pm25,
            "pm10": [None if v is None else v + 5 for v in pm25],
            "carbon_monoxide": [None if v is None else v * 10 for v in pm25],
            "aerosol_optical_depth": [None if v is None else v / 100 for v in pm25],
            "dust": [None if v is None else v / 2 for v in pm25],
        }
    })


def test_air_quality_pide_variables_cams_global_de_hoy_y_manana_en_utc():
    seen = []

    async def run():
        transport = httpx.MockTransport(
            lambda r: seen.append(r) or json_response({"hourly": {
                "time": ["2026-10-19T12:00"],
                "pm2_5": [12.3], "pm10": [13.3], "carbon_monoxide": [123.0],
                "aerosol_optical_depth": [0.12], "dust": [1.5],
            }}))
        async with httpx.AsyncClient(transport=transport) as http:
            return await weather.air_quality(http, -35.4, -71.6)

    out = asyncio.run(run())
    assert out["pm25"] == [12.3] and out["pm10"] == [13.3] and out["co"] == [123.0]
    assert out["aod"] == [0.12] and out["dust"] == [1.5]
    params = seen[0].url.params
    assert seen[0].url.host == "air-quality-api.open-meteo.com"
    assert params["hourly"] == weather.AIR_VARS and params["forecast_days"] == "2"
    assert params["timezone"] == "GMT" and params["domains"] == "cams_global"


def test_air_daily_max_agrupa_por_dia_local_no_utc():
    # El cruce de medianoche: las 02:30 UTC del 20 de octubre son las 23:30 del 19 en Chile (UTC-3).
    out = weather.air_daily_max(series(
        ("2026-10-19T10:00", 5.0),   # 07:00 Chile del 19
        ("2026-10-20T02:30", 18.0),  # 23:30 Chile del 19: sigue siendo «hoy»
        ("2026-10-20T04:00", 9.5),   # 01:00 Chile del 20
        ("2026-10-20T10:00", None),  # sin dato no mueve el máximo
    ))
    assert out == {"2026-10-19": 18.0, "2026-10-20": 9.5}


def test_air_daily_max_acepta_otra_variable():
    out = weather.air_daily_max({"time": ["2026-10-19T10:00", "2026-10-20T10:00"], "pm10": [7.0, 9.0]}, "pm10")
    assert out == {"2026-10-19": 7.0, "2026-10-20": 9.0}


def test_risk_comuna_publica_el_aire(make_client, web):
    web.add(lambda r: "air-quality" in r.url.host,
            lambda r: air_payload((local_stamp(0, 9), 11.0), (local_stamp(0, 18), 22.5), (local_stamp(1), 8.0)))
    with make_client() as client:
        air = client.get("/api/risk/5109").json()["air"]
    assert air["pm25_today_max"] == 22.5 and air["pm25_tomorrow_max"] == 8.0
    assert air["pm10_today_max"] == 27.5 and air["pm10_tomorrow_max"] == 13.0
    assert air["co_today_max"] == 225.0 and air["co_tomorrow_max"] == 80.0
    assert air["aod_today_max"] == pytest.approx(0.225) and air["aod_tomorrow_max"] == pytest.approx(0.08)
    assert air["dust_today_max"] == 11.25 and air["dust_tomorrow_max"] == 4.0
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

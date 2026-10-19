"""RISK-14: el cupo diario de Open-Meteo se cuenta por familia y se publica en /api/status."""
from __future__ import annotations

import asyncio
from datetime import date

import httpx
import pytest

from backend.providers import weather
from tests.conftest import json_response


@pytest.fixture(autouse=True)
def _contador_limpio(monkeypatch):
    """El contador es estado global del proceso: cada prueba arranca en cero."""
    monkeypatch.setattr(weather, "_calls", {"since": None, "day": None, "calls": 0, "by_endpoint": {}})


def client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_cada_llamada_suma():
    async def run():
        async with client(lambda r: json_response({"current": {}, "current_units": {}})) as http:
            await weather.current(http, -35.4, -71.6)
            await weather.current(http, -35.4, -71.6)

    asyncio.run(run())
    c = weather.counts()
    assert c["calls"] == 2 and c["by_endpoint"] == {"forecast": 2}
    assert c["since"]


def test_familias_se_clasifican_por_la_url():
    assert weather._family(weather.FORECAST_URL) == "forecast"
    assert weather._family(weather.ARCHIVE_URL) == "archive"
    assert weather._family("https://air-quality-api.open-meteo.com/v1/air-quality") == "air-quality"
    assert weather._family("https://example.com/v1/otra-cosa") == "otras"

    async def run():
        async with client(lambda r: json_response({})) as http:
            await weather._get(http, weather.ARCHIVE_URL, {})
            await weather._get(http, "https://air-quality-api.open-meteo.com/v1/air-quality", {})
            await weather._get(http, "https://example.com/v1/otra-cosa", {})

    asyncio.run(run())
    c = weather.counts()
    assert c["calls"] == 3
    assert c["by_endpoint"] == {"archive": 1, "air-quality": 1, "otras": 1}


def test_reintentos_de_bulk_tambien_suman(monkeypatch):
    monkeypatch.setattr(weather, "FWI_RETRY_WAIT_S", 0)
    responses = iter([httpx.Response(429), json_response({"hourly": {}})])

    async def run():
        async with client(lambda r: next(responses)) as http:
            return await weather._bulk(http, weather.ARCHIVE_URL, {})

    asyncio.run(run())
    c = weather.counts()
    assert c["calls"] == 2 and c["by_endpoint"] == {"archive": 2}, "el 429 y el reintento son dos llamadas"


def test_el_contador_se_reinicia_al_cambiar_el_dia_en_chile(monkeypatch):
    async def llamar():
        async with client(lambda r: json_response({})) as http:
            await weather._get(http, weather.FORECAST_URL, {})

    monkeypatch.setattr(weather, "_today", lambda: date(2026, 10, 19))
    asyncio.run(llamar())
    asyncio.run(llamar())
    assert weather.counts()["calls"] == 2

    monkeypatch.setattr(weather, "_today", lambda: date(2026, 10, 20))
    asyncio.run(llamar())
    c = weather.counts()
    assert c["calls"] == 1 and c["by_endpoint"] == {"forecast": 1}, "al otro día la cuenta vuelve a cero"


def test_status_publica_el_contador(make_client):
    async def llamar():
        async with client(lambda r: json_response({"current": {}, "current_units": {}})) as http:
            await weather.current(http, -35.4, -71.6)

    with make_client() as app:
        asyncio.run(llamar())
        om = app.get("/api/status").json()["open_meteo"]
    assert om["calls"] == 1 and om["by_endpoint"] == {"forecast": 1} and om["since"]

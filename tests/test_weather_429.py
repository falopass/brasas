"""RISK-14: un 429 pasajero no tumba la corrida completa del riesgo.

La llamada por lotes (ciclo de riesgo, sin tope de tiempo) espera y reintenta; la consulta
puntual de una persona (una petición HTTP con 12 s de tope en `web/js/api.js`) falla rápido.
"""

from __future__ import annotations

import asyncio
from collections import Counter

import httpx
import pytest

from backend.providers import weather
from tests.conftest import json_response


@pytest.fixture(autouse=True)
def _contador_limpio(monkeypatch):
    """El contador de cupo es estado global del proceso: cada prueba arranca en cero."""
    monkeypatch.setattr(
        weather,
        "_calls",
        {"since": None, "day": None, "calls": 0, "locations": 0, "by_endpoint": {}, "by_endpoint_locations": {}, "rate_limited": 0},
    )


@pytest.fixture
def esperas(monkeypatch):
    """Registra las esperas de `_bulk` sin dormir de verdad."""
    registradas: list[float] = []

    async def dormir(seconds, *args, **kwargs):
        registradas.append(seconds)

    monkeypatch.setattr(weather.asyncio, "sleep", dormir)
    return registradas


def client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def respuesta(latitudes: list[str], longitudes: list[str]) -> httpx.Response:
    """Cada ubicación lleva su lat/lon como marca: permite comprobar orden y alineación."""
    return json_response([{"hourly": {"marca": f"{lat},{lon}"}} for lat, lon in zip(latitudes, longitudes)])


def lote_de(points: list[tuple[float, float]], request: httpx.Request) -> int:
    """Índice de lote a partir de la primera ubicación pedida."""
    lat = request.url.params["latitude"].split(",")[0]
    lon = request.url.params["longitude"].split(",")[0]
    return points.index((float(lat), float(lon))) // weather.BATCH_SIZE


def test_lote_con_429_espera_reintenta_y_conserva_el_orden(esperas):
    points = [(round(-30.0 - i * 0.01, 4), round(-71.0 - i * 0.01, 4)) for i in range(150)]
    intentos: Counter[int] = Counter()

    def handler(request):
        latitudes = request.url.params["latitude"].split(",")
        longitudes = request.url.params["longitude"].split(",")
        lote = lote_de(points, request)
        intentos[lote] += 1
        if lote == 1 and intentos[lote] == 1:
            return httpx.Response(429)
        return respuesta(latitudes, longitudes)

    async def run():
        async with client(handler) as http:
            return await weather.forecast_hourly(http, points)

    resultado = asyncio.run(run())
    assert len(resultado) == 150, "el lote que falló se reintenta, no se pierde"
    assert [item["marca"] for item in resultado] == [f"{lat:.4f},{lon:.4f}" for lat, lon in points], (
        "la salida sigue siendo paralela a points: el elemento i es el punto i"
    )
    assert intentos[1] == 2
    assert esperas, "el 429 esperó antes de reintentar"


@pytest.mark.parametrize("n", [1, weather.BATCH_SIZE])
def test_consulta_puntual_falla_rapido_sin_esperar(esperas, n):
    points = [(round(-35.4 - i * 0.01, 4), -71.6) for i in range(n)]

    def handler(request):
        return httpx.Response(429)

    async def run():
        async with client(handler) as http:
            await weather.forecast_hourly(http, points)

    with pytest.raises(weather.WeatherRateLimited):
        asyncio.run(run())
    assert esperas == [], "una petición de usuario no puede esperar 65 s"


def test_cuatro_429_en_un_lote_propagan_el_error(esperas):
    points = [(round(-30.0 - i * 0.01, 4), -71.0) for i in range(100)]
    intentos: Counter[int] = Counter()

    def handler(request):
        latitudes = request.url.params["latitude"].split(",")
        longitudes = request.url.params["longitude"].split(",")
        lote = lote_de(points, request)
        intentos[lote] += 1
        if lote == 1:
            return httpx.Response(429)
        return respuesta(latitudes, longitudes)

    async def run():
        async with client(handler) as http:
            await weather.forecast_hourly(http, points)

    with pytest.raises(weather.WeatherRateLimited):
        asyncio.run(run())
    assert intentos[1] == 4, "reintenta hasta 4 veces y después propaga"
    assert len(esperas) == 3, "espera entre intentos, no después del último"

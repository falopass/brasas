"""Contrato de los endpoints geo de los casos históricos (`/polar` y `/weather`).

Cubren el camino feliz y los errores de las rutas que alimentan los gráficos de la
vista Historia. Todo lo externo (NASA FIRMS, Open-Meteo) se simula con monkeypatch,
y `make_client` monta un `httpx.MockTransport`: estas pruebas no tocan la red.
"""
from __future__ import annotations

from backend.providers import firms, weather

POINTS = [
    {"lat": -33.01, "lon": -71.55, "acq_datetime": "2024-02-02T18:20:00Z", "frp": 12.3, "instrument": "VIIRS"},
    {"lat": -33.02, "lon": -71.56, "acq_datetime": "2024-02-02T19:00:00Z", "frp": 8.1, "instrument": "VIIRS"},
    {"lat": -33.03, "lon": -71.57, "acq_datetime": "2024-02-03T02:40:00Z", "frp": 21.7, "instrument": "MODIS"},
]

HOURLY = {"time": ["2024-02-02T00:00", "2024-02-02T01:00"], "temperature_2m": [18.4, 17.9], "wind_speed_10m": [9.2, 11.0]}


def test_geo_404s(make_client):
    with make_client() as client:
        assert client.get("/api/cases/nope/polar").status_code == 404
        assert client.post("/api/cases/nope/polar").status_code == 404
        assert client.get("/api/cases/nope/weather").status_code == 404


def test_polar_post_without_firms_key_returns_503_with_code(make_client):
    with make_client() as client:
        r = client.post("/api/cases/vina-del-mar-2024/polar")
        assert r.status_code == 503
        detail = r.json()["detail"]
        assert detail["code"] == "FIRMS_KEY_MISSING"


def test_polar_happy_path_and_cache(make_client, monkeypatch):
    calls = []

    async def fake_fetch(key, bbox, sources, days=1, start=None, end=None, client=None):
        calls.append({"key": key, "bbox": bbox, "sources": sources, "start": start, "end": end})
        return list(POINTS), ["aviso de prueba"]

    monkeypatch.setattr(firms, "fetch_hotspots", fake_fetch)
    with make_client(FIRMS_MAP_KEY="k-123") as client:
        r = client.post("/api/cases/vina-del-mar-2024/polar")
        assert r.status_code == 200
        assert r.json() == {"count": 3, "notices": ["aviso de prueba"]}
        assert len(calls) == 1 and calls[0]["key"] == "k-123"

        got = client.get("/api/cases/vina-del-mar-2024/polar")
        assert got.status_code == 200
        assert got.json() == {"points": POINTS}

        # Comportamiento real: el POST siempre vuelve a descargar, no mira la caché.
        r2 = client.post("/api/cases/vina-del-mar-2024/polar")
        assert r2.status_code == 200 and r2.json()["count"] == 3
        assert len(calls) == 2


def test_polar_upstream_error_returns_502(make_client, monkeypatch):
    async def broken(*args, **kwargs):
        raise firms.UpstreamError("FIRMS no respondió")

    monkeypatch.setattr(firms, "fetch_hotspots", broken)
    with make_client(FIRMS_MAP_KEY="k-123") as client:
        r = client.post("/api/cases/vina-del-mar-2024/polar")
        assert r.status_code == 502
        assert "FIRMS" in r.json()["detail"]
        # El fallo no deja nada cacheado.
        assert client.get("/api/cases/vina-del-mar-2024/polar").json() == {"points": []}


def test_weather_happy_path_and_cache(make_client, monkeypatch):
    calls = []

    async def fake_archive(client, lat, lon, start_date, end_date):
        calls.append({"lat": lat, "lon": lon, "start": start_date, "end": end_date})
        return dict(HOURLY)

    monkeypatch.setattr(weather, "archive_hourly", fake_archive)
    with make_client() as client:
        r = client.get("/api/cases/vina-del-mar-2024/weather")
        assert r.status_code == 200
        payload = r.json()
        assert payload["hourly"] == HOURLY
        assert payload["timezone"] == "UTC" and "ERA5" in payload["source"]
        assert len(calls) == 1

        # Segunda llamada: sale de la caché, sin volver al proveedor.
        r2 = client.get("/api/cases/vina-del-mar-2024/weather")
        assert r2.status_code == 200 and r2.json() == payload
        assert len(calls) == 1


def test_weather_upstream_error_returns_502(make_client, monkeypatch):
    async def broken(*args, **kwargs):
        raise weather.WeatherError("Open-Meteo caído")

    monkeypatch.setattr(weather, "archive_hourly", broken)
    with make_client() as client:
        r = client.get("/api/cases/vina-del-mar-2024/weather")
        assert r.status_code == 502
        assert r.json()["detail"]

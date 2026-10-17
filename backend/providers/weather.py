"""Open-Meteo: pronóstico horario (riesgo por comuna), condiciones actuales (alertas) y reanálisis ERA5 (casos)."""
from __future__ import annotations

from typing import Any

import httpx

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
HOURLY_VARS = "temperature_2m,relative_humidity_2m,wind_speed_10m,wind_gusts_10m,wind_direction_10m"
CURRENT_VARS = "temperature_2m,relative_humidity_2m,wind_speed_10m,wind_gusts_10m,wind_direction_10m"
BATCH_SIZE = 50


class WeatherError(Exception):
    pass


async def _get(client: httpx.AsyncClient, url: str, params: dict[str, Any]) -> Any:
    try:
        response = await client.get(url, params=params)
        response.raise_for_status()
        return response.json()
    except (httpx.RequestError, httpx.HTTPStatusError, ValueError) as exc:
        raise WeatherError(f"Open-Meteo no respondió ({type(exc).__name__}).") from exc


async def forecast_hourly(client: httpx.AsyncClient, points: list[tuple[float, float]], days: int = 7) -> list[dict[str, Any]]:
    """Pronóstico horario para muchos puntos (lat, lon), en lotes multi-ubicación.

    Devuelve una lista paralela a `points` con {time, temperature_2m, ...} en hora de Chile.
    """
    results: list[dict[str, Any]] = []
    for i in range(0, len(points), BATCH_SIZE):
        batch = points[i:i + BATCH_SIZE]
        data = await _get(client, FORECAST_URL, {
            "latitude": ",".join(f"{lat:.4f}" for lat, _ in batch),
            "longitude": ",".join(f"{lon:.4f}" for _, lon in batch),
            "hourly": HOURLY_VARS, "forecast_days": days, "timezone": "America/Santiago",
            "wind_speed_unit": "kmh",
        })
        items = data if isinstance(data, list) else [data]
        if len(items) != len(batch):
            raise WeatherError("Open-Meteo devolvió un número inesperado de ubicaciones.")
        results.extend(item.get("hourly", {}) for item in items)
    return results


async def current(client: httpx.AsyncClient, lat: float, lon: float) -> dict[str, Any]:
    data = await _get(client, FORECAST_URL, {
        "latitude": f"{lat:.4f}", "longitude": f"{lon:.4f}", "current": CURRENT_VARS,
        "timezone": "America/Santiago", "wind_speed_unit": "kmh",
    })
    return {"data": data.get("current", {}), "units": data.get("current_units", {})}


async def archive_hourly(client: httpx.AsyncClient, lat: float, lon: float, start_date: str, end_date: str) -> dict[str, Any]:
    """Reanálisis horario (ERA5 vía Open-Meteo) en UTC, para reconstrucciones históricas."""
    data = await _get(client, ARCHIVE_URL, {
        "latitude": f"{lat:.4f}", "longitude": f"{lon:.4f}", "start_date": start_date, "end_date": end_date,
        "hourly": HOURLY_VARS, "timezone": "GMT", "wind_speed_unit": "kmh",
    })
    return data.get("hourly", {})

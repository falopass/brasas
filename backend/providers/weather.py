"""Open-Meteo: pronóstico horario (riesgo por comuna), condiciones actuales (alertas) y reanálisis ERA5 (casos)."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
HOURLY_VARS = "temperature_2m,relative_humidity_2m,wind_speed_10m,wind_gusts_10m,wind_direction_10m"
CURRENT_VARS = "temperature_2m,relative_humidity_2m,wind_speed_10m,wind_gusts_10m,wind_direction_10m"
BATCH_SIZE = 50


class WeatherError(Exception):
    pass


class WeatherRateLimited(WeatherError):
    """Open-Meteo rechazó la petición por volumen (límite por minuto). Se puede reintentar."""


async def _get(client: httpx.AsyncClient, url: str, params: dict[str, Any]) -> Any:
    try:
        response = await client.get(url, params=params)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 429:
            raise WeatherRateLimited("Open-Meteo pidió esperar: límite por minuto.") from exc
        raise WeatherError(f"Open-Meteo no respondió ({type(exc).__name__}).") from exc
    except (httpx.RequestError, ValueError) as exc:
        raise WeatherError(f"Open-Meteo no respondió ({type(exc).__name__}).") from exc


async def forecast_hourly(client: httpx.AsyncClient, points: list[tuple[float, float]], days: int = 7) -> list[dict[str, Any]]:
    """Pronóstico horario para muchos puntos (lat, lon), en lotes multi-ubicación.

    Devuelve una lista paralela a `points` con {time, temperature_2m, ...}; `time` en UTC.
    """
    results: list[dict[str, Any]] = []
    for i in range(0, len(points), BATCH_SIZE):
        batch = points[i:i + BATCH_SIZE]
        data = await _get(client, FORECAST_URL, {
            "latitude": ",".join(f"{lat:.4f}" for lat, _ in batch),
            "longitude": ",".join(f"{lon:.4f}" for _, lon in batch),
            "hourly": HOURLY_VARS, "forecast_days": days, "timezone": "GMT",
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


FWI_ARCHIVE_DAYS = 60
FWI_VARS = "temperature_2m,relative_humidity_2m,wind_speed_10m,precipitation"
FWI_PAUSE_S = 4          # pausa entre lotes: el límite por minuto cuenta volumen, no peticiones
FWI_RETRY_WAIT_S = 65    # lo que pide Open-Meteo cuando responde 429


async def _bulk(client: httpx.AsyncClient, url: str, params: dict[str, Any], attempts: int = 3) -> Any:
    """Petición pesada (muchas ubicaciones × muchos días) con espera y reintento por límite."""
    for attempt in range(attempts):
        try:
            return await _get(client, url, params)
        except WeatherRateLimited:
            if attempt == attempts - 1:
                raise
            await asyncio.sleep(FWI_RETRY_WAIT_S)
    raise WeatherError("Open-Meteo no respondió.")


async def fwi_inputs(client: httpx.AsyncClient, points: list[tuple[float, float]], days: int = FWI_ARCHIVE_DAYS,
                     past_days: int = 7, forecast_days: int = 7) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Series horarias para el FWI en muchos puntos: (archivo de `days` días, pronóstico).

    Se piden en hora local de Chile, que es la que usa el sistema (observación de las 13 h). El
    pronóstico repite los últimos `past_days` días porque el archivo de reanálisis llega con retraso.

    El archivo de 60 días para 345 comunas pesa lo suficiente para pasar el límite por minuto de
    Open-Meteo: por eso los lotes van espaciados y, si aun así responde 429, se espera y se reintenta.
    """
    today = datetime.now(ZoneInfo("America/Santiago")).date()
    archive_from = (today - timedelta(days=days)).isoformat()
    out: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for index, i in enumerate(range(0, len(points), BATCH_SIZE)):
        if index:
            await asyncio.sleep(FWI_PAUSE_S)
        batch = points[i:i + BATCH_SIZE]
        shared = {"latitude": ",".join(f"{lat:.4f}" for lat, _ in batch),
                  "longitude": ",".join(f"{lon:.4f}" for _, lon in batch),
                  "hourly": FWI_VARS, "timezone": "America/Santiago", "wind_speed_unit": "kmh"}
        archive = await _bulk(client, ARCHIVE_URL, {**shared, "start_date": archive_from, "end_date": today.isoformat()})
        forecast = await _bulk(client, FORECAST_URL, {**shared, "past_days": past_days, "forecast_days": forecast_days})
        for a, f in zip(_items(archive, batch), _items(forecast, batch)):
            out.append((a.get("hourly", {}), f.get("hourly", {})))
    return out


def _items(data: Any, batch: list[tuple[float, float]]) -> list[dict[str, Any]]:
    items = data if isinstance(data, list) else [data]
    if len(items) != len(batch):
        raise WeatherError("Open-Meteo devolvió un número inesperado de ubicaciones.")
    return items

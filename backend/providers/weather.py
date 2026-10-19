"""Open-Meteo: pronóstico horario (riesgo por comuna), condiciones actuales (alertas) y reanálisis ERA5 (casos)."""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
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


FWI_VARS = "temperature_2m,relative_humidity_2m,wind_speed_10m,precipitation"
FWI_PAUSE_S = 4          # pausa entre peticiones: el límite por minuto cuenta volumen, no peticiones
FWI_RETRY_WAIT_S = 65    # lo que pide Open-Meteo cuando responde 429
FWI_SEASON_START = (6, 1)  # la temporada «en curso» empieza el 1 de junio, como en rain_season


def _season_start(today: date) -> date:
    """El 1 de junio más reciente: inicio de la temporada a la que pertenece `today`."""
    year = today.year if (today.month, today.day) >= FWI_SEASON_START else today.year - 1
    return date(year, *FWI_SEASON_START)


def _month_ranges(start: date, end: date) -> list[tuple[date, date]]:
    """Trocea [start, end] en meses naturales, para repartir el volumen de cada petición."""
    ranges = []
    month = start.replace(day=1)
    while month <= end:
        nxt = (month.replace(day=28) + timedelta(days=7)).replace(day=1)
        ranges.append((max(start, month), min(end, nxt - timedelta(days=1))))
        month = nxt
    return ranges


async def _bulk(client: httpx.AsyncClient, url: str, params: dict[str, Any], attempts: int = 4) -> Any:
    """Petición pesada (muchas ubicaciones × muchos días) con espera y reintento por límite.

    El límite por minuto se gasta por volumen, no por número de peticiones: una respuesta 429 no
    significa que la petición esté mal, sino que hay que esperar a que se reponga el cupo.
    """
    for attempt in range(attempts):
        try:
            return await _get(client, url, params)
        except WeatherRateLimited:
            if attempt == attempts - 1:
                raise
            await asyncio.sleep(FWI_RETRY_WAIT_S * (attempt + 1))
    raise WeatherError("Open-Meteo no respondió.")


async def fwi_inputs(client: httpx.AsyncClient, points: list[tuple[float, float]],
                     past_days: int = 7, forecast_days: int = 7) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Series horarias para el FWI en muchos puntos: (archivo desde el 1 de junio, pronóstico).

    Se piden en hora local de Chile, que es la que usa el sistema (observación de las 13 h). El
    pronóstico repite los últimos `past_days` días porque el archivo de reanálisis llega con retraso.

    El archivo cubre la temporada completa en curso (desde el 1 de junio, convenio de `rain_season`)
    y no una ventana fija de días: el DC (la sequía profunda) tiene memoria de meses y arrancarlo
    en el valor de primavera canadiense a mitad de temporada la subestima justo en verano. Los días
    anteriores a hoy solo alimentan esa memoria recursiva; quien guarda la serie los descarta.

    En enero la ventana son ~7,5 meses × 345 comunas, así que el archivo se pide troceado por meses
    con la misma pausa entre peticiones, para repartir el volumen por minuto que limita Open-Meteo;
    si aun así responde 429, `_bulk` espera y reintenta.
    """
    today = datetime.now(ZoneInfo("America/Santiago")).date()
    archive_from = _season_start(today)
    out: list[tuple[dict[str, Any], dict[str, Any]]] = []
    first = True
    for i in range(0, len(points), BATCH_SIZE):
        batch = points[i:i + BATCH_SIZE]
        shared = {"latitude": ",".join(f"{lat:.4f}" for lat, _ in batch),
                  "longitude": ",".join(f"{lon:.4f}" for _, lon in batch),
                  "hourly": FWI_VARS, "timezone": "America/Santiago", "wind_speed_unit": "kmh"}
        archive: list[dict[str, list]] = [{} for _ in batch]
        for start, end in _month_ranges(archive_from, today):
            if not first:
                await asyncio.sleep(FWI_PAUSE_S)
            first = False
            chunk = await _bulk(client, ARCHIVE_URL, {**shared, "start_date": start.isoformat(),
                                                      "end_date": end.isoformat()})
            for acc, item in zip(archive, _items(chunk, batch)):
                for key, values in item.get("hourly", {}).items():
                    if isinstance(values, list):
                        acc.setdefault(key, []).extend(values)
        await asyncio.sleep(FWI_PAUSE_S)
        forecast = await _bulk(client, FORECAST_URL, {**shared, "past_days": past_days, "forecast_days": forecast_days})
        for a, f in zip(archive, _items(forecast, batch)):
            out.append((a, f.get("hourly", {})))
    return out


def _items(data: Any, batch: list[tuple[float, float]]) -> list[dict[str, Any]]:
    items = data if isinstance(data, list) else [data]
    if len(items) != len(batch):
        raise WeatherError("Open-Meteo devolvió un número inesperado de ubicaciones.")
    return items


RAIN_DAILY = "precipitation_sum"


async def daily_rain(client: httpx.AsyncClient, points: list[tuple[float, float]], start_date: str | None = None,
                     end_date: str | None = None, past_days: int | None = None) -> list[dict[str, float]]:
    """Lluvia diaria en mm para muchos puntos: {«AAAA-MM-DD»: mm}.

    Con `past_days` usa el pronóstico, que trae también los últimos días ya medidos y tapa el retraso
    del archivo. Sin él, el archivo de reanálisis ERA5 entre dos fechas.
    """
    out: list[dict[str, float]] = []
    for i in range(0, len(points), BATCH_SIZE):
        batch = points[i:i + BATCH_SIZE]
        shared = {"latitude": ",".join(f"{lat:.4f}" for lat, _ in batch),
                  "longitude": ",".join(f"{lon:.4f}" for _, lon in batch),
                  "daily": RAIN_DAILY, "timezone": "America/Santiago"}
        if past_days is not None:
            data = await _bulk(client, FORECAST_URL, {**shared, "past_days": past_days, "forecast_days": 1})
        else:
            data = await _bulk(client, ARCHIVE_URL, {**shared, "start_date": start_date, "end_date": end_date})
        for item in _items(data, batch):
            daily = item.get("daily") or {}
            out.append({stamp: value for stamp, value in zip(daily.get("time") or [], daily.get(RAIN_DAILY) or [])})
    return out

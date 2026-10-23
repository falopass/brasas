"""Relieve por punto: Copernicus DEM GLO-90 (~90 m) servido por la API de elevación de Open-Meteo.

`api.open-meteo.com/v1/elevation` devuelve la altura en metros de una lista de puntos (hasta
100 por llamada). Cada ubicación descuenta el cupo diario de Open-Meteo igual que el
pronóstico, así que la consulta pasa por `weather._get`: comparte contador de llamadas,
timeouts y errores con el resto de Open-Meteo (en `by_endpoint` queda en la familia «otras»).

Con una grilla 3×3 alrededor del punto —paso de 90 m, la resolución del modelo— el método de
Horn entrega la pendiente en grados y la orientación de la ladera: el rumbo HACIA donde baja
el terreno, la convención que `fwi.propagation_scenario` espera en `aspect_deg` (él mismo le
suma 180° para empujar el escenario cuesta arriba). El relieve no cambia, así que el
resultado queda en la caché de la base por un año: una sola llamada por punto redondeado a
0,001° (~110 m).
"""

from __future__ import annotations

import math

import httpx

from backend.db import Database
from backend.providers import weather

ELEVATION_URL = "https://api.open-meteo.com/v1/elevation"
GRID_STEP_M = 90.0          # resolución del GLO-90: paso de la grilla de muestreo
M_PER_DEG_LAT = 111320.0    # metros por grado de latitud
CACHE_TTL_S = 86400 * 365   # el relieve no cambia: una sola llamada por punto


async def elevations(client: httpx.AsyncClient, points: list[tuple[float, float]]) -> list[float]:
    """Elevación en metros de cada punto, en el mismo orden (una ubicación de cupo por punto)."""
    data = await weather._get(
        client,
        ELEVATION_URL,
        {
            "latitude": ",".join(f"{lat:.4f}" for lat, _ in points),
            "longitude": ",".join(f"{lon:.4f}" for _, lon in points),
        },
    )
    z = data.get("elevation") if isinstance(data, dict) else None
    if not isinstance(z, list) or len(z) != len(points) or not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in z):
        raise weather.WeatherError("Open-Meteo devolvió una elevación inesperada.")
    return [float(v) for v in z]


def grid(lat: float, lon: float) -> list[tuple[float, float]]:
    """Grilla 3×3 centrada en (lat, lon) con paso de `GRID_STEP_M`, de NO a SE por filas."""
    dlat = GRID_STEP_M / M_PER_DEG_LAT
    dlon = GRID_STEP_M / (M_PER_DEG_LAT * math.cos(math.radians(lat)))
    return [
        (lat + dy * dlat, lon + dx * dlon)
        for dy in (1.0, 0.0, -1.0)  # la fila norte primero
        for dx in (-1.0, 0.0, 1.0)  # y dentro de ella, de oeste a este
    ]


def slope_aspect_from_grid(z: list[float], cell_m: float = GRID_STEP_M) -> tuple[float, float]:
    """Pendiente y orientación de la ladera por el método de Horn sobre la grilla de `grid`.

    `z` son las nueve elevaciones en metros (NO, N, NE, O, C, E, SO, S, SE) y `cell_m` el lado
    de la celda. Devuelve `(slope_deg, aspect_deg)`: la pendiente en grados (0-90) y el rumbo
    desde el norte geográfico HACIA donde baja el terreno —la convención de `aspect_deg` en
    `propagation_scenario`—. En una grilla plana devuelve (0.0, 0.0).
    """
    dzdx = ((z[2] + 2.0 * z[5] + z[8]) - (z[0] + 2.0 * z[3] + z[6])) / (8.0 * cell_m)
    dzdy = ((z[6] + 2.0 * z[7] + z[8]) - (z[0] + 2.0 * z[1] + z[2])) / (8.0 * cell_m)  # hacia el sur
    slope = math.degrees(math.atan(math.hypot(dzdx, dzdy)))
    aspect = math.degrees(math.atan2(-dzdx, dzdy)) % 360.0  # cuesta abajo, rumbo desde el norte
    return slope, aspect


def cache_key(lat: float, lon: float) -> str:
    """Clave de la caché permanente de relieve: el punto redondeado a 0,001° (~110 m)."""
    return f"slope:{round(lat, 3):.3f}:{round(lon, 3):.3f}"


async def slope_aspect(db: Database, client: httpx.AsyncClient, lat: float, lon: float) -> tuple[float, float] | None:
    """(pendiente en grados, orientación cuesta abajo en grados) del punto, o None si no hay dato.

    Consulta Open-Meteo solo si el punto redondeado a 0,001° no está en la caché de la base:
    cada lugar cuesta una sola llamada de nueve ubicaciones para siempre. Si la API no
    responde o devuelve algo inesperado devuelve None: el escenario sigue en terreno plano
    y lo declara, como hasta ahora.
    """
    cached = db.cache_get(cache_key(lat, lon))
    if cached:
        return (float(cached[0]), float(cached[1]))
    try:
        z = await elevations(client, grid(lat, lon))
    except weather.WeatherError:
        return None
    slope, aspect = slope_aspect_from_grid(z)
    result = (round(slope, 2), round(aspect, 1))
    db.cache_set(cache_key(lat, lon), list(result), CACHE_TTL_S)
    return result

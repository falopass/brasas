"""Grilla de viento a 10 m sobre Chile continental (RISK-07), precalculada desde Open-Meteo.

El mapa anima partículas sobre esta grilla: el backend la refresca cada 6 h dentro del
ciclo y la sirve ya armada, así que ninguna visita llama a Open-Meteo.

Presupuesto por refresco: la grilla 1° cubre el bbox continental (-75.8,-56.0,-66.4,-17.5)
con 380 celdas (10 columnas × 38 filas) → `weather.forecast_hourly` lota de a 50 →
8 llamadas y 380 ubicaciones,
≈1.520 ubicaciones por día con 4 refrescos. El cupo diario lo gobierna services:
`windgrid_cycle` solo pide si el cupo alcanza (cede ante pronóstico y FWI).
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from backend.geo import EXTRA_ZONES

STEP_DEG = 1.0          # decisión del lead: 1°, no 0,25°
REFRESH_S = 6 * 3600    # refresco dentro del ciclo, sin cron nuevo

CHILE_BBOX = EXTRA_ZONES["chile"]["bbox"]  # oeste, sur, este, norte


def grid_points() -> list[tuple[float, float]]:
    """Centros de celda de 1° que caen dentro del bbox de Chile continental."""
    west, south, east, north = CHILE_BBOX
    puntos = []
    # floor, no int(): con west -75,8 el int truncaba a -75 y perdía la columna -75,5.
    lat = math.floor(south) + STEP_DEG / 2
    while lat < north:
        lon = math.floor(west) + STEP_DEG / 2
        while lon < east:
            puntos.append((round(lat, 2), round(lon, 2)))
            lon += STEP_DEG
        lat += STEP_DEG
    return puntos


def necesita_refresco(computed_at: str | None, now: datetime) -> bool:
    """True si no hay grilla o la que hay ya pasó el período de refresco."""
    if not computed_at:
        return True
    try:
        return (now - datetime.fromisoformat(computed_at.replace("Z", "+00:00"))).total_seconds() >= REFRESH_S
    except (TypeError, ValueError):
        return True


def cabe_en_cupo(necesarias: int, cap: int, gastado: int) -> bool:
    """True si el cupo diario restante cubre las ubicaciones de un refresco."""
    return necesarias > 0 and gastado + necesarias <= cap


def _hora_mas_cercana(times: list[str], now: datetime) -> int:
    """Índice de la hora del pronóstico más cercana a `now` (los `time` de Open-Meteo son UTC)."""
    mejor, mejor_d = 0, None
    for i, t in enumerate(times):
        try:
            t0 = datetime.fromisoformat(t.replace("Z", "+00:00"))
            # Open-Meteo devuelve `time` naive (sin offset): se lee como UTC, igual que
            # weather.air_daily_max, nunca como hora local.
            if t0.tzinfo is None:
                t0 = t0.replace(tzinfo=timezone.utc)
            d = abs((t0 - now).total_seconds())
        except (TypeError, ValueError):
            continue
        if mejor_d is None or d < mejor_d:
            mejor, mejor_d = i, d
    return mejor


def build_grid(points: list[tuple[float, float]], rows: list[dict[str, Any]],
               now: datetime | None = None) -> dict[str, Any]:
    """Une las filas del pronóstico (paralelas a `points`) en la grilla compacta.

    Cada celda: velocidad en km/h y dirección en grados **de dónde viene** el viento,
    convención `wind_direction_10m` de Open-Meteo. Datos faltantes → null, nunca NaN.
    """
    now = now or datetime.now(timezone.utc)
    speed: list[float | None] = []
    direc: list[int | None] = []
    for row in rows or []:
        idx = _hora_mas_cercana(row.get("time") or [], now)
        try:
            v = row["wind_speed_10m"][idx]
            d = row["wind_direction_10m"][idx]
            speed.append(round(float(v), 1) if v is not None else None)
            direc.append(int(round(float(d))) % 360 if d is not None else None)
        except (KeyError, IndexError, TypeError, ValueError):
            speed.append(None)
            direc.append(None)
    return {
        "computed_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "step": STEP_DEG,
        "points": [[lat, lon] for lat, lon in points],
        "speed": speed,
        "dir": direc,
    }

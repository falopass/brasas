"""Grilla de viento a 10 m sobre Chile continental (RISK-07), precalculada desde Open-Meteo.

El mapa anima partículas sobre esta grilla: el backend la refresca cada 6 h dentro del
ciclo y la sirve ya armada, así que ninguna visita llama a Open-Meteo.

Además de la grilla de 1° (todo el país) lleva una subgrilla fina de 0,25° sobre la franja
centro-sur (Valparaíso a La Araucanía), ráfagas (`wind_gusts_10m`) y cuatro pasos horarios
(+0/+3/+6/+12 h). Ambas grillas son regulares: el cliente interpola en `O(1)` con
`lat0/lon0/step/rows/cols`, el índice de la celda `(r, c)` es `r * cols + c`.

Presupuesto por refresco: la grilla 1° cubre el bbox continental (-75.8,-56.0,-66.4,-17.5)
con 380 celdas (10 columnas × 38 filas, 8 llamadas) y la subgrilla fina de 0,25° suma
390 celdas (13 × 30, 8 llamadas) → hasta 770 ubicaciones (16 llamadas) por refresco,
≈3.080 ubicaciones por día con 4 refrescos cuando el cupo alcanza (o 380/≈1.520 si cede
la subgrilla fina). El cupo diario lo gobierna services: `windgrid_cycle` solo pide si el
cupo alcanza (cede ante pronóstico y FWI).
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any

from backend.geo import EXTRA_ZONES

STEP_DEG = 1.0          # decisión del lead: 1°, no 0,25°
REFRESH_S = 6 * 3600    # refresco dentro del ciclo, sin cron nuevo

CHILE_BBOX = EXTRA_ZONES["chile"]["bbox"]  # oeste, sur, este, norte

FINE_STEP_DEG = 0.25
FINE_BBOX = (-73.5, -39.5, -70.5, -32.25)  # oeste, sur, este, norte (EPSG:4326 · Valparaíso a La Araucanía)
FORECAST_STEPS_H = (0, 3, 6, 12)
# Un paso solo toma el dato si la hora del pronóstico queda a ≤ 90 min del instante pedido.
_MAX_DESFASE_S = 90 * 60

WIND_SOURCE = {
    "name": "Open-Meteo (ECMWF IFS 0,25°)",
    "url": "https://open-meteo.com/en/docs",
    "license": "CC BY 4.0 (uso no comercial)",
}


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


def fine_grid_points() -> list[tuple[float, float]]:
    """Nodos de la subgrilla de 0,25° sobre `FINE_BBOX`, bordes incluidos (30 filas × 13 columnas).

    Orden: latitud ascendente (exterior) y longitud ascendente (interior), así que el
    índice de `(fila, columna)` es `fila * columnas + columna`. Se indexa por entero
    y no por acumulación de flotantes para que no se arrastre el error.
    """
    west, south, east, north = FINE_BBOX
    rows = round((north - south) / FINE_STEP_DEG) + 1
    cols = round((east - west) / FINE_STEP_DEG) + 1
    return [
        (round(south + r * FINE_STEP_DEG, 2), round(west + c * FINE_STEP_DEG, 2))
        for r in range(rows)
        for c in range(cols)
    ]


def grid_shape(points: list[tuple[float, float]], step: float) -> tuple[float, float, int, int] | None:
    """`(lat0, lon0, filas, columnas)` si `points` es una grilla regular completa; si no, `None`.

    Regular: orden fila a fila (lat ascendente, lon ascendente), paso `step` y
    `filas * columnas == len(points)`. Un subconjunto o una sola fila/columna no sirve
    para interpolar, así que devuelve `None` y el cliente usa la lista `points`.
    """
    n = len(points)
    if n < 4 or step <= 0:
        return None
    tol = 1e-4
    lat0, lon0 = points[0]
    cols = 0
    while cols < n and abs(points[cols][0] - lat0) <= tol:
        cols += 1
    if cols < 2 or n % cols:
        return None
    rows = n // cols
    if rows < 2:
        return None
    for r in range(rows):
        for c in range(cols):
            lat, lon = points[r * cols + c]
            if abs(lat - (lat0 + r * step)) > tol or abs(lon - (lon0 + c * step)) > tol:
                return None
    return lat0, lon0, rows, cols


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


def _utc(t: Any) -> datetime | None:
    """Lee un `time` de Open-Meteo (naive = UTC) o devuelve None si no se puede."""
    try:
        t0 = datetime.fromisoformat(str(t).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return t0.replace(tzinfo=timezone.utc) if t0.tzinfo is None else t0


def _num(serie: Any, idx: int) -> float | None:
    """Valor finito de `serie[idx]` o None: faltante, fuera de rango o NaN nunca se inventan."""
    try:
        v = float(serie[idx])
    except (KeyError, IndexError, TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _paso(row: dict[str, Any], target: datetime) -> tuple[float | None, int | None, float | None, datetime | None]:
    """(velocidad km/h, dirección de dónde viene, ráfaga km/h, hora UTC válida) más cercana a `target`."""
    times = row.get("time") or []
    if not times:
        return None, None, None, None
    idx = _hora_mas_cercana(times, target)
    t0 = _utc(times[idx])
    if t0 is None or abs((t0 - target).total_seconds()) > _MAX_DESFASE_S:
        return None, None, None, None
    v = _num(row.get("wind_speed_10m"), idx)
    d = _num(row.get("wind_direction_10m"), idx)
    g = _num(row.get("wind_gusts_10m"), idx)
    return (
        round(v, 1) if v is not None else None,
        int(round(d)) % 360 if d is not None else None,
        round(g, 1) if g is not None else None,
        t0,
    )


def _series(rows: list[dict[str, Any]], now: datetime) -> dict[str, Any]:
    """Velocidad, dirección y ráfaga por celda para cada paso de `FORECAST_STEPS_H`."""
    steps: dict[str, Any] = {}
    for h in FORECAST_STEPS_H:
        target = now + timedelta(hours=h)
        vals = [_paso(row, target) for row in rows]
        valida = next((v[3] for v in vals if v[3] is not None), None)
        if valida is None:
            valida = (target.astimezone(timezone.utc) + timedelta(minutes=30)).replace(
                minute=0, second=0, microsecond=0,
            )
        steps[str(h)] = {
            "at": valida.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "speed": [v[0] for v in vals],
            "dir": [v[1] for v in vals],
            "gust": [v[2] for v in vals],
        }
    return steps


def build_fine_grid(points: list[tuple[float, float]], rows: list[dict[str, Any]],
                    now: datetime | None = None) -> dict[str, Any]:
    """Bloque compacto de la subgrilla de 0,25°: sin `points`, se indexa con `lat0/lon0/step`."""
    now = now or datetime.now(timezone.utc)
    steps = _series(rows or [], now)
    out: dict[str, Any] = {"step": FINE_STEP_DEG, "bbox": list(FINE_BBOX)}
    shape = grid_shape(points, FINE_STEP_DEG)
    if shape:
        out.update(lat0=shape[0], lon0=shape[1], rows=shape[2], cols=shape[3])
    out.update(speed=steps["0"]["speed"], dir=steps["0"]["dir"], gust=steps["0"]["gust"], steps=steps)
    return out


def build_grid(points: list[tuple[float, float]], rows: list[dict[str, Any]],
               now: datetime | None = None, *, step: float = STEP_DEG,
               fine: dict[str, Any] | None = None) -> dict[str, Any]:
    """Une las filas del pronóstico (paralelas a `points`) en la grilla compacta.

    Cada celda: velocidad y ráfaga en km/h y dirección en grados **de dónde viene** el
    viento, convención `wind_direction_10m` de Open-Meteo. Datos faltantes → null, nunca
    NaN. `speed`, `dir` y `gust` son el paso +0 h; `steps` trae +0/+3/+6/+12 h.
    """
    now = now or datetime.now(timezone.utc)
    steps = _series(rows or [], now)
    out: dict[str, Any] = {
        "computed_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "step": step,
        "points": [[lat, lon] for lat, lon in points],
    }
    shape = grid_shape(points, step)
    if shape:
        out.update(lat0=shape[0], lon0=shape[1], rows=shape[2], cols=shape[3])
    out.update(speed=steps["0"]["speed"], dir=steps["0"]["dir"], gust=steps["0"]["gust"],
               source=WIND_SOURCE, steps=steps)
    if fine is not None:
        out["fine"] = fine
    return out

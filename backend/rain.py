"""Anomalía de lluvia de la temporada fría (junio a octubre) por comuna.

La idea que viene de la investigación (la «paradoja hidro-pirológica») es contraintuitiva: en la zona
central, un invierno **más lluvioso que lo normal** no baja el riesgo del verano siguiente, lo sube,
porque hace crecer más pasto y matorral, y ese combustible nuevo se seca en enero. Un invierno seco
deja menos combustible, pero el que hay se seca antes.

Por eso BRASA no dice «llovió mucho, estamos tranquilos»: dice cuánto se apartó la temporada de su
normal 1991-2020 y qué implica para el pasto que viene.

Se compara **la misma ventana de días**: la temporada en curso (1 de junio → hoy) contra el promedio
de esa misma ventana en 1991-2020. Comparar una temporada a medio terminar con una normal completa
haría ver sequía donde solo falta tiempo.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

SEASON_MONTHS = (6, 7, 8, 9, 10)
SEASON_START = (6, 1)
SEASON_END = (10, 31)

# Cortes del cociente lluvia/normal. El texto no juzga el riesgo de hoy: habla del combustible.
LEVELS = ("muy_seco", "seco", "normal", "humedo", "muy_humedo")
LEVEL_LABELS = {"muy_seco": "Muy por debajo de lo normal", "seco": "Por debajo de lo normal",
                "normal": "En torno a lo normal", "humedo": "Por encima de lo normal",
                "muy_humedo": "Muy por encima de lo normal"}
THRESHOLDS = ((0.5, "muy_seco"), (0.85, "seco"), (1.15, "normal"), (1.5, "humedo"))

# Claves «MM-DD» de un año no bisiesto, en orden: el índice de las listas de 365 valores
# del archivo versionado de normales (web/data/rain_normals.json, FIX-25).
DAY_KEYS = [(date(2021, 1, 1) + timedelta(days=i)).strftime("%m-%d") for i in range(365)]


def season_window(today: date) -> tuple[date, date]:
    """Ventana de la temporada: del 1 de junio a hoy, recortada al 31 de octubre.

    Antes de junio la temporada todavía no empezó: devuelve una ventana invertida
    (`end < start`, el fin es el día anterior al inicio) para que los guardias de la
    ingesta la traten como vacía. Una ventana de un solo día futuro hacía escribir
    `current_mm = 0` y publicar «100 % menos de lluvia» sobre días que aún no ocurren.
    """
    year = today.year
    start = date(year, *SEASON_START)
    end = min(today, date(year, *SEASON_END))
    return (start, end) if end >= start else (start, start - timedelta(days=1))


def level(ratio: float | None) -> str | None:
    """Nivel en palabras a partir del cociente lluvia/normal."""
    if ratio is None:
        return None
    for limit, name in THRESHOLDS:
        if ratio < limit:
            return name
    return "muy_humedo"


def build_normal(series: dict[str, float], year_from: int = 1991, year_to: int = 2020) -> dict[str, float]:
    """Promedio por día del año (clave «MM-DD») de una serie diaria de lluvia.

    `series` tiene claves «AAAA-MM-DD». Los días 29 de febrero se ignoran: comparar temporadas no
    los necesita y así todas las claves existen en todos los años.
    """
    totals: dict[str, list[float]] = {}
    for stamp, value in series.items():
        month_day = stamp[5:]
        if month_day == "02-29" or value is None:
            continue
        totals.setdefault(month_day, []).append(float(value))
    years = year_to - year_from + 1
    return {key: round(sum(values) / years, 3) for key, values in totals.items() if len(values) >= years // 2}


def window_normal(daily_normal: dict[str, float], start: date, end: date) -> float:
    """Lluvia normal acumulada en una ventana, a partir de los promedios diarios."""
    total = 0.0
    for month_day, value in daily_normal.items():
        month, day = int(month_day[:2]), int(month_day[3:])
        if (month, day) < (start.month, start.day) or (month, day) > (end.month, end.day):
            continue
        total += value
    return round(total, 1)


def window_sum(series: dict[str, float], start: date, end: date) -> float:
    """Lluvia caída en una ventana concreta (solo días con dato)."""
    total = 0.0
    for stamp, value in series.items():
        if value is None:
            continue
        moment = date.fromisoformat(stamp)
        if start <= moment <= end:
            total += float(value)
    return round(total, 1)


def ratio(current: float | None, normal: float | None) -> float | None:
    """Cuántas veces la lluvia normal. None si no hay base de comparación."""
    if current is None or not normal or normal <= 0:
        return None
    return round(current / normal, 3)


def evaluate(current: float | None, normal: float | None) -> dict[str, Any]:
    """Resultado con su nivel y una frase en palabras llanas. Sin datos no se inventa un nivel."""
    value = ratio(current, normal)
    name = level(value)
    percent = None if value is None else round((value - 1) * 100)
    return {"current_mm": current, "normal_mm": normal, "ratio": value, "percent": percent,
            "level": name, "label": LEVEL_LABELS.get(name) if name else None,
            "plain": plain_text(name, percent)}


def plain_text(name: str | None, percent: int | None) -> str:
    """Qué significa para el pasto que va a crecer y secarse en verano."""
    if name is None:
        return "Todavía no hay suficiente temporada de lluvias para compararla con lo normal."
    if name == "muy_seco":
        return f"Ha llovido un {abs(percent)} % menos que un año normal: habrá menos pasto nuevo, pero el que crezca se secará antes."
    if name == "seco":
        return f"Ha llovido un {abs(percent)} % menos que un año normal: menos combustible fino para el verano."
    if name == "normal":
        return "La lluvia va en torno a lo normal de los últimos 30 años."
    if name == "humedo":
        return f"Ha llovido un {percent} % más que un año normal: habrá más pasto, y ese pasto se secará en verano."
    return (f"Ha llovido un {percent} % más que un año normal: mucho pasto nuevo, que en verano será "
            "combustible fino en las laderas de la zona central.")


def load_normals_file(path: str | Path) -> dict[str, Any] | None:
    """Lee las normales versionadas (`web/data/rain_normals.json`, FIX-25).

    El archivo trae {generated_at, source, period, cells: {comuna_code: [365 mm]}} y sirve para
    repoblar `rain_normal` cuando se pierde `work.db`. Devuelve {"generated_at", "cells": {code:
    {"MM-DD": mm}}} o None si el archivo falta, está roto o no trae ninguna celda válida: una
    celda mala (largo distinto de 365 o valores no numéricos) se descarta sin invalidar a las demás.
    """
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    cells = data.get("cells") if isinstance(data, dict) else None
    if not isinstance(cells, dict):
        return None
    valid: dict[int, dict[str, float]] = {}
    for code, values in cells.items():
        if (not isinstance(values, list) or len(values) != len(DAY_KEYS)
                or any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in values)):
            continue
        try:
            key = int(code)
        except (TypeError, ValueError):
            continue
        valid[key] = dict(zip(DAY_KEYS, values))
    if not valid:
        return None
    return {"generated_at": str(data.get("generated_at") or ""), "cells": valid}

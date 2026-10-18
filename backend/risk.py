"""Índice diario 30-30-30 por comuna, combinado con el FWI.

La regla 30-30-30 (temperatura sobre 30 °C, humedad relativa bajo 30 % y viento sobre 30 km/h)
es la referencia que CONAF difunde para condiciones de propagación muy favorables.
BRASA la evalúa hora a hora sobre el pronóstico de Open-Meteo en el centro de cada comuna.

El 30-30-30 mira el día; el FWI (backend/fwi.py) mira además cuánto llevan secándose el pasto y
la hojarasca en las semanas previas. `combine` junta los dos en un solo nivel de condiciones, sin
que ninguno reemplace al otro: los dos se muestran por separado y el combinado se explica.

Es un indicador meteorológico de peligro, no la probabilidad de que ocurra un incendio.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

CHILE_TZ = ZoneInfo("America/Santiago")
T_LIMIT, RH_LIMIT, WIND_LIMIT = 30.0, 30.0, 30.0
LEVELS = ["bajo", "moderado", "alto", "extremo"]
LEVEL_LABELS = {"bajo": "Bajo", "moderado": "Moderado", "alto": "Alto", "extremo": "Extremo"}
RANK = {name: index for index, name in enumerate(LEVELS)}
CONCURRENCE = RANK["alto"]  # desde aquí dos índices que coinciden empeoran el cuadro


MIN_VALID_HOURS = 6  # horas con temperatura, humedad y viento para clasificar un día


def hour_flags(t: float | None, rh: float | None, wind: float | None) -> tuple[bool, bool, bool]:
    return (t is not None and t > T_LIMIT, rh is not None and rh < RH_LIMIT, wind is not None and wind > WIND_LIMIT)


def _clip(value: float) -> float:
    return max(0.0, min(1.0, value))


def hour_score(t: float | None, rh: float | None, wind: float | None) -> float:
    """Puntaje continuo 0-100: qué tan cerca está cada variable de su umbral (media geométrica suave)."""
    if t is None or rh is None or wind is None:
        return 0.0
    st = _clip((t - 15) / (T_LIMIT - 15))
    srh = _clip((70 - rh) / (70 - RH_LIMIT))
    sw = _clip(wind / WIND_LIMIT)
    return round(100 * (st * srh * max(sw, 0.25)) ** (1 / 3), 1)


def classify_day(hours_3: int, hours_2: int, tmax: float | None, rhmin: float | None, max_score: float) -> str:
    if hours_3 >= 1:
        return "extremo"
    if hours_2 >= 3 or max_score >= 80:
        return "alto"
    if hours_2 >= 1 or max_score >= 55 or ((tmax or 0) >= 27 and (rhmin or 100) <= 40):
        return "moderado"
    return "bajo"


def combine(level_3030: str, fwi_level: str | None) -> tuple[str, list[str]]:
    """Nivel de condiciones del día: 30-30-30 y FWI juntos, con la razón de cada uno.

    Regla explícita y conservadora, porque los dos índices miden cosas distintas del mismo día:

    1. Manda el más alto. El 30-30-30 describe el día (calor, sequedad, viento); el FWI describe
       además cuánto llevan secándose el pasto y la hojarasca. Ninguno cancela al otro.
    2. Si **los dos** llegan a «alto» o más, sube un paso. Son medidas independientes que
       coinciden: eso es peor que una sola en ese mismo nivel.
    3. Nunca pasa de «extremo».

    Devuelve el nivel y las razones en palabras para mostrarlas junto al número, no en su lugar.
    """
    base = RANK.get(level_3030, 0)
    reasons = [f"30-30-30: {LEVEL_LABELS.get(level_3030, 'sin dato')}"]
    if fwi_level not in RANK:
        reasons.append("FWI: sin dato para hoy")
        return LEVELS[base], reasons
    top = max(base, RANK[fwi_level])
    reasons.append(f"FWI: {LEVEL_LABELS[fwi_level]}")
    if base >= CONCURRENCE and RANK[fwi_level] >= CONCURRENCE and top < len(LEVELS) - 1:
        top += 1
        reasons.append("Los dos índices coinciden en condiciones altas: se sube un paso.")
    return LEVELS[top], reasons


def local_day(stamp_utc: str) -> str:
    """Fecha en Chile de una hora UTC ("2027-01-15T02:00" UTC → "2027-01-14")."""
    moment = datetime.fromisoformat(stamp_utc.rstrip("Z")).replace(tzinfo=ZoneInfo("UTC"))
    return moment.astimezone(CHILE_TZ).date().isoformat()


def evaluate(hourly: dict[str, list[Any]]) -> dict[str, Any]:
    """Evalúa un pronóstico horario (horas en UTC) → horas marcadas y resumen por día de Chile."""
    times = hourly.get("time") or []
    temp = hourly.get("temperature_2m") or []
    hum = hourly.get("relative_humidity_2m") or []
    wind = hourly.get("wind_speed_10m") or []
    gust = hourly.get("wind_gusts_10m") or []
    wdir = hourly.get("wind_direction_10m") or []
    hours: list[dict[str, Any]] = []
    days: dict[str, dict[str, Any]] = {}
    for i, stamp in enumerate(times):
        t = temp[i] if i < len(temp) else None
        rh = hum[i] if i < len(hum) else None
        w = wind[i] if i < len(wind) else None
        flags = hour_flags(t, rh, w)
        n = sum(flags)
        score = hour_score(t, rh, w)
        hours.append({"time": stamp if stamp.endswith("Z") else f"{stamp}Z", "t": t, "rh": rh, "wind": w,
                      "gust": gust[i] if i < len(gust) else None,
                      "dir": wdir[i] if i < len(wdir) else None, "n": n, "score": score})
        key = local_day(stamp)
        day = days.setdefault(key, {"date": key, "hours_3of3": 0, "hours_2of3": 0, "tmax": None,
                                           "rhmin": None, "windmax": None, "gustmax": None, "max_score": 0.0, "valid_hours": 0})
        day["valid_hours"] += t is not None and rh is not None and w is not None
        day["hours_3of3"] += n == 3
        day["hours_2of3"] += n >= 2
        if t is not None:
            day["tmax"] = t if day["tmax"] is None else max(day["tmax"], t)
        if rh is not None:
            day["rhmin"] = rh if day["rhmin"] is None else min(day["rhmin"], rh)
        if w is not None:
            day["windmax"] = w if day["windmax"] is None else max(day["windmax"], w)
        g = gust[i] if i < len(gust) else None
        if g is not None:
            day["gustmax"] = g if day["gustmax"] is None else max(day["gustmax"], g)
        day["max_score"] = max(day["max_score"], score)
    summary = []
    for day in days.values():
        # Un día sin suficientes horas medidas no se clasifica: «sin datos» nunca debe verse como «bajo».
        valid = day.pop("valid_hours")
        if valid < MIN_VALID_HOURS:
            continue
        level = classify_day(day["hours_3of3"], day["hours_2of3"], day["tmax"], day["rhmin"], day["max_score"])
        summary.append({**day, "level": level, "score": int(round(day["max_score"]))})
    return {"hours": hours, "days": summary}

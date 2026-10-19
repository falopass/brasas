"""Índice diario 30-30-30 por comuna, combinado con el FWI.

La regla 30-30-30 (temperatura sobre 30 °C, humedad relativa bajo 30 % y viento sobre 30 km/h)
es la referencia que CONAF difunde para condiciones de propagación muy favorables.
BRASA la evalúa hora a hora sobre el pronóstico de Open-Meteo en varios puntos de cada comuna
(`evaluation_points`: el centro y, si su caja es extensa, hasta cuatro puntos interiores) y la
deja con el peor nivel del día (`evaluate_comuna`): una comuna que junta costa y cordillera no
se deja representar por un solo centro.

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

MAX_POINTS = 5      # el centro más hasta 4 puntos interiores de la caja
INNER_STEP = 0.25   # los interiores se ubican a un cuarto del ancho/alto hacia adentro
MIN_SPAN_DEG = 0.5  # bajo ~0,5° de lado (~50 km) el centro solo ya representa a la comuna


def evaluation_points(comuna, inside=None) -> list[tuple[float, float]]:
    """Puntos (lat, lon) donde se evalúa el 30-30-30 de una comuna; nunca más de MAX_POINTS.

    - El centro siempre entra: viene del catastro BCN, no de la caja.
    - Si la caja mide menos de MIN_SPAN_DEG (~0,5°, unos 50 km) en su lado mayor, la comuna es
      chica y el centro alcanza: puntos tan juntos casi nunca cambian el pronóstico y solo
      gastan cupo de Open-Meteo.
    - Si es extensa (Aysén, Natales, Antofagasta: el centro puede caer en mar o cordillera y no
      representar a la comuna), se suman hasta 4 puntos interiores a INNER_STEP del ancho y del
      alto de la caja.

    `inside(lat, lon)` —cuando se entrega— descarta los interiores que caen fuera del polígono
    de la comuna (mar o comuna vecina): un punto fuera del territorio no la representa. Sin
    `inside`, quedan todos los puntos del margen interior de la caja.
    """
    points = [(comuna.center[1], comuna.center[0])]
    w, s, e, n = comuna.bbox
    if max(e - w, n - s) < MIN_SPAN_DEG:
        return points
    dx, dy = (e - w) * INNER_STEP, (n - s) * INNER_STEP
    for lon, lat in ((w + dx, s + dy), (w + dx, n - dy), (e - dx, s + dy), (e - dx, n - dy)):
        if inside is None or inside(lat, lon):
            points.append((lat, lon))
    return points[:MAX_POINTS]


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


def point_today(hourly: dict[str, list[Any]], today: str | None = None) -> dict[str, Any] | None:
    """30-30-30 de hoy en un punto exacto (el `hourly` de Open-Meteo del punto, mismo formato que `evaluate`).

    Devuelve el nivel del día y una frase con la causa («calor 33 °C, aire seco 18 %,
    viento 35 km/h → peligro extremo»). La persona pregunta por su casa, no por la comuna:
    la comuna evalúa su centro y esta evaluación usa el punto guardado. `None` cuando el
    pronóstico no alcanza para clasificar hoy (un día sin datos no debe verse como «bajo»).
    """
    today = today or datetime.now(CHILE_TZ).date().isoformat()
    day = next((d for d in evaluate(hourly)["days"] if d["date"] == today), None)
    if day is None:
        return None
    parts = []
    if day["tmax"] is not None:
        parts.append(f"calor {day['tmax']:.0f} °C" if day["tmax"] > T_LIMIT else f"máxima {day['tmax']:.0f} °C")
    if day["rhmin"] is not None:
        parts.append(f"aire seco {day['rhmin']:.0f} %" if day["rhmin"] < RH_LIMIT else f"humedad {day['rhmin']:.0f} %")
    if day["windmax"] is not None:
        parts.append(f"viento {day['windmax']:.0f} km/h")
    label = f"peligro {LEVEL_LABELS[day['level']].lower()}"
    reason = f"{', '.join(parts)} → {label}" if parts else label
    return {"level": day["level"], "reasons": [reason]}


def evaluate_comuna(points: list[tuple[float, float]], hourlies: list[dict[str, Any]]) -> dict[str, Any]:
    """Evalúa una comuna en varios puntos y la deja con el peor caso.

    Cada punto pasa por `evaluate` con su propio pronóstico. Por fecha, el resumen de la
    comuna es el del punto con el nivel más alto (a igual nivel, el de mayor puntaje): así
    una comuna extensa que junta mar, valle y cordillera en la misma caja no queda
    representada solo por su centro. `worst_point` es el punto que produjo el peor día.

    Las `hours` devueltas son la serie del `worst_point` —la que explica el nivel— y cada
    hora declara `points_used` (cuántos puntos se evaluaron) y `worst_point` ({lat, lon}),
    así el registro horario documenta su propia procedencia. Si ningún punto produce un día
    clasificable, las horas son las del primer punto (el centro) y `worst_point` queda None.
    """
    by_point = [(point, evaluate(hourly)) for point, hourly in zip(points, hourlies)]
    best: dict[str, tuple[tuple[int, int], dict[str, Any], tuple[float, float]]] = {}
    for point, result in by_point:
        for day in result["days"]:
            key = (RANK.get(day["level"], -1), day["score"])
            if day["date"] not in best or key > best[day["date"]][0]:
                best[day["date"]] = (key, day, point)
    days = [entry[1] for _, entry in sorted(best.items())]
    top = max(best.values(), key=lambda entry: entry[0], default=None)
    worst = {"lat": top[2][0], "lon": top[2][1]} if top else None
    worst_i = next((i for i, (point, _) in enumerate(by_point) if top and point == top[2]), 0)
    meta = {"points_used": len(by_point), "worst_point": worst}
    hours = [{**hour, **meta} for hour in (by_point[worst_i][1]["hours"] if by_point else [])]
    return {"hours": hours, "days": days, "points_used": len(by_point), "worst_point": worst}

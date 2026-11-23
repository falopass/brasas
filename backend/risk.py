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

import math
from datetime import datetime, timezone
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


def budgeted_points(per_comuna: list[list[tuple[float, float]]], budget: int,
                    offset: int = 0) -> tuple[list[list[tuple[float, float]]], int]:
    """Recorta una pasada al presupuesto de ubicaciones, rotando los interiores entre pasadas.

    El centro de cada comuna siempre entra: sin él la comuna quedaría sin nivel. Con el cupo
    restante, cada comuna extensa recibe primero un punto interior —cuando el cupo alcanza para
    todas—; los cupos que sobran suman un segundo interior, rotando comunas e índices en cada
    pasada. Así ninguna comuna extensa se queda sin un punto que represente su costa o su
    cordillera, y la rotación termina visitando todos los interiores. Devuelve los puntos y el
    offset siguiente.
    """
    total = sum(len(points) for points in per_comuna)
    if total <= budget:
        return [list(points) for points in per_comuna], offset
    out = [list(points[:1]) for points in per_comuna]
    room = max(0, budget - len(per_comuna))
    with_interiors = [index for index, points in enumerate(per_comuna) if len(points) > 1]
    if not with_interiors or room == 0:
        return out, offset
    count = len(with_interiors)
    rounds = max(len(points) - 1 for points in per_comuna)
    first = min(room, count)
    start = (offset * first) % count
    order = with_interiors[start:] + with_interiors[:start]
    for index in order[:first]:
        points = per_comuna[index]
        out[index].append(points[1 + offset % (len(points) - 1)])
    extra = room - first
    if extra:
        start = (offset * extra) % count
        order = with_interiors[start:] + with_interiors[:start]
        for index in order[:extra]:
            points = per_comuna[index]
            out[index].append(points[1 + (offset + 1) % (len(points) - 1)])
    return out, (offset + 1) % (count * rounds)


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


# --- Atmósfera: índice de Haines, déficit de presión de vapor y suelo (RISK-24) ---

MAGNUS_A, MAGNUS_B = 17.625, 243.04
HAINES_HIGH_ELEVATION_M = 1000.0
HAINES_LEVELS = {1: "muy_bajo", 2: "muy_bajo", 3: "muy_bajo", 4: "bajo", 5: "moderado", 6: "alto"}
# Umbrales (límite inferior de cada clase 2 y 3) de la estabilidad (A) y la humedad (B) por variante.
_HAINES_BANDS = {
    "alta": {"levels_hpa": "700-500", "a": (18.0, 22.0), "b": (15.0, 21.0)},
    "media": {"levels_hpa": "850-700", "a": (6.0, 11.0), "b": (6.0, 13.0)},
}


def _finite(value: Any) -> float | None:
    """Número finito o None: un valor ausente, no numérico, NaN o infinito no entra a ningún cálculo."""
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def dewpoint_c(temp_c: float | None, rh_pct: float | None) -> float | None:
    """Punto de rocío (°C) con la fórmula de Magnus; None si falta un dato o la humedad no está en (0, 100]."""
    t, rh = _finite(temp_c), _finite(rh_pct)
    if t is None or rh is None or rh <= 0 or rh > 100:
        return None
    gamma = math.log(rh / 100.0) + MAGNUS_A * t / (MAGNUS_B + t)
    return MAGNUS_B * gamma / (MAGNUS_A - gamma)


def _band(value: float, limits: tuple[float, float]) -> int:
    return 1 if value < limits[0] else 2 if value < limits[1] else 3


def haines_index(t_low: float | None, t_high: float | None, rh_low: float | None, elevation_m: float = 0.0) -> dict[str, Any] | None:
    """Índice de Haines (2-6): potencial de un incendio de crecer por inestabilidad y aire seco en altura.

    Variante «alta» desde 1.000 m (700-500 hPa) y «media» bajo ese nivel (850-700 hPa): `t_low` y
    `rh_low` son la temperatura y la humedad del nivel inferior, `t_high` la temperatura del
    superior. A (estabilidad) = `t_low - t_high`; B (humedad) = depresión del punto de rocío del
    nivel inferior. Sin los tres datos válidos devuelve None: nunca se rellena con un valor típico.
    """
    low, high, dew = _finite(t_low), _finite(t_high), dewpoint_c(t_low, rh_low)
    if low is None or high is None or dew is None:
        return None
    variant = "alta" if (_finite(elevation_m) or 0.0) >= HAINES_HIGH_ELEVATION_M else "media"
    bands = _HAINES_BANDS[variant]
    lapse, depression = low - high, low - dew
    stability, moisture = _band(lapse, bands["a"]), _band(depression, bands["b"])
    index = stability + moisture
    return {
        "index": index,
        "level": HAINES_LEVELS[index],
        "variant": variant,
        "levels_hpa": bands["levels_hpa"],
        "stability": stability,
        "moisture": moisture,
        "lapse_c": round(lapse, 1),
        "dewpoint_depression_c": round(depression, 1),
    }


def _series(hourly: dict[str, Any], key: str, size: int) -> list[Any]:
    values = hourly.get(key)
    values = values if isinstance(values, list) else []
    return values[:size] + [None] * (size - len(values))


def _utc_hour(stamp: Any) -> datetime | None:
    try:
        moment = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment.replace(tzinfo=timezone.utc) if moment.tzinfo is None else moment.astimezone(timezone.utc)


def evaluate_atmosphere(hourly: dict[str, Any], elevation_m: float = 0.0, now: datetime | None = None) -> dict[str, Any] | None:
    """Resumen del día local de Chile de un punto: déficit de vapor, suelo, CAPE y Haines.

    `hourly` es el bloque horario de Open-Meteo (horas en UTC). Se toma el día de Chile de `now`
    (hora real con su UTC-3/-4); si la serie no trae ninguna hora de ese día se usan todas las
    válidas, para no esconder un pronóstico que sí existe. Cada métrica se calcula solo con sus
    propios datos: si faltan los niveles de presión, `haines` es None pero el resto se conserva.
    Sin ninguna métrica válida devuelve None.
    """
    times = hourly.get("time") if isinstance(hourly.get("time"), list) else []
    size = len(times)
    now = now or datetime.now(timezone.utc)
    today = (now.replace(tzinfo=timezone.utc) if now.tzinfo is None else now).astimezone(CHILE_TZ).date()
    moments = [_utc_hour(stamp) for stamp in times]
    valid = [i for i, moment in enumerate(moments) if moment is not None]
    in_day = [i for i in valid if moments[i].astimezone(CHILE_TZ).date() == today]
    chosen = in_day or valid
    if not chosen:
        return None

    high_ground = (_finite(elevation_m) or 0.0) >= HAINES_HIGH_ELEVATION_M
    t_low_key, t_high_key, rh_key = (
        ("temperature_700hPa", "temperature_500hPa", "relative_humidity_700hPa")
        if high_ground
        else ("temperature_850hPa", "temperature_700hPa", "relative_humidity_850hPa")
    )
    cols = {
        key: _series(hourly, key, size)
        for key in (
            "vapour_pressure_deficit",
            "soil_moisture_0_to_1cm",
            "soil_moisture_0_to_7cm",
            "cape",
            t_low_key,
            t_high_key,
            rh_key,
        )
    }

    def values(key: str) -> list[tuple[int, float]]:
        return [(i, v) for i in chosen if (v := _finite(cols[key][i])) is not None]

    vpd, cape = values("vapour_pressure_deficit"), values("cape")
    soil_1, soil_7 = values("soil_moisture_0_to_1cm"), values("soil_moisture_0_to_7cm")
    best: tuple[int, dict[str, Any]] | None = None
    for i in chosen:
        h = haines_index(_finite(cols[t_low_key][i]), _finite(cols[t_high_key][i]), _finite(cols[rh_key][i]), elevation_m)
        if h is not None and (best is None or h["index"] > best[1]["index"]):
            best = (i, h)
    if not (vpd or cape or soil_1 or soil_7 or best):
        return None

    if best is not None:
        peak = best[0]
    elif vpd:
        peak = max(vpd, key=lambda item: item[1])[0]
    elif cape:
        peak = max(cape, key=lambda item: item[1])[0]
    else:
        peak = (soil_1 or soil_7)[0][0]
    return {
        "vpd_kpa": max((v for _, v in vpd), default=None),
        "soil_moisture_0_to_1cm": min((v for _, v in soil_1), default=None),
        "soil_moisture_0_to_7cm": min((v for _, v in soil_7), default=None),
        "cape_j_kg": max((v for _, v in cape), default=None),
        "haines": best[1] if best else None,
        "observed_at": moments[peak].strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


# Umbrales de la señal de aire (µg/m³, CAMS vía Open-Meteo): MP2,5 alto con CO elevado o con
# fracción fina dominante apunta a humo; polvo mineral o MP gruesos dominantes, a polvo.
SMOKE_PM25, SMOKE_CO, SMOKE_FINE_RATIO, DUST_LIMIT = 25.0, 400.0, 0.55, 50.0
DUST_PM10, DUST_COARSE_RATIO = 80.0, 0.35


def classify_air_signal(pm25: float | None, pm10: float | None, co: float | None, dust: float | None) -> str | None:
    """«humo», «polvo» o None según los máximos de MP2,5, MP10, CO y polvo (todos en µg/m³).

    Es una señal del modelo, no una medición ni un diagnóstico: no distingue humo de incendio de
    otras quemas. Sin MP2,5 válido no hay humo; un dato ausente nunca cuenta como cero.
    """
    p25, p10, c, d = _finite(pm25), _finite(pm10), _finite(co), _finite(dust)
    if p25 is not None and p25 >= SMOKE_PM25:
        fine = p10 is not None and p10 > 0 and p25 / p10 >= SMOKE_FINE_RATIO and (d is None or d < DUST_LIMIT)
        if (c is not None and c >= SMOKE_CO) or fine:
            return "humo"
    if (d is not None and d >= DUST_LIMIT) or (
        p10 is not None and p10 >= DUST_PM10 and (p25 is None or p25 / p10 < DUST_COARSE_RATIO)
    ):
        return "polvo"
    return None

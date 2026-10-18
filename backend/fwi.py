"""Índice de peligro de incendio forestal (FWI, sistema canadiense) por comuna.

El FWI (Van Wagner, 1987) resume en un número qué tan probable es que un incendio que ya empezó
se propague con intensidad. Se calcula en cadena: tres códigos de humedad del combustible
(FFMC, DMC, DC) alimentan dos índices de comportamiento (ISI, BUI) y de ahí sale el FWI.

BRASA lo calcula con las estaciones de Open-Meteo del centro de cada comuna: temperatura,
humedad relativa y viento a las 13 h locales, y lluvia de las 24 h anteriores. Se muestra junto a
la regla 30-30-30, no en su reemplazo: el 30-30-30 mira el pronóstico hora a hora de hoy; el FWI
integra además la sequía acumulada de semanas.

Latitud y mes importan: el DMC y el DC se ajustan por el largo del día de cada estación, y las
tablas tienen versiones propias para el hemisferio sur (enero = verano). Sin latitud se usa la
tabla de 40-55°N (el valor publicado de referencia), que es lo que usan las pruebas.

Un día sin temperatura, humedad o viento no avanza la cadena: se conserva el estado anterior y se
marca el día como «sin datos», para que un hueco nunca se lea como peligro bajo.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable

# Valores de arranque fuera de temporada (Van Wagner, 1987): el sistema parte de un combustible a
# media capacidad. Se usan al inicio de cualquier serie, porque no hay memoria previa que heredar.
INIT_FFMC, INIT_DMC, INIT_DC = 85.0, 6.0, 15.0

# Constante de conversión entre el código FFMC y el contenido de humedad. No es 147,2 (el valor
# redondeado que aparece en los libros): es 250 · 59,5 / 101, y esa diferencia mueve el FFMC unas
# centésimas por día.
FFMC_COEFFICIENT = 250.0 * 59.5 / 101.0

# Umbrales de interpretación de CFFDRS para el FWI (tabla de interpretación estándar).
LEVELS = ["bajo", "moderado", "alto", "extremo"]
LEVEL_LABELS = {"bajo": "Bajo", "moderado": "Moderado", "alto": "Alto", "extremo": "Extremo"}
FWI_THRESHOLDS = ((9.0, "bajo"), (18.0, "moderado"), (35.0, "alto"))

SOURCE = "Van Wagner (1987), The Canadian Forest Fire Weather Index System"
SOURCE_URL = "https://cfs.nrcan.gc.ca/publications?id=19927"

# Factores de largo del día para el secado del humus (DMC), por banda de latitud.
# `north_40` es la tabla publicada de referencia (40-55°N); las demás son sus versiones por banda,
# con las estaciones invertidas en el hemisferio sur.
DAY_LENGTH = {
    "north_40": (6.5, 7.5, 9.0, 12.8, 13.9, 13.9, 12.4, 10.9, 9.4, 8.0, 7.0, 6.0),
    "north_20": (7.9, 8.4, 8.9, 9.5, 9.9, 10.2, 10.1, 9.7, 9.1, 8.6, 8.1, 7.8),
    "south_20": (10.1, 9.6, 9.1, 8.5, 8.1, 7.8, 7.9, 8.3, 8.9, 9.4, 9.9, 10.2),
    "south_40": (11.5, 10.5, 9.2, 7.9, 6.8, 6.2, 6.5, 7.4, 8.7, 10.0, 11.2, 11.8),
}
# Factor estacional del DC (evapotranspiración): negativo en invierno, porque el día es corto.
DROUGHT_FACTOR = {
    "north_40": (-1.6, -1.6, -1.6, 0.9, 3.8, 5.8, 6.4, 5.0, 2.4, 0.4, -1.6, -1.6),
    "south_20": (6.4, 5.0, 2.4, 0.4, -1.6, -1.6, -1.6, -1.6, -1.6, 0.9, 3.8, 5.8),
}
EQUATORIAL_DROUGHT_FACTOR = 1.4


@dataclass(frozen=True)
class State:
    """Los seis códigos del sistema para un día."""
    ffmc: float
    dmc: float
    dc: float
    isi: float
    bui: float
    fwi: float

    def as_dict(self) -> dict[str, float]:
        return {"ffmc": round(self.ffmc, 4), "dmc": round(self.dmc, 4), "dc": round(self.dc, 4),
                "isi": round(self.isi, 4), "bui": round(self.bui, 4), "fwi": round(self.fwi, 4)}


def startup() -> State:
    """Estado inicial con los valores de arranque y sus índices derivados."""
    return _state(INIT_FFMC, INIT_DMC, INIT_DC, wind=0.0)


def day_length_band(lat: float | None) -> str:
    """Banda de latitud para el factor de largo del día del DMC."""
    if lat is None or lat > 30:
        return "north_40"
    if lat > 10:
        return "north_20"
    if lat > -10:
        return "equator"
    if lat > -30:
        return "south_20"
    return "south_40"


def day_length_factor(lat: float | None, month: int) -> float:
    """Factor de secado del humus (DMC) para esa latitud y ese mes del año."""
    band = day_length_band(lat)
    if band == "equator":
        return 9.0
    return DAY_LENGTH[band][month - 1]


def drought_factor(lat: float | None, month: int) -> float:
    """Factor estacional del DC para esa latitud y ese mes del año."""
    if lat is None or lat > 20:
        return DROUGHT_FACTOR["north_40"][month - 1]
    if lat <= -20:
        return DROUGHT_FACTOR["south_20"][month - 1]
    return EQUATORIAL_DROUGHT_FACTOR


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def ffmc(temp: float, rh: float, wind: float, rain: float, prev: float) -> float:
    """Código de humedad del combustible fino (hojarasca y pasto): seca en horas."""
    rh = _clamp(rh, 1.0, 100.0)
    wmo = FFMC_COEFFICIENT * (101.0 - prev) / (59.5 + prev)
    if rain > 0.5:
        ra = rain - 0.5
        # La corrección por encima del 150 % se calcula sobre la humedad de ANTES de la lluvia.
        dry = wmo
        wmo = dry + 42.5 * ra * math.exp(-100.0 / (251.0 - dry)) * (1.0 - math.exp(-6.93 / ra))
        if dry > 150.0:
            wmo += 0.0015 * (dry - 150.0) ** 2 * math.sqrt(ra)
    wmo = min(wmo, 250.0)

    # Humedad de equilibrio secando (ed) y humedeciendo (ew), con la corrección por temperatura.
    correction = 0.18 * (21.1 - temp) * (1.0 - math.exp(-0.115 * rh))
    ed = 0.942 * rh ** 0.679 + 11.0 * math.exp((rh - 100.0) / 10.0) + correction
    ew = 0.618 * rh ** 0.753 + 10.0 * math.exp((rh - 100.0) / 10.0) + correction

    if wmo < ed and wmo < ew:  # el combustible gana humedad
        gain = 1.0 - rh / 100.0  # la tasa de humedecimiento crece con la humedad del aire
        ko = 0.424 * (1.0 - gain ** 1.7) + 0.0694 * math.sqrt(wind) * (1.0 - gain ** 8)
        m = ew - (ew - wmo) / 10 ** (ko * 0.581 * math.exp(0.0365 * temp))
    elif wmo > ed:  # el combustible pierde humedad
        ko = 0.424 * (1.0 - (rh / 100.0) ** 1.7) + 0.0694 * math.sqrt(wind) * (1.0 - (rh / 100.0) ** 8)
        m = ed + (wmo - ed) / 10 ** (ko * 0.581 * math.exp(0.0365 * temp))
    else:
        m = wmo
    return _clamp(59.5 * (250.0 - m) / (FFMC_COEFFICIENT + m), 0.0, 101.0)


def dmc(temp: float, rh: float, rain: float, prev: float, month: int, lat: float | None = None) -> float:
    """Código de humedad de la capa de humus: capa intermedia, memoria de días."""
    temp = max(temp, -1.1)
    rh = _clamp(rh, 0.0, 100.0)
    if rain <= 1.5:
        pr = prev
    else:
        rw = 0.92 * rain - 1.27
        wmi = 20.0 + 280.0 / math.exp(0.023 * prev)
        if prev <= 33.0:
            b = 100.0 / (0.5 + 0.3 * prev)
        elif prev <= 65.0:
            b = 14.0 - 1.3 * math.log(prev)
        else:
            b = 6.2 * math.log(prev) - 17.2
        wmr = wmi + 1000.0 * rw / (48.77 + b * rw)
        pr = 43.43 * (5.6348 - math.log(wmr - 20.0)) if wmr > 20.0 else 0.0
    pr = max(pr, 0.0)
    rk = 1.894 * (temp + 1.1) * (100.0 - rh) * day_length_factor(lat, month) * 1e-4
    return max(0.0, pr + rk)


def dc(temp: float, rain: float, prev: float, month: int, lat: float | None = None) -> float:
    """Código de sequía: capa profunda, memoria de semanas y meses."""
    temp = max(temp, -2.8)
    if rain <= 2.8:
        dr = prev
    else:
        rw = 0.83 * rain - 1.27
        smi = 800.0 * math.exp(-prev / 400.0)
        dr = max(0.0, prev - 400.0 * math.log(1.0 + 3.937 * rw / smi))
    pe = max(0.0, (0.36 * (temp + 2.8) + drought_factor(lat, month)) / 2.0)
    return max(0.0, dr + pe)


def isi(ffmc_value: float, wind: float) -> float:
    """Índice de propagación inicial: velocidad esperada del fuego en combustible fino."""
    m = FFMC_COEFFICIENT * (101.0 - ffmc_value) / (59.5 + ffmc_value)
    fine = 91.9 * math.exp(-0.1386 * m) * (1.0 + m ** 5.31 / 4.93e7)
    return 0.208 * math.exp(0.05039 * wind) * fine


def bui(dmc_value: float, dc_value: float) -> float:
    """Índice de combustible disponible: cuánto combustible acumulado puede arder."""
    if dmc_value == 0.0 and dc_value == 0.0:
        return 0.0
    simple = 0.8 * dc_value * dmc_value / (dmc_value + 0.4 * dc_value)
    if dmc_value == 0.0:
        return 0.0
    p = (dmc_value - simple) / dmc_value
    compound = dmc_value - (0.92 + (0.0114 * dmc_value) ** 1.7) * p
    return max(0.0, compound) if simple < dmc_value else simple


def fwi(isi_value: float, bui_value: float) -> float:
    """Índice final: intensidad de propagación esperada (adimensional)."""
    if bui_value > 80.0:
        fd = 1000.0 / (25.0 + 108.64 / math.exp(0.023 * bui_value))
    else:
        fd = 0.626 * bui_value ** 0.809 + 2.0
    b = 0.1 * isi_value * fd
    if b <= 1.0:
        return b
    return math.exp(2.72 * (0.434 * math.log(b)) ** 0.647)


def _state(ffmc_value: float, dmc_value: float, dc_value: float, wind: float) -> State:
    i = isi(ffmc_value, wind)
    b = bui(dmc_value, dc_value)
    return State(ffmc_value, dmc_value, dc_value, i, b, fwi(i, b))


def level(fwi_value: float | None) -> str | None:
    """Nivel en palabras a partir del FWI, con los umbrales de interpretación de CFFDRS."""
    if fwi_value is None:
        return None
    for limit, name in FWI_THRESHOLDS:
        if fwi_value < limit:
            return name
    return "extremo"


def step(prev: State, row: dict[str, Any], lat: float | None = None) -> State:
    """Avanza un día la cadena. Si falta una observación, devuelve el estado anterior."""
    temp, rh, wind = row.get("temp"), row.get("rh"), row.get("wind")
    if temp is None or rh is None or wind is None:
        return prev
    rain = row.get("rain") or 0.0
    month = _month(row.get("date"))
    f = ffmc(temp, rh, wind, rain, prev.ffmc)
    d = dmc(temp, rh, rain, prev.dmc, month, lat)
    c = dc(temp, rain, prev.dc, month, lat)
    return _state(f, d, c, wind)


def _month(date: Any) -> int:
    try:
        return int(str(date)[5:7])
    except ValueError:
        return 1


def series(rows: Iterable[dict[str, Any]], lat: float | None = None, init: State | None = None) -> list[dict[str, Any]]:
    """Calcula la serie completa. Cada fila: {date, temp, rh, wind, rain}.

    Devuelve una fila por entrada, con los códigos del día y `level`. Los días sin datos conservan
    el estado anterior y quedan marcados con `missing: True`.
    """
    state = init or startup()
    out: list[dict[str, Any]] = []
    for row in rows:
        temp, rh, wind = row.get("temp"), row.get("rh"), row.get("wind")
        missing = temp is None or rh is None or wind is None
        state = step(state, row, lat)
        out.append({"date": row.get("date"), "temp": temp, "rh": rh, "wind": wind,
                    "rain": row.get("rain") or 0.0, "missing": missing,
                    **state.as_dict(), "level": level(state.fwi)})
    return out


def summary(rows: list[dict[str, Any]], days: int = 3) -> list[dict[str, Any]]:
    """Los últimos `days` días con datos, para mostrar en la ficha y en Riesgo."""
    valid = [r for r in rows if not r["missing"]]
    return valid[-days:] if days else valid


def hourly_to_daily(hourly: dict[str, list[Any]], obs_hour: int = 13) -> list[dict[str, Any]]:
    """Convierte horas locales de Chile en un registro por día: la observación de las 13 h y su lluvia.

    La lluvia es la de las 24 h anteriores a esa observación, que es el intervalo con el que trabaja
    el sistema. El primer día se descarta: su ventana de lluvia estaría incompleta.
    """
    times = hourly.get("time") or []
    temp = hourly.get("temperature_2m") or []
    hum = hourly.get("relative_humidity_2m") or []
    wind = hourly.get("wind_speed_10m") or []
    rain = hourly.get("precipitation") or []
    out: list[dict[str, Any]] = []
    for i, stamp in enumerate(times):
        if i < 23 or _hour(stamp) != obs_hour:
            continue
        window = [rain[j] for j in range(i - 23, i + 1) if j < len(rain)]
        known = [v for v in window if v is not None]
        out.append({"date": str(stamp)[:10], "temp": temp[i] if i < len(temp) else None,
                    "rh": hum[i] if i < len(hum) else None, "wind": wind[i] if i < len(wind) else None,
                    "rain": round(sum(known), 2) if known else None})
    return out


def _hour(stamp: Any) -> int:
    try:
        return int(str(stamp)[11:13])
    except ValueError:
        return -1


def merge_days(archive: list[dict[str, Any]], forecast: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Une archivo y pronóstico por fecha: el archivo manda, excepto donde no trae la observación.

    El archivo de reanálisis llega con días de retraso; el pronóstico cubre ese hueco y los días que
    vienen. Así la serie no tiene saltos y el estado de sequía se arrastra sin reinicios.
    """
    merged = {r["date"]: r for r in archive if r.get("temp") is not None and r.get("rh") is not None}
    for row in forecast:
        merged.setdefault(row["date"], row)
    return [merged[date] for date in sorted(merged)]


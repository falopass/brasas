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
        return {
            "ffmc": round(self.ffmc, 4),
            "dmc": round(self.dmc, 4),
            "dc": round(self.dc, 4),
            "isi": round(self.isi, 4),
            "bui": round(self.bui, 4),
            "fwi": round(self.fwi, 4),
        }


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
    ed = 0.942 * rh**0.679 + 11.0 * math.exp((rh - 100.0) / 10.0) + correction
    ew = 0.618 * rh**0.753 + 10.0 * math.exp((rh - 100.0) / 10.0) + correction

    if wmo < ed and wmo < ew:  # el combustible gana humedad
        gain = 1.0 - rh / 100.0  # la tasa de humedecimiento crece con la humedad del aire
        ko = 0.424 * (1.0 - gain**1.7) + 0.0694 * math.sqrt(wind) * (1.0 - gain**8)
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
    fine = 91.9 * math.exp(-0.1386 * m) * (1.0 + m**5.31 / 4.93e7)
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
        fd = 0.626 * bui_value**0.809 + 2.0
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


def percentile(value: float | None, series: list[float], minimum: int = 10) -> float | None:
    """Dónde cae `value` dentro de su propia historia, en escala de 0 a 100.

    Regla: cuentan los valores menores que `value` más la mitad de los empates; cuando los
    empates son impares la mitad se redondea hacia arriba, porque una observación no se
    parte. Con una serie sin repetidos equivale a la fracción de días con FWI menor o
    igual, y el máximo de la serie queda siempre en 100.

    Ejemplo: en la serie 1 a 10 el 5 queda en el percentil 50 (cuatro menores + un
    empate) y el 10 en el 100; en la serie [5, 5, 5, 5] el 5 queda en el 50 (dos de los
    cuatro empates cuentan).

    Devuelve None si falta `value` o si la serie trae menos de `minimum` datos: con tan
    poca historia cualquier percentil sería una cifra inventada.
    """
    if value is None or len(series) < minimum:
        return None
    below = sum(1 for item in series if item < value)
    ties = sum(1 for item in series if item == value)
    return round(100 * (below + (ties + 1) // 2) / len(series))


# ---------------------------------------------------------------------------
# Escenario estimado de propagación (FUEGO-02)
#
# El ISI de más arriba ya combina viento y combustible fino; este bloque lo convierte en una
# velocidad de avance y una dirección, sumando la pendiente cuando existe. Es la forma simple
# del enfoque de Rothermel/Byram que usa el sistema canadiense FBP (FCFDG 1992, informe
# ST-X-3, ecuaciones 39-51; correcciones de Wotton et al. 2009, informe GLC-X-10), y se limita
# al combustible fino, que es lo que describe el FFMC:
#
# 1. La humedad del combustible fino entra por el FFMC, dentro del ISI (ecs. 45-46): es un
#    factor multiplicativo, no un peso aditivo.
# 2. La pendiente se convierte en un «viento equivalente» (WSE) que empuja ladera arriba: el
#    factor SF = e^(3,533·(pendiente %/100)^1,2) escala la velocidad sin viento y esa ROS se
#    invierte por la curva del combustible (ecs. 39-44). La del punto la estima
#    `providers/elevation` desde el Copernicus DEM GLO-90 vía Open-Meteo; sin ese dato queda
#    fuera del cálculo y se declara en `assumptions`.
# 3. El viento y el WSE se suman como vectores: el viento empuja a sotavento y la pendiente,
#    cuesta arriba (ecs. 47-51). Tampoco hay pesos aquí: es una suma física.
# 4. La velocidad sale de la curva ROS = a·(1-e^(-b·ISI))^c del combustible O-1b (pasto en pie,
#    completamente curado —con grado de curado 100 el factor de curado es 1 y la ecuación es la
#    de base—). Es la curva publicada más cercana a hojarasca y pasto: el matorral chileno no
#    tiene una propia en BRASA, y por eso el resultado es un escenario estimado, nunca una
#    predicción ni el perímetro del fuego.

SPREAD_FUEL = "pasto en pie seco (tipo O-1b del FBP canadiense)"
SPREAD_ROS_A, SPREAD_ROS_B, SPREAD_ROS_C = 250.0, 0.0350, 1.7  # curva ROS del tipo O-1b (FCFDG 1992)
SLOPE_CAP_PCT = 70.0  # sobre 70 % de pendiente el FBP fija el factor en 10 (sin evidencia empírica)
SPREAD_SOURCE = "FCFDG (1992) ST-X-3, ecs. 39-51; Wotton et al. (2009) GLC-X-10"


def _spread_ros(isi_value: float) -> float:
    """Velocidad de propagación en m/min del combustible de referencia, a partir del ISI."""
    return SPREAD_ROS_A * (1.0 - math.exp(-SPREAD_ROS_B * isi_value)) ** SPREAD_ROS_C


def _spread_isi_from_ros(ros_m_min: float) -> float:
    """ISI equivalente a una ROS: la inversa de `_spread_ros`, con el tope de Wotton (ec. 41b)."""
    rest = 1.0 - (ros_m_min / SPREAD_ROS_A) ** (1.0 / SPREAD_ROS_C)
    return math.log(max(rest, 0.01)) / (-SPREAD_ROS_B)


def _slope_factor(slope_deg: float) -> float:
    """Factor de propagación por pendiente (ec. 39): crece con la pendiente en %, tope 10 a 70 %."""
    pct = math.tan(math.radians(slope_deg)) * 100.0
    return 10.0 if pct >= SLOPE_CAP_PCT else math.exp(3.533 * (pct / 100.0) ** 1.2)


def _finite(value: Any) -> Any:
    """El número tal cual si es finito; None si es NaN, infinito, texto u otra cosa de JSON."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return value


def _slope_equivalent_wind(isf: float, fuel_factor: float) -> float:
    """Viento equivalente a la pendiente, hacia la subida (ecs. 44a-e de Wotton 2009)."""
    wse = math.log(isf / (0.208 * fuel_factor)) / 0.05039
    if wse > 40.0:
        if isf >= 0.999 * 2.496 * fuel_factor:
            wse = 112.45
        else:
            wse = 28.0 - math.log(1.0 - isf / (2.496 * fuel_factor)) / 0.0818
    return wse


def propagation_scenario(
    ffmc_value: float | None,
    wind_kmh: float | None,
    wind_deg: float | None = None,
    slope_deg: float | None = None,
    aspect_deg: float | None = None,
) -> dict[str, Any] | None:
    """Escenario estimado de propagación: velocidad y dirección dominante del avance.

    `wind_deg` es la dirección DESDE la que sopla el viento (convención meteorológica, la de
    Open-Meteo) y `aspect_deg` la dirección HACIA la que mira la ladera (hacia abajo); ambas se
    convierten a rumbo de avance sumándoles 180°, como en el FBP. `slope_deg` es la pendiente en
    grados —la estima `providers/elevation` desde el Copernicus DEM GLO-90 vía Open-Meteo—;
    sin ella (sin consulta al DEM o proveedor caído) el escenario es de terreno plano.

    Un aporte sin dirección conocida se asume alineado con la resultante de los demás: es una
    cota alta declarada en `assumptions`, no un dato. Sin FFMC o sin velocidad de viento no hay
    escenario: devuelve None en vez de inventar condiciones.
    """
    # Guardas de entrada: lo que llega de JSON puede ser NaN, infinito o texto. El FFMC solo
    # tiene sentido físico en (0, 101]; fuera de ahí m sale negativo y el ISI, sin sentido.
    ffmc_value = _finite(ffmc_value)
    wind_kmh = _finite(wind_kmh)
    if ffmc_value is None or wind_kmh is None or not 0.0 < ffmc_value <= 101.0 or wind_kmh < 0.0:
        return None
    # Direcciones y pendiente no finitas se tratan como desconocidas, no como dato; los rumbos
    # se normalizan a [0, 360) antes de entrar a la suma vectorial y de salir al payload.
    wind_deg = _finite(wind_deg)
    aspect_deg = _finite(aspect_deg)
    slope_deg = _finite(slope_deg)
    if wind_deg is not None:
        wind_deg %= 360.0
    if aspect_deg is not None:
        aspect_deg %= 360.0
    m = FFMC_COEFFICIENT * (101.0 - ffmc_value) / (59.5 + ffmc_value)
    fuel_factor = 91.9 * math.exp(-0.1386 * m) * (1.0 + m**5.31 / 4.93e7)
    zero_wind_isi = 0.208 * fuel_factor

    wind_to = math.radians((wind_deg + 180.0) % 360.0) if wind_deg is not None else None
    upslope = math.radians((aspect_deg + 180.0) % 360.0) if aspect_deg is not None else None

    slope_wind = 0.0
    if slope_deg and zero_wind_isi > 0.0:
        isf = _spread_isi_from_ros(_spread_ros(zero_wind_isi) * _slope_factor(slope_deg))
        slope_wind = _slope_equivalent_wind(isf, fuel_factor) if isf > 0.0 else 0.0

    # Suma vectorial (ecs. 47-51): cada aporte empuja hacia su dirección; el que no la tiene
    # se asume alineado con la resultante y se declara como cota alta en `assumptions`.
    push_x = push_y = undirected = 0.0
    for speed, direction in ((wind_kmh, wind_to), (slope_wind, upslope)):
        if direction is not None:
            push_x += speed * math.sin(direction)
            push_y += speed * math.cos(direction)
        else:
            undirected += speed
    directed = math.hypot(push_x, push_y)
    raz = None
    if directed > 0.0:
        raz = math.degrees(math.acos(_clamp(push_y / directed, -1.0, 1.0)))
        if push_x < 0.0:
            raz = (360.0 - raz) % 360.0
    effective_wind = directed + undirected

    assumptions = ["Combustible de referencia: " + SPREAD_FUEL + "; el matorral chileno no tiene curva propia en BRASA."]
    if slope_deg:
        assumptions.append(
            "Pendiente estimada con el modelo de elevación Copernicus GLO-90 (vía Open-Meteo): "
            "~90 m de resolución, no el detalle fino de la quebrada."
        )
    else:
        assumptions.append(
            "Terreno plano: este escenario no considera la pendiente del terreno; "
            "en una ladera el fuego suele subir más rápido y el avance puede cambiar de dirección."
        )
    if wind_deg is None:
        assumptions.append("Sin dirección de viento confiable: se asume la de la resultante.")
    elif slope_deg and aspect_deg is None:
        assumptions.append("Sin orientación de ladera: se asumió que la pendiente empuja a favor del viento (cota alta).")

    try:
        isi_eff = zero_wind_isi * math.exp(0.05039 * effective_wind)
        ros = _spread_ros(isi_eff)
    except (OverflowError, ValueError):
        return None
    if not all(math.isfinite(v) for v in (effective_wind, isi_eff, ros)):
        return None
    return {
        "kind": "escenario_estimado",
        "ffmc": round(ffmc_value, 2),
        "wind_kmh": wind_kmh,
        "wind_deg": wind_deg,
        "slope_deg": slope_deg,
        "aspect_deg": aspect_deg,
        "effective_wind_kmh": round(effective_wind, 1),
        "isi": round(isi_eff, 2),
        "speed_m_min": round(ros, 1),
        "speed_kmh": round(ros * 0.06, 2),
        "direction_deg": round(raz, 1) if raz is not None else None,
        "fuel": SPREAD_FUEL,
        "reference": SPREAD_SOURCE,
        "assumptions": assumptions,
    }


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
        out.append(
            {
                "date": row.get("date"),
                "temp": temp,
                "rh": rh,
                "wind": wind,
                "rain": row.get("rain") or 0.0,
                "missing": missing,
                **state.as_dict(),
                "level": level(state.fwi),
            }
        )
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
        out.append(
            {
                "date": str(stamp)[:10],
                "temp": temp[i] if i < len(temp) else None,
                "rh": hum[i] if i < len(hum) else None,
                "wind": wind[i] if i < len(wind) else None,
                "rain": round(sum(known), 2) if known else None,
            }
        )
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

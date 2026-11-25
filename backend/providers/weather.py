"""Open-Meteo: pronóstico horario (riesgo por comuna), condiciones actuales (alertas) y reanálisis ERA5 (casos)."""

from __future__ import annotations

import asyncio
from contextvars import ContextVar
from datetime import date, datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlsplit
from weakref import WeakKeyDictionary
from zoneinfo import ZoneInfo

import httpx

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
AIR_VARS = "pm2_5,pm10,carbon_monoxide,aerosol_optical_depth,dust"
HOURLY_VARS = "temperature_2m,relative_humidity_2m,wind_speed_10m,wind_gusts_10m,wind_direction_10m"
CURRENT_VARS = "temperature_2m,relative_humidity_2m,wind_speed_10m,wind_gusts_10m,wind_direction_10m"
BATCH_SIZE = 50
# Modelo global fijo del pronóstico: sin `models` Open-Meteo mezcla modelos según la región y los
# niveles de presión (850/700/500 hPa) no siempre vienen del mismo, lo que rompe el índice de Haines.
DEFAULT_MODEL = "ecmwf_ifs025"
# Variables de atmósfera y suelo para vigilar el combustible y la inestabilidad (índice de Haines).
ATMOS_EXTRA_VARS = [
    "vapour_pressure_deficit",
    "soil_moisture_0_to_1cm",
    "soil_moisture_0_to_7cm",
    "cape",
    "temperature_850hPa",
    "temperature_700hPa",
    "temperature_500hPa",
    "relative_humidity_850hPa",
    "relative_humidity_700hPa",
]
# Tope propio bajo el límite gratuito de Open-Meteo (10.000/día): deja margen para el viento de
# los avisos, el clima de los casos y los reintentos. Cada ubicación de un lote cuenta como una
# llamada, así que el presupuesto se mide en ubicaciones, no en peticiones HTTP.
DAILY_LOCATIONS_CAP = 9000


class WeatherError(Exception):
    pass


class WeatherRateLimited(WeatherError):
    """Open-Meteo rechazó la petición por volumen (límite por minuto). Se puede reintentar."""


CHILE_TZ = ZoneInfo("America/Santiago")
_CALL_FAMILIES = ("forecast", "archive", "air-quality")

# Cupo de Open-Meteo (RISK-14): llamadas, ubicaciones y 429 hechos hoy, en el día local de Chile.
# Es diagnóstico: cuenta cada intento, incluidos los 429 y los fallos de red del proceso.
_calls: dict[str, Any] = {
    "since": None,
    "day": None,
    "calls": 0,
    "locations": 0,
    "by_endpoint": {},
    "by_endpoint_locations": {},
    "rate_limited": 0,
}

# REND-02: lo efectivamente servido (solo respuestas exitosas) es lo que descuenta el cupo
# persistente; un 429 o una red caída no gastan el día, solo quedan en el diagnóstico de arriba.
_served: dict[str, Any] = {"day": None, "locations": 0}


class SpentOp:
    """Gasto servido de UNA operación, separado por día local de Chile (REND-02 t4).

    La diferencia de `served()` antes y después mezclaba operaciones: una respuesta ajena que
    llegara en medio (otra ruta, otro `asyncio.gather`, otro hilo) quedaba atribuida a la tarea
    que medía, inflando su gasto y el día. Cada operación abre su propio `SpentOp` con
    `start_op` y lo liquida con `end_op`: ni el intercalado de otras operaciones ni los hilos
    (`asyncio.to_thread` copia el contexto) pueden contaminarlo, y las operaciones anidadas
    suman solo a la más interior, así nunca se cuenta doble.

    REND-02 t4: además de lo servido (`by_day`), la operación anota lo despachado y sin
    respuesta (`in_flight`) y si fue cortada (`cut`). Una cancelación o un timeout con la
    petición ya en la red dejan el resultado incierto: Open-Meteo pudo haberla servido y
    esa parte se conserva como gasto al liquidar; un 429 o un error con respuesta recibida
    son fallos ciertos y dejan de estar en vuelo (el contrato de siempre: no cuentan).

    Re-revisión (G1/G2): lo en vuelo se anota por el día local en que la petición salió a la
    red (`in_flight`, día → ubicaciones), no como un total, así un corte conserva el gasto en
    el día donde quedó en vuelo: reservar en D y despachar en D+1 no le imputa a D. La
    operación conoce además el día de su reserva (`reserve_day`), un gancho de cobertura
    (`cover`) que `_get` usa para que el despacho quede cubierto por una reserva del día en
    que ocurre cuando la medianoche de Chile cae en medio de la operación, y `extra`: las
    reservas hechas en días distintos al de la reserva, que la liquidación ajusta por su lado.
    """

    __slots__ = ("by_day", "in_flight", "cut", "reserve_day", "cover", "extra")

    def __init__(self) -> None:
        # Día local (AAAA-MM-DD) del DESPACHO → ubicaciones servidas por peticiones
        # despachadas ese día (G3): una respuesta que cruza medianoche se cobra al día
        # que la cubre —el que `in_flight` anotó al enviar—, no al día nuevo, para que
        # ninguna petición ya despachada caiga en un día sin reserva que la respalde.
        self.by_day: dict[str, int] = {}
        # Día local del DESPACHO → ubicaciones con la petición enviada y sin respuesta;
        # con respuesta cierta (éxito, 429, error de red) vuelven a cero.
        self.in_flight: dict[str, int] = {}
        # La operación se cortó (timeout o cancelación) con peticiones en vuelo.
        self.cut: bool = False
        # Día donde `_om_reserve` cubrió esta operación; None si la operación no reserva.
        self.reserve_day: str | None = None
        # Gancho (día, ubicaciones) → bool que `_get` llama al cambiar el día contable.
        self.cover: Any = None
        # Día → ubicaciones reservadas en días distintos al de la reserva (cobertura G1).
        self.extra: dict[str, int] = {}

    @property
    def locations(self) -> int:
        return sum(self.by_day.values())


def _flight_add(op: SpentOp, day: str, locations: int) -> None:
    """Anota el despacho en el día local en que la petición salió a la red (G2)."""
    op.in_flight[day] = op.in_flight.get(day, 0) + locations


def _flight_back(op: SpentOp, day: str, locations: int) -> None:
    """Retira del vuelo lo que recibió respuesta cierta: ya no queda nada incierto."""
    restante = op.in_flight.get(day, 0) - locations
    if restante > 0:
        op.in_flight[day] = restante
    else:
        op.in_flight.pop(day, None)


_op_stack: ContextVar[tuple[SpentOp, ...]] = ContextVar("om_op_stack", default=())


def start_op() -> SpentOp:
    """Abre la contabilidad local de una operación (el que pide a Open-Meteo la liquida)."""
    op = SpentOp()
    _op_stack.set(_op_stack.get() + (op,))
    return op


def end_op(op: SpentOp) -> SpentOp:
    """Cierra la operación y la devuelve con su gasto por día; cerrar dos veces no duplica."""
    stack = _op_stack.get()
    if op in stack:
        i = len(stack) - 1 - stack[::-1].index(op)
        _op_stack.set(stack[:i] + stack[i + 1 :])
    return op


def _op_active() -> bool:
    """Si hay una operación abierta en este contexto: su gasto lo liquida quien la abrió."""
    return bool(_op_stack.get())


# REND-02: medidor del gasto por tarea, asociado al cliente HTTP que pertenece a cada `Services`.
# Así dos instancias no se pisan el callable ni registran el gasto en la base ajena.
_day_meters: WeakKeyDictionary = WeakKeyDictionary()


def set_day_meter(client: httpx.AsyncClient, meter: Any) -> None:
    """Asocia el medidor de gasto al cliente que usa una instancia de `Services`."""
    _day_meters[client] = meter


def clear_day_meter(client: httpx.AsyncClient, meter: Any) -> None:
    """Limpia el medidor solo si sigue siendo `meter`: no pisa el de otra instancia."""
    if _day_meters.get(client) == meter:
        _day_meters.pop(client, None)


def _today() -> date:
    return datetime.now(CHILE_TZ).date()


def _family(url: str) -> str:
    tail = urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1]
    return tail if tail in _CALL_FAMILIES else "otras"


def _bump(url: str, locations: int = 1) -> None:
    """Suma un intento al diagnóstico del día: cuenta también los 429 y los fallos de red."""
    today = _today()
    if _calls["day"] != today:
        _calls.update(
            day=today,
            calls=0,
            locations=0,
            by_endpoint={},
            by_endpoint_locations={},
            rate_limited=0,
            since=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
    _calls["calls"] += 1
    _calls["locations"] += locations
    family = _family(url)
    _calls["by_endpoint"][family] = _calls["by_endpoint"].get(family, 0) + 1
    _calls["by_endpoint_locations"][family] = _calls["by_endpoint_locations"].get(family, 0) + locations


def _served_add(url: str, locations: int = 1, day: str | None = None) -> None:
    """Suma ubicaciones servidas al diagnóstico global y a la operación abierta, si la hay.

    Solo la operación más interior del contexto recibe el gasto (los `start_op` anidados no
    cuentan doble). Re-revisión G3: la clave de la operación es el día del DESPACHO que
    `day` trae —el mismo que `in_flight` anotó al enviar—, no el día de la respuesta: cada
    petición despachada queda cobrada en el día cuya reserva la respaldó (o cuya cobertura
    `extra` la cubrió), y una respuesta que llega tras medianoche no infla el día nuevo.
    Sin `day` (respuestas simuladas por `_count`, que no pasaron por `_get`) vale el día
    local de la respuesta, como siempre.
    """
    today = _today()
    if _served["day"] != today:
        _served.update(day=today, locations=0)
    _served["locations"] += locations
    stack = _op_stack.get()
    if stack:
        op = stack[-1]
        clave = day or today.isoformat()
        op.by_day[clave] = op.by_day.get(clave, 0) + locations


def _self_record(client: httpx.AsyncClient, task: str, locations: int = 1) -> None:
    """Registra el gasto de una llamada de consumidor único cuando nadie lo liquida por ella.

    `current` y `archive_hourly` las usan llamadores que no saben de cupos (avisos, casos).
    Si este contexto abrió una operación (`start_op`), su contador ya sumó el gasto y quien
    la abrió es quien la registra con su tarea: no se cuenta dos veces.
    """
    if _op_active():
        return
    meter = _day_meters.get(client)
    if meter is not None:
        meter(task, locations)


def served() -> int:
    """Ubicaciones de respuestas exitosas hechas por este proceso hoy (día local de Chile).

    REND-02 t4: queda solo como diagnóstico del proceso (lo publica `/api/status`). El gasto
    que descuenta el cupo persistente se mide por operación (`start_op`/`end_op`), no con
    diferencias de este total, que mezclan operaciones concurrentes.
    """
    today = _today()
    if _served["day"] != today:
        _served.update(day=today, locations=0)
    return int(_served["locations"])


def _count(url: str, locations: int = 1) -> None:
    """Registra una llamada servida: el intento para el diagnóstico y el gasto efectivo.

    Es también la puerta que usan las pruebas para simular respuestas de Open-Meteo.
    """
    _bump(url, locations)
    _served_add(url, locations)


def counts() -> dict[str, Any]:
    """Llamadas y ubicaciones a Open-Meteo hechas hoy (día local de Chile), por familia y 429 recibidos.

    `calls` cuenta peticiones HTTP; `locations` cuenta cada punto de un lote multi-ubicación,
    que es lo que descuenta el cupo de Open-Meteo. El contador vive en memoria y se reinicia
    con el proceso: en Cloudflare el contenedor se suspende entre disparos del cron, así que
    la cifra es la de esta instancia; el acumulado de las tareas programadas se guarda en la
    base (`open_meteo_day`). Si el cupo se acerca al límite, la prioridad fija vigente para
    repartirlo es: pronóstico > FWI > normales > casos.
    """
    return {
        "since": _calls["since"],
        "calls": _calls["calls"],
        "locations": _calls["locations"],
        "by_endpoint": dict(_calls["by_endpoint"]),
        "by_endpoint_locations": dict(_calls["by_endpoint_locations"]),
        "rate_limited": _calls["rate_limited"],
    }


def _param_locations(params: dict[str, Any]) -> int:
    """Ubicaciones de una petición: la lista de latitudes separadas por coma, o una sola."""
    latitudes = str(params.get("latitude") or "").strip()
    return latitudes.count(",") + 1 if latitudes else 1


async def _get(client: httpx.AsyncClient, url: str, params: dict[str, Any]) -> Any:
    locations = _param_locations(params)
    _bump(url, locations)  # el intento se anota antes del pedido: los 429 también son diagnóstico
    stack = _op_stack.get()
    op = stack[-1] if stack else None
    hoy: str | None = None
    if op is not None:
        hoy = _today().isoformat()
        # Re-revisión G1: el despacho debe quedar cubierto por una reserva del día en que
        # ocurre. Si el día contable cambió desde la reserva (la medianoche de Chile cayó
        # en medio de la operación), la cobertura se pide aquí —bajo el candado de la base,
        # con chequeo y suma atómicos— antes de salir a la red. Sin cupo en el día nuevo,
        # la petición no se despacha y la tarea degrada igual que ante un «sin cupo».
        if op.reserve_day is not None and hoy != op.reserve_day and not (op.cover and op.cover(hoy, locations)):
            raise WeatherError("Sin cupo diario de Open-Meteo: cambió el día y el nuevo no da.")
        _flight_add(op, hoy, locations)
    try:
        response = await client.get(url, params=params)
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPStatusError as exc:
        if op is not None:
            _flight_back(op, hoy, locations)  # respuesta cierta: ya no queda nada en vuelo
        if exc.response.status_code == 429:
            _calls["rate_limited"] += 1
            raise WeatherRateLimited("Open-Meteo pidió esperar: límite por minuto.") from exc
        raise WeatherError(f"Open-Meteo no respondió ({type(exc).__name__}).") from exc
    except httpx.TimeoutException as exc:
        # Re-revisión S2: `TimeoutException` es subclase de `RequestError` y caía en el
        # reembolso general. Un Read/Write/PoolTimeout tras enviar deja la respuesta
        # incierta (Open-Meteo pudo procesar la petición) y lo despachado se conserva como
        # gasto, igual que un corte. El ConnectTimeout es distinto: la conexión nunca se
        # estableció y la petición no salió, así que sí vale cero.
        if op is not None:
            if isinstance(exc, httpx.ConnectTimeout):
                _flight_back(op, hoy, locations)  # no llegó a enviarse: fallo cierto, cero
            else:
                op.cut = True  # quedó en vuelo en el día del despacho: se conserva
        raise WeatherError(f"Open-Meteo no respondió ({type(exc).__name__}).") from exc
    except (httpx.RequestError, ValueError) as exc:
        if op is not None:
            _flight_back(op, hoy, locations)  # error de red con respuesta cierta: el fallo no gasta
        raise WeatherError(f"Open-Meteo no respondió ({type(exc).__name__}).") from exc
    except asyncio.CancelledError:
        # Timeout o cancelación con la petición ya despachada: la respuesta quedó incierta;
        # lo que sigue en vuelo se conserva como gasto del día del despacho y se re-lanza.
        if op is not None:
            op.cut = True
        raise
    if op is not None:
        _flight_back(op, hoy, locations)  # llegó la respuesta: lo servido sale del vuelo
    # REND-02: solo lo servido descuenta el cupo; el 429 y la red caída quedaron arriba.
    # Re-revisión G3: el gasto se imputa al día del despacho (`hoy`), aunque la respuesta
    # haya llegado tras la medianoche: ese día es el que reservó (o cubrió) la petición.
    _served_add(url, locations, day=hoy)
    return data


async def forecast_hourly(
    client: httpx.AsyncClient,
    points: list[tuple[float, float]],
    days: int = 7,
    extra_vars: list[str] | None = None,
    models: str | None = DEFAULT_MODEL,
) -> list[dict[str, Any]]:
    """Pronóstico horario para muchos puntos (lat, lon), en lotes multi-ubicación.

    Devuelve una lista paralela a `points` con {time, temperature_2m, ...}; `time` en UTC.
    `extra_vars` suma variables horarias solo a esta llamada (p. ej. ["precipitation",
    "freezing_level_height"] para la lluvia, AGUA-03A): el lote de las 345 comunas no las pide.
    `models` fija el modelo de Open-Meteo (por defecto ECMWF IFS 0,25°); con `None` o vacío no se envía
    y la API elige por su cuenta.

    Con más de un lote (`len(points) > BATCH_SIZE`) se usa `_bulk`, que espera y reintenta ante
    un 429: es la corrida completa del riesgo, que no tiene tope de tiempo. Con
    `len(points) <= BATCH_SIZE` se usa `_get` y el fallo es rápido: es la consulta puntual de una
    persona dentro de una petición HTTP, con 12 s de tope en `web/js/api.js`; esperar 65 s sería
    peor que fallar.

    La salida sigue siendo paralela a `points` (mismo largo y orden): `compute_risk` reparte por
    posición. Si un lote falla tras los reintentos, la excepción se propaga; nunca se devuelve
    una lista más corta ni reordenada, porque una comuna recibiría el pronóstico de otra.
    """
    hourly_vars = HOURLY_VARS if not extra_vars else HOURLY_VARS + "," + ",".join(extra_vars)
    fetch = _bulk if len(points) > BATCH_SIZE else _get
    results: list[dict[str, Any]] = []
    for i in range(0, len(points), BATCH_SIZE):
        batch = points[i : i + BATCH_SIZE]
        params: dict[str, Any] = {
            "latitude": ",".join(f"{lat:.4f}" for lat, _ in batch),
            "longitude": ",".join(f"{lon:.4f}" for _, lon in batch),
            "hourly": hourly_vars,
            "forecast_days": days,
            "timezone": "GMT",
            "wind_speed_unit": "kmh",
        }
        if models:
            params["models"] = models
        data = await fetch(client, FORECAST_URL, params)
        items = data if isinstance(data, list) else [data]
        if len(items) != len(batch):
            raise WeatherError("Open-Meteo devolvió un número inesperado de ubicaciones.")
        for item in items:
            hourly = dict(item.get("hourly") or {})
            elev = item.get("elevation")
            if isinstance(elev, (int, float)) and not isinstance(elev, bool):
                hourly["_elevation_m"] = float(elev)
            results.append(hourly)
    return results


async def current(client: httpx.AsyncClient, lat: float, lon: float) -> dict[str, Any]:
    """Condiciones actuales en un punto: una sola ubicación de cupo (REND-02 la registra).

    Es la llamada de consumidor único del viento —`wind_at` para los avisos y `/api/weather`—,
    así que el gasto se registra aquí mismo bajo la tarea «viento», sin cupo de por medio.
    """
    data = await _get(
        client,
        FORECAST_URL,
        {
            "latitude": f"{lat:.4f}",
            "longitude": f"{lon:.4f}",
            "current": CURRENT_VARS,
            "timezone": "America/Santiago",
            "wind_speed_unit": "kmh",
        },
    )
    # REND-02 t4: con una operación abierta, su contador ya sumó esta ubicación y la liquida
    # quien la abrió (p. ej. `wind_at` bajo «viento»); sin operación, el viento de los avisos
    # y `/api/weather` se registra aquí mismo, como siempre.
    _self_record(client, "viento", 1)
    return {"data": data.get("current", {}), "units": data.get("current_units", {})}


async def archive_hourly(client: httpx.AsyncClient, lat: float, lon: float, start_date: str, end_date: str) -> dict[str, Any]:
    """Reanálisis horario (ERA5 vía Open-Meteo) en UTC, para reconstrucciones históricas.

    Consumidor único (la reconstrucción de casos), así que su gasto de una ubicación se
    registra aquí mismo bajo la tarea «casos» (REND-02).
    """
    data = await _get(
        client,
        ARCHIVE_URL,
        {
            "latitude": f"{lat:.4f}",
            "longitude": f"{lon:.4f}",
            "start_date": start_date,
            "end_date": end_date,
            "hourly": HOURLY_VARS,
            "timezone": "GMT",
            "wind_speed_unit": "kmh",
        },
    )
    # REND-02 t4: mismo criterio que `current` — la reconstrucción de casos la llama quien no
    # gestiona cupos (`routes/community.py`), así que aquí se registra bajo «casos».
    _self_record(client, "casos", 1)
    return data.get("hourly", {})


FWI_VARS = "temperature_2m,relative_humidity_2m,wind_speed_10m,precipitation"
FWI_PAUSE_S = 4  # pausa entre peticiones: el límite por minuto cuenta volumen, no peticiones
FWI_RETRY_WAIT_S = 65  # lo que pide Open-Meteo cuando responde 429
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


def fwi_locations(comunas: int, today: date | None = None, archive_from: date | None = None) -> int:
    """Ubicaciones que pide una pasada del FWI: un tramo de archivo por mes y el pronóstico.

    Cada tramo mensual se pide con todas las comunas en lotes de `BATCH_SIZE`; el cupo cuenta
    cada ubicación de cada lote, así que una pasada cuesta `comunas × (meses + 1)`, no `comunas`.
    Con `archive_from` se mide una tanda en ventana incremental (que arranca después del
    inicio de la temporada): el costo de ESA tanda, no el de la temporada completa.
    """
    today = today or _today()
    archive_from = archive_from or _season_start(today)
    return comunas * (len(_month_ranges(archive_from, today)) + 1)


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


async def fwi_inputs(
    client: httpx.AsyncClient,
    points: list[tuple[float, float]],
    past_days: int = 7,
    forecast_days: int = 7,
    archive_from: date | None = None,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Series horarias para el FWI en muchos puntos: (archivo, pronóstico).

    Se piden en hora local de Chile, que es la que usa el sistema (observación de las 13 h en
    horario de verano y 12 h en invierno). El pronóstico repite los últimos `past_days` días
    porque el archivo de reanálisis llega con retraso.

    `archive_from` fija el inicio del archivo; por defecto es la temporada completa desde el 1 de
    junio (convención de `rain_season`), necesaria en el arranque en frío porque el DC tiene memoria
    de meses. Con estado previo en `fwi_daily`, el servicio pide solo una ventana corta.
    """
    today = datetime.now(ZoneInfo("America/Santiago")).date()
    archive_from = archive_from or _season_start(today)
    out: list[tuple[dict[str, Any], dict[str, Any]]] = []
    first = True
    for i in range(0, len(points), BATCH_SIZE):
        batch = points[i : i + BATCH_SIZE]
        shared = {
            "latitude": ",".join(f"{lat:.4f}" for lat, _ in batch),
            "longitude": ",".join(f"{lon:.4f}" for _, lon in batch),
            "hourly": FWI_VARS,
            "timezone": "America/Santiago",
            "wind_speed_unit": "kmh",
        }
        archive: list[dict[str, list]] = [{} for _ in batch]
        for start, end in _month_ranges(archive_from, today):
            if not first:
                await asyncio.sleep(FWI_PAUSE_S)
            first = False
            chunk = await _bulk(client, ARCHIVE_URL, {**shared, "start_date": start.isoformat(), "end_date": end.isoformat()})
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


async def air_quality(client: httpx.AsyncClient, lat: float, lon: float) -> dict[str, Any]:
    """Variables de aire pronosticadas por CAMS en un punto, horario para hoy y mañana (UTC).

    Se fija `domains=cams_global` para que el pronóstico venga del modelo CAMS global y no de
    la mezcla por defecto; MP2,5 sigue como `pm25` para las alertas de humo.
    """
    data = await _get(
        client,
        AIR_QUALITY_URL,
        {
            "latitude": f"{lat:.4f}",
            "longitude": f"{lon:.4f}",
            "hourly": AIR_VARS,
            "forecast_days": 2,
            "timezone": "GMT",
            "domains": "cams_global",
        },
    )
    return _air_series(data.get("hourly", {}))


def _air_series(hourly: dict[str, Any]) -> dict[str, Any]:
    return {
        "time": hourly.get("time") or [],
        "pm25": hourly.get("pm2_5") or [],
        "pm10": hourly.get("pm10") or [],
        "co": hourly.get("carbon_monoxide") or [],
        "aod": hourly.get("aerosol_optical_depth") or [],
        "dust": hourly.get("dust") or [],
    }


async def air_quality_batch(client: httpx.AsyncClient, points: list[tuple[float, float]], days: int = 2) -> list[dict[str, Any]]:
    """Aire CAMS para muchos puntos (lat, lon) en lotes multi-ubicación, paralelo a `points`.

    Mismo criterio que `forecast_hourly`: con más de un lote se usa `_bulk` (espera y reintenta ante
    un 429) y con uno solo `_get`, de fallo rápido. Si un lote falla la excepción se propaga: nunca
    se devuelve una lista más corta, porque una comuna recibiría el aire de otra.
    """
    fetch = _bulk if len(points) > BATCH_SIZE else _get
    results: list[dict[str, Any]] = []
    for i in range(0, len(points), BATCH_SIZE):
        batch = points[i : i + BATCH_SIZE]
        data = await fetch(
            client,
            AIR_QUALITY_URL,
            {
                "latitude": ",".join(f"{lat:.4f}" for lat, _ in batch),
                "longitude": ",".join(f"{lon:.4f}" for _, lon in batch),
                "hourly": AIR_VARS,
                "forecast_days": days,
                "timezone": "GMT",
                "domains": "cams_global",
            },
        )
        results.extend(_air_series(item.get("hourly") or {}) for item in _items(data, batch))
    return results


def air_daily_max(series: dict[str, Any], key: str = "pm25") -> dict[str, float]:
    """Máximo de una variable de aire por día local de Chile a partir de la serie horaria en UTC.

    Las horas se reagrupan en America/Santiago: el día de una persona no es el día UTC,
    así que las primeras horas UTC de mañana ya son «hoy» en Chile.
    """
    out: dict[str, float] = {}
    for ts, value in zip(series.get("time") or [], series.get(key) or []):
        if value is None:
            continue
        try:
            moment = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        except ValueError:
            continue
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        day = moment.astimezone(CHILE_TZ).date().isoformat()
        out[day] = max(float(value), out.get(day, float("-inf")))
    return out


RAIN_DAILY = "precipitation_sum"


async def daily_rain(
    client: httpx.AsyncClient,
    points: list[tuple[float, float]],
    start_date: str | None = None,
    end_date: str | None = None,
    past_days: int | None = None,
) -> list[dict[str, float]]:
    """Lluvia diaria en mm para muchos puntos: {«AAAA-MM-DD»: mm}.

    Con `past_days` usa el pronóstico, que trae también los últimos días ya medidos y tapa el retraso
    del archivo. Sin él, el archivo de reanálisis ERA5 entre dos fechas.
    """
    out: list[dict[str, float]] = []
    for i in range(0, len(points), BATCH_SIZE):
        batch = points[i : i + BATCH_SIZE]
        shared = {
            "latitude": ",".join(f"{lat:.4f}" for lat, _ in batch),
            "longitude": ",".join(f"{lon:.4f}" for _, lon in batch),
            "daily": RAIN_DAILY,
            "timezone": "America/Santiago",
        }
        if past_days is not None:
            data = await _bulk(client, FORECAST_URL, {**shared, "past_days": past_days, "forecast_days": 1})
        else:
            data = await _bulk(client, ARCHIVE_URL, {**shared, "start_date": start_date, "end_date": end_date})
        for item in _items(data, batch):
            daily = item.get("daily") or {}
            out.append({stamp: value for stamp, value in zip(daily.get("time") or [], daily.get(RAIN_DAILY) or [])})
    return out

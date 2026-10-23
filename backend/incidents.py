"""Incidentes: la evidencia satelital agrupada en el espacio y el tiempo.

Un punto de calor no es un incendio. BRASA junta las detecciones cercanas en un *incidente* y le da un estado
según cuánta evidencia independiente hay, sin presentarse nunca como fuente oficial:

- anomalia:   una sola detección (o solo de confianza baja). Puede ser fuego, una quema o una industria.
- posible:    dos o más detecciones confiables en momentos distintos, o vista por dos sensores distintos.
              Con GOES como único sensor, los dos momentos deben estar a ≤ 30 min (dos barridos seguidos).
- reportado:  además hay un aviso ciudadano verificado por moderación cerca y a la misma hora.
- confirmado: una fuente oficial (CONAF/SENAPRED) lo reconoce (official_ref). BRASA no confirma por su cuenta.
- extinguido: 24 h sin detecciones nuevas (sin evidencia satelital, no «apagado oficialmente»).
- descartado: quedó sin comuna chilena —sus detecciones cayeron fuera del país—; no es un
  incendio de Chile y no se publica, pero la fila se conserva hasta la purga normal.

Fuentes de calor fijas probables (industria, antorchas, volcanes): si TODA la evidencia de un incidente cae en
una de ellas, se marca fixed_source y no genera aviso automático. Basta una detección fuera para avisar normal.
"""
from __future__ import annotations

import json
import math
import sqlite3
import uuid
from bisect import bisect_left, bisect_right
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from typing import Any, Callable, Iterator
from zoneinfo import ZoneInfo

from backend.db import Database
from backend.geo import haversine_km, inside_chile, territory
from backend.settings import ROOT

RELIABLE = {"alta", "nominal", "media"}
ACTIVE_HOURS = 6          # una detección se une a incidentes vistos en las últimas 6 h
EXTINGUISH_HOURS = 24     # sin detecciones en 24 h → extinguido (según satélite)
REOPEN_HOURS = 72         # un rescoldo rebrota en los primeros días: hasta 72 h la evidencia
                          # nueva reabre el mismo incidente (un fuego = una ficha); más allá es otro fuego
FIXED_DAYS = 8            # celda con detecciones en ≥ 8 días distintos en 30 días → fuente fija probable
FIXED_WINDOW_DAYS = 30
FIXED_CELL_DEG = 0.02     # ~2 km
FIXED_KM = 5.0            # un incendio informado por CONAF a esta distancia invalida la regla (FIX-03)
FIXED_WEEKS = 3           # los días tienen que repartirse en al menos tres semanas distintas
OFF_SEASON_MONTHS = (4, 5, 6, 7, 8, 9, 10, 11)  # fuera de la temporada alta: noviembre a marzo
REPORT_KM, REPORT_HOURS = 3.0, 12
GOES_PAIR_MINUTES = 30  # GOES barre el disco cada 10 min: dos momentos a ≤ 30 min son dos barridos
                        # seguidos; un reflejo no se repite (menos falsos positivos sin perder rapidez)
OPEN_STATES = ("anomalia", "posible", "reportado", "confirmado", "controlado")
CAND_PAD_DEG = 0.06   # margen de la caja candidata (~6 km); la distancia real se mide contra cada detección
GRID_CELL_DEG = 0.05  # lado de la celda de la cuadrícula que indexa los incidentes abiertos en el ciclo
LINK_PAD_DEG = 0.06   # superconjunto del alcance de link_km (~6,7 km > máx. real ~4 km): solo acota la búsqueda
CHILE_TZ = ZoneInfo("America/Santiago")
MASK_DAY_HOURS = range(8, 20)  # franja «dia» de la máscara del norte: 08:00-19:59 hora de Chile,
                             # el mismo corte que el medidor de falsos positivos (INV-25)


def _t(stamp: str) -> datetime:
    return datetime.fromisoformat(stamp.replace("Z", "+00:00"))


def _stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def link_km(res_a_m: int | None, res_b_m: int | None) -> float:
    """Distancia máxima para considerar dos detecciones parte del mismo fuego: 2 km + media de las resoluciones."""
    return 2.0 + ((res_a_m or 375) + (res_b_m or 375)) / 2000.0


# Un «linker» decide a qué incidentes candidatos se une una detección nueva: recibe, por
# incidente, los puntos de sus miembros dentro del área de búsqueda y a lo más ACTIVE_HOURS
# de distancia temporal de la detección —REOPEN_HOURS si el incidente está «extinguido»,
# porque un rescoldo lo reabre— tuplas (lat, lon, resolution_m, observed_at), y la
# detección, y devuelve los ids de los incidentes tocados. Es el punto de extensión de
# `update(linker=…)` para comparar estrategias de agrupación (DET-09); la vigente es `LINKER`.
Linker = Callable[[list[tuple[str, list[tuple[float, float, int | None, str]]]],
                  float, float, int | None, str], set[str]]


def single_link(candidates: list[tuple[str, list[tuple[float, float, int | None, str]]]],
                lat: float, lon: float, resolution_m: int | None, observed_at: str) -> set[str]:
    """Enlace simple (regla vigente): la detección toca a todo incidente que tenga un
    miembro a ≤ `link_km` de ella. En episodios masivos puede encadenar focos distintos.

    La hora de la detección entra en el contrato para estrategias con ventana temporal
    por miembro; aquí no se usa porque ese filtro ya se aplicó al recoger los puntos
    (QA-07: solo llegan miembros a ≤ ACTIVE_HOURS de la detección).
    """
    return {iid for iid, points in candidates
            if any(haversine_km(plat, plon, lat, lon) <= link_km(pres, resolution_m)
                   for plat, plon, pres, _ in points)}


LINKER: Linker = single_link  # regla de agrupación vigente


@lru_cache(maxsize=1)
def known_fixed_sources() -> list[dict[str, Any]]:
    """Fuentes fijas conocidas (volcanes activos), con su radio. Archivo editable con fuente de cada punto."""
    path = ROOT / "web" / "data" / "persistent_hotspots.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))["sources"]
    except (OSError, ValueError, KeyError):
        return []


@lru_cache(maxsize=1)
def mascara_norte() -> list[dict[str, Any]]:
    """Celdas enmascaradas del norte grande (DET-45/INV-25): calor permanente medido, no incendio.

    Archivo versionado como `persistent_hotspots.json`; parte con `cells` vacía y se calibra
    con la medición de la temporada real. Cada celda declara `revisar_el`: vencida, deja de
    silenciar hasta que alguien la vuelva a medir.
    """
    path = ROOT / "web" / "data" / "mascara-norte.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))["cells"]
    except (OSError, ValueError, KeyError):
        return []


def _mask_reason(lat: float, lon: float, sensor: str | None, observed_at: str | None, now: datetime) -> str | None:
    """La razón si la detección cae en una celda vigente de la máscara del norte, o None.

    Solo GOES (sensor «ABI»): VIIRS y MODIS ven con resolución suficiente y no se enmascaran.
    `franja` de la celda: «dia» vale de 08:00 a 19:59 hora de Chile según el `observed_at` de
    la detección (el suelo desnudo solo engaña de día); «siempre» cubre el calor permanente.
    `revisar_el` (fecha ISO inclusiva) es la revisión comprometida: vencida o ilegible la celda
    no silencia, igual que `valid_to` en las fuentes curadas —avisar de más, no tapar—.
    Una celda o un `observed_at` mal formado tampoco silencia: se ignora y sigue el ciclo.
    """
    if sensor != "ABI":
        return None
    try:
        chile_hour = _t(observed_at).astimezone(CHILE_TZ).hour if observed_at else None
    except (TypeError, ValueError, AttributeError):
        chile_hour = None  # sello ilegible: «dia» no se puede evaluar → esas celdas no silencian
    for cell in mascara_norte():
        try:
            if date.fromisoformat(cell["revisar_el"]) < now.date():
                continue
            if haversine_km(lat, lon, cell["lat"], cell["lon"]) > cell["radio_km"]:
                continue
            franja = cell.get("franja")
            if franja == "dia":
                if chile_hour is None or chile_hour not in MASK_DAY_HOURS:
                    continue
            elif franja != "siempre":
                continue  # una franja desconocida no silencia
        except (KeyError, TypeError, ValueError):
            continue  # celda mal formada: se ignora, no tumba el ciclo
        return f"máscara del norte: {cell.get('motivo', 'celda calibrada')}"
    return None


def _source_active(src: dict[str, Any], now: datetime) -> bool:
    """¿La fuente curada silencia a `now`? `valid_from`/`valid_to` son días ISO (AAAA-MM-DD)
    inclusivos; `valid_from` sin `valid_to` vale desde esa fecha en adelante y sin fechas vale
    siempre (INV-16 §6: una instalación apagada no debe seguir tapando calor real). Una fecha
    mal escrita desactiva el punto: preferimos avisar de más a silenciar por un error de tipeo.
    """
    try:
        start = date.fromisoformat(src["valid_from"]) if src.get("valid_from") else None
        end = date.fromisoformat(src["valid_to"]) if src.get("valid_to") else None
    except (TypeError, ValueError):
        return False
    day = now.date()
    return (start is None or start <= day) and (end is None or day <= end)


def _official_near(db: Database, lat: float, lon: float, since: str) -> bool:
    """¿Hay un incendio informado por CONAF a ≤ FIXED_KM del punto, dentro de la ventana?"""
    for row in db.query("SELECT lat, lon FROM official_fires WHERE started_at >= ? OR started_at IS NULL", (since,)):
        if haversine_km(lat, lon, row["lat"], row["lon"]) <= FIXED_KM:
            return True
    return False


def fixed_reason(db: Database, lat: float, lon: float, now: datetime, ctx: dict[str, Any] | None = None,
                 sensor: str | None = None, observed_at: str | None = None) -> str | None:
    """Por qué una celda se considera fuente fija probable, o None si no lo es.

    Reglas (FIX-03), en este orden:
    1. Un incendio informado por CONAF a ≤ 5 km dentro de la ventana **invalida la regla entera**,
       también para un volcán conocido: un incendio real en la ladera no puede quedar silenciado
       por el cráter que hay al lado.
    2. Fuente fija conocida **vigente** a `now` (ventana `valid_from`/`valid_to` del punto):
       es fija, y se dice cuál. Fuera de su ventana no silencia.
    3. Celda vigente de la máscara del norte (`mascara-norte.json`, DET-45): silencia solo
       detecciones de GOES dentro de su radio y su `franja`; `sensor` y `observed_at` son los
       de la detección evaluada —sin ellos la máscara no aplica—.
    4. Patrón de industria: ≥ 8 días con calor en 30, **y** esos días repartidos en ≥ 3 semanas
       distintas con ≥ 14 días entre la primera y la última, o con presencia fuera de la
       temporada (abril a noviembre). Sin el reparto, un incendio de diez días seguidos
       parecería una antorcha: las semanas ISO son cubos de calendario y diez días seguidos
       pueden tocar tres sin separarse de verdad.

    Con `ctx` (el contexto del ciclo de FIX-15: oficiales de la ventana e índice de días por
    celda) las mismas consultas se resuelven en memoria con resultados idénticos.
    """
    since = _stamp(now - timedelta(days=FIXED_WINDOW_DAYS))
    if ctx is None:
        if _official_near(db, lat, lon, since):
            return None
    elif any(haversine_km(lat, lon, r["lat"], r["lon"]) <= FIXED_KM for r in ctx["official"]):
        return None
    for src in known_fixed_sources():
        if not _source_active(src, now):
            continue
        if haversine_km(lat, lon, src["lat"], src["lon"]) <= src["radius_km"]:
            label = "volcán activo conocido" if src.get("kind") == "volcan" else "fuente fija conocida"
            return f"{label} ({src.get('name', 'sin nombre')})"
    mask = _mask_reason(lat, lon, sensor, observed_at, now)
    if mask:
        return mask
    half = FIXED_CELL_DEG / 2
    if ctx is None:
        rows = db.query("SELECT DISTINCT substr(observed_at, 1, 10) AS day FROM observations "
                        "WHERE observed_at >= ? AND lat BETWEEN ? AND ? AND lon BETWEEN ? AND ? "
                        "AND confidence IN ('alta','nominal','media')",
                        (since, lat - half, lat + half, lon - half, lon + half))
        days = sorted(row["day"] for row in rows if row["day"])
    else:
        lat0, lat1, lon0, lon1 = lat - half, lat + half, lon - half, lon + half
        days = sorted({oat[:10] for cell in _cells(lat0, lon0, lat1, lon1)
                       for elat, elon, oat in ctx["days"].get(cell, ())
                       if lat0 <= elat <= lat1 and lon0 <= elon <= lon1 and oat >= since})
    if len(days) < FIXED_DAYS:
        return None
    weeks = {datetime.fromisoformat(day).isocalendar()[:2] for day in days}
    span = (datetime.fromisoformat(days[-1]) - datetime.fromisoformat(days[0])).days
    off_season = any(datetime.fromisoformat(day).month in OFF_SEASON_MONTHS for day in days)
    if len(weeks) >= FIXED_WEEKS and span >= (FIXED_WEEKS - 1) * 7:
        return f"{len(days)} días con calor repartidos en {len(weeks)} semanas distintas"
    if off_season:
        return "calor fuera de la temporada de incendios"
    return None


def is_fixed_source(db: Database, lat: float, lon: float, now: datetime, ctx: dict[str, Any] | None = None,
                    sensor: str | None = None, observed_at: str | None = None) -> bool:
    """True si la celda parece una fuente de calor fija. La razón se pide con `fixed_reason`.

    `sensor` y `observed_at` son los de la detección evaluada: la máscara del norte (regla 3)
    los necesita; sin ellos no enmascara.
    """
    return fixed_reason(db, lat, lon, now, ctx, sensor=sensor, observed_at=observed_at) is not None


def refresh_near(db: Database, lat: float, lon: float, now: datetime | None = None, km: float = REPORT_KM) -> int:
    """Recalcula los incidentes abiertos a ≤ `km` del punto y devuelve cuántos tocó.

    Se llama al verificar (o al revocar la verificación de) un reporte ciudadano: puede llevar el
    incidente a «reportado» —o devolverlo— sin que llegue ninguna detección nueva (FIX-09). La
    ventana es la de vida del incidente abierto (EXTINGUISH_HOURS), no la de vinculación: un
    incidente sigue abierto 24 h aunque no tenga detecciones nuevas en las últimas 6.
    """
    moment = now or datetime.now(timezone.utc)
    since = _stamp(moment - timedelta(hours=EXTINGUISH_HOURS))
    rows = db.query(f"SELECT * FROM incidents WHERE status IN ({','.join('?' * len(OPEN_STATES))}) AND last_seen_at >= ?",
                    (*OPEN_STATES, since))
    near = [row for row in rows if haversine_km(lat, lon, row["lat"], row["lon"]) <= km]
    for row in near:
        _refresh(db, row["id"], moment)
    return len(near)


def _nearest_comuna(inc: dict[str, Any]) -> int | None:
    """FIX-73: la comuna más cercana al centro del incidente, para cuando ningún miembro la trae.

    Un foco rural que cae en un hueco del trazado comunal (precordillera, límites, costa
    simplificada) llega a la ingesta con `comuna_code` nulo y el incidente lo heredaba:
    «sin comuna», sin enlace a la ficha comunal y `expire` lo cerraba al ciclo siguiente.
    `territory().nearest` asigna solo si el borde está a ≤ 3 km; más lejos (extranjero,
    mar abierto) devuelve None y el incidente se queda sin comuna como antes.
    """
    near = territory().nearest(inc["lat"], inc["lon"])
    return near.code if near else None


def _members(db: Database, incident_id: str) -> list[dict[str, Any]]:
    return db.query("SELECT o.* FROM observations o JOIN incident_observations io ON io.observation_id = o.id "
                    "WHERE io.incident_id = ? ORDER BY o.observed_at", (incident_id,))


def _cells(lat0: float, lon0: float, lat1: float, lon1: float) -> Iterator[tuple[int, int]]:
    """Celdas de la cuadrícula que toca la caja [lat0, lat1] × [lon0, lon1], ambos inclusive."""
    for i in range(math.floor(lat0 / GRID_CELL_DEG), math.floor(lat1 / GRID_CELL_DEG) + 1):
        for j in range(math.floor(lon0 / GRID_CELL_DEG), math.floor(lon1 / GRID_CELL_DEG) + 1):
            yield i, j


def _candidates(live: dict[str, dict[str, Any]], grid: dict[tuple[int, int], set[str]],
                obs: dict[str, Any], when: datetime) -> list[dict[str, Any]]:
    """Incidentes abiertos cuya caja con margen contiene al punto, en el orden del SQL original.

    La consulta que reemplaza (FIX-15) filtraba por la caja y el last_seen_at guardados en la
    tabla y ordenaba por first_seen_at. Su desempate lo daba el índice (status, last_seen_at)
    que la alimenta: el IN se recorre en orden alfabético, luego last_seen_at descendente y
    rowid; el sort de SQLite es estable, así que el orden observado es (first_seen_at, status,
    last_seen_at descendente, rowid), replicado aquí con ordenamientos estables encadenados.
    """
    # QA-07: la ventana es bilateral — el rango del incidente debe solapar la ventana de la
    # detección. Sin la cota superior, una detección vieja que llega tarde encontraba
    # «activo» a un incidente que aún no empezaba cuando ella ocurrió y actuaba de puente.
    since = _stamp(when - timedelta(hours=ACTIVE_HOURS))
    reopen = _stamp(when - timedelta(hours=REOPEN_HOURS))
    until = _stamp(when + timedelta(hours=ACTIVE_HOURS))
    cell = (math.floor(obs["lat"] / GRID_CELL_DEG), math.floor(obs["lon"] / GRID_CELL_DEG))
    found = []
    for inc_id in grid.get(cell, ()):
        inc = live.get(inc_id)
        if (inc is not None and inc["first_seen_at"] <= until
                and inc["min_lat"] - CAND_PAD_DEG <= obs["lat"] <= inc["max_lat"] + CAND_PAD_DEG
                and inc["min_lon"] - CAND_PAD_DEG <= obs["lon"] <= inc["max_lon"] + CAND_PAD_DEG
                # Los abiertos miran la ventana activa; un «extinguido» reciente es un rescoldo
                # posible y conserva su ventana de reapertura (FUEGO-23).
                and (inc["last_seen_at"] >= since
                     or (inc["status"] == "extinguido" and inc["last_seen_at"] >= reopen))):
            found.append(inc)
    found.sort(key=lambda inc: inc["rowid"])
    found.sort(key=lambda inc: inc["last_seen_at"], reverse=True)
    found.sort(key=lambda inc: (inc["first_seen_at"], inc["status"]))
    return found


class _Tx:
    """Vista mínima de `Database` sobre una conexión ya abierta (FIX-15).

    `db.query/one/execute` abren un `connect()` que confirma al salir: cada sentencia del
    ciclo pagaba un commit. Con esta vista todo `update` corre dentro de una sola
    transacción y confirma una vez al final, con la misma visibilidad (la misma conexión).
    """

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def query(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    def one(self, sql: str, params: tuple = ()) -> dict[str, Any] | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def execute(self, sql: str, params: tuple = ()) -> int:
        return self._conn.execute(sql, params).rowcount


def _member_rows(tx: _Tx, incident_id: str) -> list[dict[str, Any]]:
    """Miembros con solo las columnas que usa el agrupador, en el orden exacto de `_members`."""
    return tx.query("SELECT o.lat, o.lon, o.resolution_m, o.observed_at, o.frp_mw, o.confidence, o.sensor, o.comuna_code "
                    "FROM observations o JOIN incident_observations io ON io.observation_id = o.id "
                    "WHERE io.incident_id = ? ORDER BY o.observed_at", (incident_id,))


def _agg_new() -> dict[str, Any]:
    """Agregados de un incidente: lo que `_refresh`/`_status` calculan por miembro.

    `times`/`lats`/`lons`/`sensors_seq` y `comuna_times`/`comunas` son listas en el orden
    exacto de `_members` (observed_at y, en empates, el orden de alta del vínculo
    —`bisect_right` replica «va al final de los iguales»—). Mantenerlas ordenadas es lo que
    permite que `sum(lats)` y `max(set(comunas), key=count)` den el mismo resultado bit a bit
    que el `_refresh` con la lista materializada —las sumas de flotantes y el orden interno del
    set dependen del orden de la lista—; `sensors_seq` (sensor por miembro) alimenta la
    máscara del norte sin releer la tabla.
    """
    return {"times": [], "lats": [], "lons": [], "sensors_seq": [],
            "min_lat": None, "max_lat": None, "min_lon": None, "max_lon": None, "max_frp": None,
            "n_rel": 0, "rel_sensors": set(), "all_sensors": set(),
            "rel_times": set(), "rel_times_sorted": [], "has_pair": False,
            "comuna_times": [], "comunas": []}


def _agg_add(agg: dict[str, Any], m: dict[str, Any]) -> None:
    """Suma un miembro a los agregados conservando el orden de `_members`."""
    at = m["observed_at"]
    lat, lon = m["lat"], m["lon"]
    i = bisect_right(agg["times"], at)
    agg["times"].insert(i, at)
    agg["lats"].insert(i, lat)
    agg["lons"].insert(i, lon)
    agg["sensors_seq"].insert(i, m.get("sensor"))
    agg["min_lat"] = lat if agg["min_lat"] is None else min(agg["min_lat"], lat)
    agg["max_lat"] = lat if agg["max_lat"] is None else max(agg["max_lat"], lat)
    agg["min_lon"] = lon if agg["min_lon"] is None else min(agg["min_lon"], lon)
    agg["max_lon"] = lon if agg["max_lon"] is None else max(agg["max_lon"], lon)
    frp = m.get("frp_mw")
    if frp is not None:
        agg["max_frp"] = frp if agg["max_frp"] is None else max(agg["max_frp"], frp)
    if (m.get("confidence") or "") in RELIABLE:
        agg["n_rel"] += 1
        agg["rel_sensors"].add(m.get("sensor"))
        t16 = at[:16]
        if t16 not in agg["rel_times"]:
            agg["rel_times"].add(t16)
            i = bisect_left(agg["rel_times_sorted"], t16)
            agg["rel_times_sorted"].insert(i, t16)
            moment = _t(f"{t16}:00Z")
            for j in (i - 1, i + 1):  # un momento nuevo solo puede armar par con sus vecinos
                if 0 <= j < len(agg["rel_times_sorted"]) and \
                        abs(_t(f"{agg['rel_times_sorted'][j]}:00Z") - moment) <= timedelta(minutes=GOES_PAIR_MINUTES):
                    agg["has_pair"] = True
    agg["all_sensors"].add(m.get("sensor") or "?")
    comuna = m.get("comuna_code")
    if comuna:
        i = bisect_right(agg["comuna_times"], at)
        agg["comuna_times"].insert(i, at)
        agg["comunas"].insert(i, comuna)


def _agg_from_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    agg = _agg_new()
    for m in rows:
        _agg_add(agg, m)
    return agg


def _state(db: Database) -> dict[str, Any]:
    """Índices del agrupador que sobreviven entre ciclos, por base (FIX-15).

    Los vínculos incidente–detección solo se escriben en `update` y en `prune` —que
    invalida todo el estado—, así que los puntos de los miembros y los agregados pueden
    persistir; `_sync` verifica las tablas en cada ciclo por si algo externo las tocó
    (restaurar un respaldo, retención sin prune, escritos ajenos).
    """
    st = getattr(db, "_inc_state", None)
    if st is None:
        st = db._inc_state = {"pts": {}, "cells": {}, "agg": {}, "days": None,
                              "io_n": 0, "o_n": 0, "o_max": 0}
    return st


def _sync(tx: _Tx, st: dict[str, Any]) -> None:
    """Contrasta los índices persistentes con las tablas: reconstruye si hubo escritos ajenos.

    `io_n` solo crece con los vínculos que inserta el propio ciclo (se descuentan al
    confirmarlos); `o_n`/`o_max` detectan altas (se agregan al índice de días) y
    borrados o reemplazos (reconstrucción completa).
    """
    marks = tx.one("SELECT (SELECT COUNT(*) FROM incident_observations) AS io_n, "
                   "(SELECT COUNT(*) FROM observations) AS o_n, "
                   "(SELECT MAX(rowid) FROM observations) AS o_max")
    o_max = marks["o_max"] or 0
    grew = o_max - st["o_max"]
    if marks["io_n"] != st["io_n"] or marks["o_n"] != st["o_n"] + grew:
        st["pts"].clear()
        st["cells"].clear()
        st["agg"].clear()
        st["days"] = None
    elif grew > 0 and st["days"] is not None:
        for r in tx.query("SELECT lat, lon, observed_at FROM observations "
                          "WHERE rowid > ? AND confidence IN ('alta','nominal','media')", (st["o_max"],)):
            cell = (math.floor(r["lat"] / GRID_CELL_DEG), math.floor(r["lon"] / GRID_CELL_DEG))
            st["days"].setdefault(cell, []).append((r["lat"], r["lon"], r["observed_at"]))
    st["io_n"], st["o_n"], st["o_max"] = marks["io_n"], marks["o_n"], o_max


def _status(db: Database, inc: dict[str, Any], members: list[dict[str, Any]]) -> str:
    if inc.get("official_ref"):  # el estado lo fija CONAF (link_official), no la evidencia satelital
        return inc["status"] if inc["status"] in ("confirmado", "controlado", "extinguido") else "confirmado"
    reliable = [m for m in members if (m.get("confidence") or "") in RELIABLE]
    sensors = {m.get("sensor") for m in reliable}
    distinct_times = {m["observed_at"][:16] for m in reliable}
    since = _stamp(_t(inc["first_seen_at"]) - timedelta(hours=REPORT_HOURS))
    reports = db.query("SELECT lat, lon FROM reports WHERE status = 'verificado' AND created_at >= ?", (since,))
    if reliable and any(haversine_km(r["lat"], r["lon"], inc["lat"], inc["lon"]) <= REPORT_KM for r in reports):
        return "reportado"
    if len(sensors) >= 2:
        return "posible"
    if len(distinct_times) >= 2:
        if sensors != {"ABI"}:
            return "posible"
        # GOES como único sensor pide persistencia: dos barridos seguidos, o sea un par de
        # momentos consecutivos (tras ordenar) a ≤ GOES_PAIR_MINUTES; dos momentos lejanos no bastan.
        times = sorted(_t(f"{t}:00Z") for t in distinct_times)
        if any(b - a <= timedelta(minutes=GOES_PAIR_MINUTES) for a, b in zip(times, times[1:])):
            return "posible"
    return "anomalia"


def _refresh(db: Database, incident_id: str, now: datetime,
             members: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Recalcula centro, caja, conteos, sensores, FRP, fuente fija y estado de un incidente."""
    inc = db.one("SELECT * FROM incidents WHERE id = ?", (incident_id,))
    members = _members(db, incident_id) if members is None else members
    lats = [m["lat"] for m in members]
    lons = [m["lon"] for m in members]
    reliable = [m for m in members if (m.get("confidence") or "") in RELIABLE]
    frps = [m["frp_mw"] for m in members if m.get("frp_mw") is not None]
    comunas = [m["comuna_code"] for m in members if m.get("comuna_code")]
    fixed = all(is_fixed_source(db, m["lat"], m["lon"], now, sensor=m.get("sensor"),
                                observed_at=m["observed_at"]) for m in members) if members else False
    reason = None
    if fixed:
        reason = next((r for r in (fixed_reason(db, m["lat"], m["lon"], now, sensor=m.get("sensor"),
                                               observed_at=m["observed_at"]) for m in members) if r), None)
    inc.update({
        "lat": sum(lats) / len(lats), "lon": sum(lons) / len(lons),
        "min_lat": min(lats), "max_lat": max(lats), "min_lon": min(lons), "max_lon": max(lons),
        "first_seen_at": members[0]["observed_at"], "last_seen_at": members[-1]["observed_at"],
        "n_obs": len(members), "n_reliable": len(reliable),
        "sensors": ",".join(sorted({m.get("sensor") or "?" for m in members})),
        "max_frp": max(frps) if frps else None,
        "comuna_code": max(set(comunas), key=comunas.count) if comunas else None,
        "fixed_source": int(fixed),
        "fixed_reason": reason if fixed else None,
    })
    if inc["comuna_code"] is None:
        inc["comuna_code"] = _nearest_comuna(inc)
    status = _status(db, inc, members)
    if status != inc["status"]:
        inc["status"], inc["status_changed_at"] = status, _stamp(now)
    inc["updated_at"] = _stamp(now)
    db.execute("UPDATE incidents SET status=?, status_changed_at=?, first_seen_at=?, last_seen_at=?, lat=?, lon=?, min_lat=?, "
               "max_lat=?, min_lon=?, max_lon=?, n_obs=?, n_reliable=?, sensors=?, max_frp=?, comuna_code=?, fixed_source=?, "
               "fixed_reason=?, updated_at=? WHERE id=?",
               (inc["status"], inc["status_changed_at"], inc["first_seen_at"], inc["last_seen_at"], inc["lat"], inc["lon"],
                inc["min_lat"], inc["max_lat"], inc["min_lon"], inc["max_lon"], inc["n_obs"], inc["n_reliable"], inc["sensors"],
                inc["max_frp"], inc["comuna_code"], inc["fixed_source"], inc.get("fixed_reason"), inc["updated_at"], incident_id))
    return inc


def _status_fast(tx: _Tx, inc: dict[str, Any], agg: dict[str, Any]) -> str:
    """`_status` sobre los agregados del incidente: mismas reglas sin recorrer los miembros."""
    if inc.get("official_ref"):  # el estado lo fija CONAF (link_official), no la evidencia satelital
        return inc["status"] if inc["status"] in ("confirmado", "controlado", "extinguido") else "confirmado"
    if agg["n_rel"]:
        since = _stamp(_t(inc["first_seen_at"]) - timedelta(hours=REPORT_HOURS))
        reports = tx.query("SELECT lat, lon FROM reports WHERE status = 'verificado' AND created_at >= ?", (since,))
        if any(haversine_km(r["lat"], r["lon"], inc["lat"], inc["lon"]) <= REPORT_KM for r in reports):
            return "reportado"
    if len(agg["rel_sensors"]) >= 2:
        return "posible"
    if len(agg["rel_times"]) >= 2 and (agg["rel_sensors"] != {"ABI"} or agg["has_pair"]):
        return "posible"
    return "anomalia"


def _refresh_fast(tx: _Tx, inc: dict[str, Any], now: datetime, st: dict[str, Any],
                  fixed_ctx) -> dict[str, Any]:
    """`_refresh` sobre los agregados persistentes: mismo resultado sin recorrer la tabla.

    La lista de miembros solo se relee cuando `fixed` resulta verdadero y hay que hallar
    la primera razón en el orden de miembros de la tabla.
    """
    incident_id = inc["id"]
    agg = st["agg"].get(incident_id)
    if agg is None:
        agg = _agg_from_rows(_member_rows(tx, incident_id))
        st["agg"][incident_id] = agg
    n = len(agg["times"])
    fixed = False
    if n:
        ctx = fixed_ctx()
        fixed = all(is_fixed_source(tx, mlat, mlon, now, ctx, msensor, mt)
                    for mlat, mlon, msensor, mt in zip(agg["lats"], agg["lons"],
                                                       agg["sensors_seq"], agg["times"]))
    reason = None
    if fixed:
        reason = next((r for r in (fixed_reason(tx, m["lat"], m["lon"], now, ctx, m.get("sensor"),
                                                m["observed_at"])
                                   for m in _member_rows(tx, incident_id)) if r), None)
    inc.update({
        "lat": sum(agg["lats"]) / n, "lon": sum(agg["lons"]) / n,
        "min_lat": agg["min_lat"], "max_lat": agg["max_lat"], "min_lon": agg["min_lon"], "max_lon": agg["max_lon"],
        "first_seen_at": agg["times"][0], "last_seen_at": agg["times"][-1],
        "n_obs": n, "n_reliable": agg["n_rel"],
        "sensors": ",".join(sorted(agg["all_sensors"])),
        "max_frp": agg["max_frp"],
        "comuna_code": max(set(agg["comunas"]), key=agg["comunas"].count) if agg["comunas"] else None,
        "fixed_source": int(fixed),
        "fixed_reason": reason if fixed else None,
    })
    if inc["comuna_code"] is None:
        inc["comuna_code"] = _nearest_comuna(inc)
    status = _status_fast(tx, inc, agg)
    if status != inc["status"]:
        inc["status"], inc["status_changed_at"] = status, _stamp(now)
    inc["updated_at"] = _stamp(now)
    tx.execute("UPDATE incidents SET status=?, status_changed_at=?, first_seen_at=?, last_seen_at=?, lat=?, lon=?, min_lat=?, "
               "max_lat=?, min_lon=?, max_lon=?, n_obs=?, n_reliable=?, sensors=?, max_frp=?, comuna_code=?, fixed_source=?, "
               "fixed_reason=?, updated_at=? WHERE id=?",
               (inc["status"], inc["status_changed_at"], inc["first_seen_at"], inc["last_seen_at"], inc["lat"], inc["lon"],
                inc["min_lat"], inc["max_lat"], inc["min_lon"], inc["max_lon"], inc["n_obs"], inc["n_reliable"], inc["sensors"],
                inc["max_frp"], inc["comuna_code"], inc["fixed_source"], inc.get("fixed_reason"), inc["updated_at"], incident_id))
    return inc


def update(db: Database, observations: list[dict[str, Any]], now: datetime | None = None,
           linker: Linker | None = None) -> list[dict[str, Any]]:
    """Asigna las observaciones nuevas a incidentes (creando o fusionando) y devuelve los incidentes tocados.

    `linker` decide a qué incidentes candidatos se une cada detección (contrato en
    `single_link`); por defecto `LINKER`, el enlace simple vigente. Existe para comparar
    estrategias de agrupación (DET-09, `scripts/comparar_agrupacion.py`): la regla de
    producción no cambia.
    """
    now = now or datetime.now(timezone.utc)
    if not observations:
        return []
    link = linker or LINKER
    # FIX-15. Estado persistente entre ciclos (los vínculos solo cambian aquí y en prune):
    # - st["pts"]: puntos de miembros (lat, lon, resolution_m, observed_at) por celda
    #   GRID_CELL_DEG, agrupados por incidente;
    # - st["cells"]: celdas que ocupa cada incidente (para borrar sus puntos al fusionar);
    # - st["agg"]: agregados por incidente (sumas, extremos, sensores, momentos fiables);
    # - st["days"]: cuadrícula de días con calor para el patrón de fuente fija.
    # Por ciclo: una sola transacción, los incidentes abiertos indexados por su caja más
    # CAND_PAD_DEG, las detecciones precargadas de una vez y los vínculos confirmados en
    # lote. La distancia real por detección decide el toque igual que antes (las celdas solo
    # acotan la búsqueda) y _refresh_fast produce los mismos campos que _refresh.
    st = _state(db)
    with db.connect() as conn:
        tx = _Tx(conn)
        _sync(tx, st)

        live: dict[str, dict[str, Any]] = {}
        grid: dict[tuple[int, int], set[str]] = {}

        def index(inc: dict[str, Any]) -> None:
            live[inc["id"]] = inc
            for cell in _cells(inc["min_lat"] - CAND_PAD_DEG, inc["min_lon"] - CAND_PAD_DEG,
                               inc["max_lat"] + CAND_PAD_DEG, inc["max_lon"] + CAND_PAD_DEG):
                grid.setdefault(cell, set()).add(inc["id"])

        def grow(inc: dict[str, Any], lat0: float, lon0: float, lat1: float, lon1: float,
                 first: str, last: str) -> None:
            """Suma el alcance de miembros nuevos a la ficha indexada y reindexa la caja.

            QA-07: la caja y el rango temporal deben reflejar a los miembros ya enlazados
            dentro del mismo ciclo; si quedan congelados hasta el _refresh final, qué
            candidatos ve cada detección depende del orden en que fueron procesadas.
            """
            if first < inc["first_seen_at"]:
                inc["first_seen_at"] = first
            if last > inc["last_seen_at"]:
                inc["last_seen_at"] = last
            box = (min(inc["min_lat"], lat0), max(inc["max_lat"], lat1),
                   min(inc["min_lon"], lon0), max(inc["max_lon"], lon1))
            if box != (inc["min_lat"], inc["max_lat"], inc["min_lon"], inc["max_lon"]):
                inc["min_lat"], inc["max_lat"], inc["min_lon"], inc["max_lon"] = box
                for cell in _cells(box[0] - CAND_PAD_DEG, box[2] - CAND_PAD_DEG,
                                   box[1] + CAND_PAD_DEG, box[3] + CAND_PAD_DEG):
                    grid.setdefault(cell, set()).add(inc["id"])

        # FUEGO-23: además de los abiertos entran al ciclo los «extinguido» dentro de la
        # ventana de reapertura, medida desde la detección más vieja del lote para que una
        # que llega tarde encuentre igual al rescoldo que le corresponde.
        reopen_since = _stamp(min(_t(o["observed_at"]) for o in observations) - timedelta(hours=REOPEN_HOURS))
        for inc in tx.query(
                f"SELECT rowid, * FROM incidents WHERE status IN ({','.join('?' * len(OPEN_STATES))}) "
                "OR (status = 'extinguido' AND last_seen_at >= ?)",
                (*OPEN_STATES, reopen_since)):
            index(inc)

        def index_point(incident_id: str, row: dict[str, Any]) -> None:
            cell = (math.floor(row["lat"] / GRID_CELL_DEG), math.floor(row["lon"] / GRID_CELL_DEG))
            st["pts"].setdefault(cell, {}).setdefault(incident_id, []).append(
                (row["lat"], row["lon"], row.get("resolution_m"), row["observed_at"]))
            st["cells"][incident_id].add(cell)

        def drop_points(incident_id: str) -> None:
            for cell in st["cells"].pop(incident_id, ()):
                sub = st["pts"].get(cell)
                if sub is not None:
                    sub.pop(incident_id, None)
                    if not sub:
                        del st["pts"][cell]

        def ensure_points(incident_id: str) -> None:
            """Puntos y agregados del incidente: se leen una vez hasta que cambien sus miembros."""
            if incident_id in st["cells"]:
                return
            st["cells"][incident_id] = set()
            agg = _agg_new()
            for m in _member_rows(tx, incident_id):
                index_point(incident_id, m)
                _agg_add(agg, m)
            st["agg"][incident_id] = agg

        fctx_holder: list[dict[str, Any] | None] = [None]

        def fixed_ctx() -> dict[str, Any]:
            """Oficiales de la ventana e índice de días del patrón fijo: una vez por ciclo."""
            if fctx_holder[0] is None:
                days = st["days"]
                if days is None:
                    days = st["days"] = {}
                    for r in tx.query("SELECT lat, lon, observed_at FROM observations "
                                      "WHERE confidence IN ('alta','nominal','media')"):
                        cell = (math.floor(r["lat"] / GRID_CELL_DEG), math.floor(r["lon"] / GRID_CELL_DEG))
                        days.setdefault(cell, []).append((r["lat"], r["lon"], r["observed_at"]))
                fctx_holder[0] = {"days": days,
                                  "official": tx.query("SELECT lat, lon FROM official_fires "
                                                       "WHERE started_at >= ? OR started_at IS NULL",
                                                       (_stamp(now - timedelta(days=FIXED_WINDOW_DAYS)),))}
            return fctx_holder[0]

        # Los puntos/agregados de incidentes que ya no están abiertos (expiraron o se cerraron
        # por otra vía) no se vuelven a consultar nunca: se sueltan para no acumular memoria.
        for iid in set(st["cells"]) - set(live):
            drop_points(iid)
            st["agg"].pop(iid, None)

        # Las detecciones del lote con su vínculo previo, de una vez; los ids ausentes de la
        # tabla toman el camino lento (puede haber vínculo sin fila de observación).
        pre: dict[str, dict[str, Any]] = {}
        ids = [o["id"] for o in observations]
        for i in range(0, len(ids), 900):
            chunk = ids[i:i + 900]
            ph = ",".join("?" * len(chunk))
            for r in tx.query("SELECT o.id, o.lat, o.lon, o.resolution_m, o.observed_at, o.frp_mw, o.confidence, "
                              "o.sensor, o.comuna_code, EXISTS(SELECT 1 FROM incident_observations io "
                              "WHERE io.observation_id = o.id) AS linked FROM observations o "
                              f"WHERE o.id IN ({ph})", tuple(chunk)):
                pre[r["id"]] = r

        pending: list[tuple[str, str]] = []
        linked_ids: set[str] = set()

        def flush_links() -> None:
            if pending:
                cur = conn.executemany("INSERT OR IGNORE INTO incident_observations(observation_id, incident_id) "
                                       "VALUES (?, ?)", pending)
                st["io_n"] += cur.rowcount if cur.rowcount >= 0 else len(pending)
                pending.clear()

        touched: set[str] = set()
        for obs in sorted(observations, key=lambda o: o["observed_at"]):
            oid = obs["id"]
            pr = pre.get(oid)
            # FUEGO-12/FUEGO-04: una detección fuera del territorio no forma un incidente del
            # país. Se mira la coordenada (con el margen costero histórico de 0,16°), no la
            # comuna: un punto chileno del borde costero puede llegar sin comuna y aun así
            # es de Chile.
            if not inside_chile(obs["lat"], obs["lon"]):
                continue
            if oid in linked_ids:
                continue
            if pr is None:
                if tx.one("SELECT EXISTS(SELECT 1 FROM incident_observations WHERE observation_id = ?) AS x", (oid,))["x"]:
                    continue
                obs_row = None
            elif pr["linked"]:
                continue
            else:
                obs_row = pr
            linked_ids.add(oid)
            when = _t(obs["observed_at"])
            candidates = _candidates(live, grid, obs, when)
            for inc in candidates:
                ensure_points(inc["id"])
            olat, olon, ores = obs["lat"], obs["lon"], obs.get("resolution_m")
            lon_pad = LINK_PAD_DEG / max(0.1, math.cos(math.radians(olat)))
            cand_ids = {inc["id"] for inc in candidates}
            # Los puntos de cada candidato dentro del área de búsqueda y dentro de la ventana
            # temporal de la detección: el toque lo decide el linker contra los miembros, no
            # contra el centro del incidente. La cota por miembro hace que el vínculo entre
            # dos detecciones dependa solo del par —misma partición en cualquier orden de
            # llegada— y no de cuándo fue procesada cada una (QA-07).
            win_lo = _stamp(when - timedelta(hours=ACTIVE_HOURS))
            win_hi = _stamp(when + timedelta(hours=ACTIVE_HOURS))
            reopen_lo = _stamp(when - timedelta(hours=REOPEN_HOURS))
            near: dict[str, list[tuple[float, float, int | None, str]]] = {}
            for cell in _cells(olat - LINK_PAD_DEG, olon - lon_pad, olat + LINK_PAD_DEG, olon + lon_pad):
                for iid, plist in st["pts"].get(cell, {}).items():
                    if iid in cand_ids:
                        # FUEGO-23: los miembros de un «extinguido» quedaron fuera de la ventana
                        # activa, así que la suya se abre hasta REOPEN_HOURS; el toque lo decide
                        # igual la distancia del linker contra esos puntos.
                        lo = reopen_lo if live[iid]["status"] == "extinguido" else win_lo
                        near.setdefault(iid, []).extend(
                            p for p in plist
                            if abs(p[0] - olat) <= LINK_PAD_DEG and abs(p[1] - olon) <= lon_pad
                            and lo <= p[3] <= win_hi)
            touching = link(list(near.items()), olat, olon, ores, obs["observed_at"])
            matches = [inc for inc in candidates if inc["id"] in touching]
            if matches:
                target = matches[0]["id"]
                if len(matches) > 1:
                    flush_links()  # la reasignación de vínculos también alcanza los del lote
                    for other in matches[1:]:  # la detección une incidentes: se fusionan en el más antiguo
                        tx.execute("UPDATE incident_observations SET incident_id = ? WHERE incident_id = ?",
                                   (target, other["id"]))
                        # El id borrado queda como alias: los enlaces a su ficha guardados en avisos siguen abriendo.
                        tx.execute("INSERT OR REPLACE INTO incident_merges(dead_id, live_id, merged_at) VALUES (?,?,?)",
                                   (other["id"], target, _stamp(now)))
                        tx.execute("DELETE FROM incidents WHERE id = ?", (other["id"],))
                        live.pop(other["id"], None)
                        grow(live[target], other["min_lat"], other["min_lon"],
                             other["max_lat"], other["max_lon"],
                             other["first_seen_at"], other["last_seen_at"])
                        drop_points(other["id"])
                        st["agg"].pop(other["id"], None)
                        touched.discard(other["id"])
                    # Los miembros del objetivo cambiaron: se releen y se reindexan enteros.
                    drop_points(target)
                    st["agg"].pop(target, None)
            else:
                target = uuid.uuid4().hex[:12]
                stamp = obs["observed_at"]
                rowid = conn.execute("INSERT INTO incidents(id, status, status_changed_at, first_seen_at, last_seen_at, lat, lon, "
                                     "min_lat, max_lat, min_lon, max_lon, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                                     (target, "anomalia", _stamp(now), stamp, stamp, olat, olon, olat, olat, olon, olon,
                                      _stamp(now))).lastrowid
                index({"id": target, "status": "anomalia", "status_changed_at": _stamp(now), "official_ref": None,
                       "first_seen_at": stamp, "last_seen_at": stamp,
                       "min_lat": olat, "max_lat": olat, "min_lon": olon, "max_lon": olon, "rowid": rowid})
                st["cells"][target] = set()
                st["agg"][target] = _agg_new()
            pending.append((oid, target))
            if obs_row is not None:
                if target not in st["cells"]:
                    ensure_points(target)
                index_point(target, obs_row)
                _agg_add(st["agg"][target], obs_row)
            grow(live[target], olat, olon, olat, olon, obs["observed_at"], obs["observed_at"])
            touched.add(target)
        flush_links()
        return [_refresh_fast(tx, live[iid], now, st, fixed_ctx) for iid in touched]


def expire(db: Database, now: datetime | None = None) -> int:
    """Cierra los incidentes sin evidencia nueva. Los oficiales no se tocan (CONAF manda).

    Sin detecciones en 24 h → «extinguido» (según satélite). Sin comuna chilena →
    «descartado»: un fuego fuera del país no es un incendio chileno apagado, y llamarlo
    «extinguido» afirmaba algo falso (FUEGO-32). La misma pasada reetiqueta las filas que
    FUEGO-12 cerró como «extinguido» en producción; quedan en la tabla para auditoría y
    salen con la retención normal.
    """
    now = now or datetime.now(timezone.utc)
    cutoff = _stamp(now - timedelta(hours=EXTINGUISH_HOURS))
    discarded = db.execute("UPDATE incidents SET status = 'descartado', status_changed_at = ? "
                           "WHERE status IN ('anomalia','posible','reportado','extinguido') "
                           "AND official_ref IS NULL AND comuna_code IS NULL",
                           (_stamp(now),))
    extinct = db.execute("UPDATE incidents SET status = 'extinguido', status_changed_at = ? "
                         "WHERE status IN ('anomalia','posible','reportado') AND official_ref IS NULL "
                         "AND comuna_code IS NOT NULL AND last_seen_at < ?",
                         (_stamp(now), cutoff))
    return discarded + extinct


OFFICIAL_KM = 3.0          # un incendio informado por CONAF a ≤ 3 km (más medio píxel) de la evidencia
OFFICIAL_BEFORE_H = 6      # evidencia satelital desde 6 h antes del inicio oficial (el satélite a veces lo ve primero)


def link_official(db: Database, fires: list[dict[str, Any]], now: datetime | None = None) -> int:
    """Une los incendios que informa CONAF con los incidentes de BRASA y les da su estado oficial.

    Es la única vía a «confirmado»/«controlado» y la que cierra un incidente como «extinguido» según CONAF.
    """
    now = now or datetime.now(timezone.utc)
    linked = 0
    touched: set[str] = set()
    for fire in fires:
        start = _t(fire["started_at"])
        if fire["status"] == "extinguido" and now - start > timedelta(days=FIXED_WINDOW_DAYS):
            continue
        until = _stamp((_t(fire["extinguished_at"]) if fire.get("extinguished_at") else now) + timedelta(hours=1))
        pad = 0.05
        rows = db.query("SELECT * FROM incidents WHERE (official_ref = ? OR (official_ref IS NULL AND last_seen_at >= ? AND first_seen_at <= ? "
                        "AND min_lat - ? <= ? AND max_lat + ? >= ? AND min_lon - ? <= ? AND max_lon + ? >= ?))",
                        (fire["id"], _stamp(start - timedelta(hours=OFFICIAL_BEFORE_H)), until,
                         pad, fire["lat"], pad, fire["lat"], pad, fire["lon"], pad, fire["lon"]))
        for inc in rows:
            if inc["official_ref"] != fire["id"]:
                near = any(haversine_km(m["lat"], m["lon"], fire["lat"], fire["lon"]) <= OFFICIAL_KM + (m.get("resolution_m") or 375) / 2000
                           for m in _members(db, inc["id"]))
                if not near:
                    continue
            if inc["official_ref"] == fire["id"] and inc["status"] == fire["status"]:
                continue
            db.execute("UPDATE incidents SET official_ref = ?, status = ?, status_changed_at = ?, updated_at = ? WHERE id = ?",
                       (fire["id"], fire["status"], _stamp(now), _stamp(now), inc["id"]))
            linked += 1
            touched.add(inc["id"])
        if now - start <= timedelta(days=FIXED_WINDOW_DAYS):
            # La invalidación mide FIXED_KM y el vínculo OFFICIAL_KM: un incidente fijo entre ambas
            # distancias no se vincula pero sí debe perder el flag, o queda silenciado hasta que
            # llegue otra detección y provoque un _refresh.
            pad_fixed = 0.1
            fixed_near = db.query(
                f"SELECT * FROM incidents WHERE fixed_source = 1 AND status IN ({','.join('?' * len(OPEN_STATES))}) "
                "AND min_lat - ? <= ? AND max_lat + ? >= ? AND min_lon - ? <= ? AND max_lon + ? >= ?",
                (*OPEN_STATES, pad_fixed, fire["lat"], pad_fixed, fire["lat"], pad_fixed, fire["lon"], pad_fixed, fire["lon"]))
            for inc in fixed_near:
                if any(haversine_km(m["lat"], m["lon"], fire["lat"], fire["lon"]) <= FIXED_KM
                       for m in _members(db, inc["id"])):
                    touched.add(inc["id"])
    # Un incendio oficial cerca invalida la regla de «fuente fija»: hay que recalcular los flags de
    # los incidentes afectados, no esperar a la próxima detección (_refresh).
    for incident_id in touched:
        _refresh(db, incident_id, now)
    return linked


def resolve_merge(db: Database, incident_id: str) -> dict[str, Any] | None:
    """La fila vigente del incidente que absorbe a `incident_id`, o None si no existe.

    Un aviso guarda el enlace a la ficha y una fusión posterior borra el id: sin alias, abrir el
    aviso devolvería 404. Las fusiones van siempre hacia el más antiguo y pueden encadenarse.
    """
    current, seen = incident_id, set()
    while current not in seen:
        seen.add(current)
        row = db.one("SELECT live_id FROM incident_merges WHERE dead_id = ?", (current,))
        if row is None:
            break
        current = row["live_id"]
    return db.one("SELECT * FROM incidents WHERE id = ?", (current,))


def prune(db: Database, cutoff: str) -> None:
    """Tras la retención de observaciones: borra vínculos huérfanos e incidentes cerrados sin evidencia."""
    db._inc_state = None  # retención: miembros y vínculos cambian fuera de update (FIX-15)
    db.execute("DELETE FROM incident_observations WHERE observation_id NOT IN (SELECT id FROM observations)")
    db.execute("DELETE FROM incidents WHERE last_seen_at < ? AND official_ref IS NULL "
               "AND id NOT IN (SELECT incident_id FROM incident_observations)", (cutoff,))


def incident_of(db: Database, observation_id: str) -> dict[str, Any] | None:
    return db.one("SELECT i.* FROM incidents i JOIN incident_observations io ON io.incident_id = i.id "
                  "WHERE io.observation_id = ?", (observation_id,))


def members(db: Database, incident_id: str) -> list[dict[str, Any]]:
    return _members(db, incident_id)

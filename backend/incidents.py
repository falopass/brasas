"""Incidentes: la evidencia satelital agrupada en el espacio y el tiempo.

Un punto de calor no es un incendio. BRASA junta las detecciones cercanas en un *incidente* y le da un estado
según cuánta evidencia independiente hay, sin presentarse nunca como fuente oficial:

- anomalia:   una sola detección (o solo de confianza baja). Puede ser fuego, una quema o una industria.
- posible:    dos o más detecciones confiables en momentos distintos, o vista por dos sensores distintos.
- reportado:  además hay un aviso ciudadano verificado por moderación cerca y a la misma hora.
- confirmado: una fuente oficial (CONAF/SENAPRED) lo reconoce (official_ref). BRASA no confirma por su cuenta.
- extinguido: 24 h sin detecciones nuevas (sin evidencia satelital, no «apagado oficialmente»).

Fuentes de calor fijas probables (industria, antorchas, volcanes): si TODA la evidencia de un incidente cae en
una de ellas, se marca fixed_source y no genera aviso automático. Basta una detección fuera para avisar normal.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any

from backend.db import Database
from backend.geo import haversine_km
from backend.settings import ROOT

RELIABLE = {"alta", "nominal", "media"}
ACTIVE_HOURS = 6          # una detección se une a incidentes vistos en las últimas 6 h
EXTINGUISH_HOURS = 24     # sin detecciones en 24 h → extinguido (según satélite)
FIXED_DAYS = 8            # celda con detecciones en ≥ 8 días distintos en 30 días → fuente fija probable
FIXED_WINDOW_DAYS = 30
FIXED_CELL_DEG = 0.02     # ~2 km
REPORT_KM, REPORT_HOURS = 3.0, 12
OPEN_STATES = ("anomalia", "posible", "reportado", "confirmado", "controlado")


def _t(stamp: str) -> datetime:
    return datetime.fromisoformat(stamp.replace("Z", "+00:00"))


def _stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def link_km(res_a_m: int | None, res_b_m: int | None) -> float:
    """Distancia máxima para considerar dos detecciones parte del mismo fuego: 2 km + media de las resoluciones."""
    return 2.0 + ((res_a_m or 375) + (res_b_m or 375)) / 2000.0


@lru_cache(maxsize=1)
def known_fixed_sources() -> list[dict[str, Any]]:
    """Fuentes fijas conocidas (volcanes activos), con su radio. Archivo editable con fuente de cada punto."""
    path = ROOT / "web" / "data" / "persistent_hotspots.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))["sources"]
    except (OSError, ValueError, KeyError):
        return []


def is_fixed_source(db: Database, lat: float, lon: float, now: datetime) -> bool:
    for src in known_fixed_sources():
        if haversine_km(lat, lon, src["lat"], src["lon"]) <= src["radius_km"]:
            return True
    # Celda que «arde» muchos días distintos en el mismo lugar: industria o antorcha, no un incendio que avanza.
    half = FIXED_CELL_DEG / 2
    since = _stamp(now - timedelta(days=FIXED_WINDOW_DAYS))
    row = db.one("SELECT COUNT(DISTINCT substr(observed_at, 1, 10)) AS days FROM observations "
                 "WHERE observed_at >= ? AND lat BETWEEN ? AND ? AND lon BETWEEN ? AND ? AND confidence IN ('alta','nominal','media')",
                 (since, lat - half, lat + half, lon - half, lon + half))
    return bool(row and row["days"] >= FIXED_DAYS)


def _members(db: Database, incident_id: str) -> list[dict[str, Any]]:
    return db.query("SELECT o.* FROM observations o JOIN incident_observations io ON io.observation_id = o.id "
                    "WHERE io.incident_id = ? ORDER BY o.observed_at", (incident_id,))


def _candidates(db: Database, obs: dict[str, Any], when: datetime) -> list[dict[str, Any]]:
    pad = 0.06  # ~6 km: margen holgado; la distancia real se mide contra cada detección
    since = _stamp(when - timedelta(hours=ACTIVE_HOURS))
    return db.query(
        f"SELECT * FROM incidents WHERE status IN ({','.join('?' * len(OPEN_STATES))}) AND last_seen_at >= ? "
        "AND min_lat - ? <= ? AND max_lat + ? >= ? AND min_lon - ? <= ? AND max_lon + ? >= ? ORDER BY first_seen_at",
        (*OPEN_STATES, since, pad, obs["lat"], pad, obs["lat"], pad, obs["lon"], pad, obs["lon"]))


def _touches(db: Database, incident: dict[str, Any], obs: dict[str, Any]) -> bool:
    return any(haversine_km(m["lat"], m["lon"], obs["lat"], obs["lon"]) <= link_km(m.get("resolution_m"), obs.get("resolution_m"))
               for m in _members(db, incident["id"]))


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
    if len(sensors) >= 2 or len(distinct_times) >= 2:
        return "posible"
    return "anomalia"


def _refresh(db: Database, incident_id: str, now: datetime) -> dict[str, Any]:
    """Recalcula centro, caja, conteos, sensores, FRP, fuente fija y estado de un incidente."""
    inc = db.one("SELECT * FROM incidents WHERE id = ?", (incident_id,))
    members = _members(db, incident_id)
    lats = [m["lat"] for m in members]
    lons = [m["lon"] for m in members]
    reliable = [m for m in members if (m.get("confidence") or "") in RELIABLE]
    frps = [m["frp_mw"] for m in members if m.get("frp_mw") is not None]
    comunas = [m["comuna_code"] for m in members if m.get("comuna_code")]
    fixed = all(is_fixed_source(db, m["lat"], m["lon"], now) for m in members) if members else False
    inc.update({
        "lat": sum(lats) / len(lats), "lon": sum(lons) / len(lons),
        "min_lat": min(lats), "max_lat": max(lats), "min_lon": min(lons), "max_lon": max(lons),
        "first_seen_at": members[0]["observed_at"], "last_seen_at": members[-1]["observed_at"],
        "n_obs": len(members), "n_reliable": len(reliable),
        "sensors": ",".join(sorted({m.get("sensor") or "?" for m in members})),
        "max_frp": max(frps) if frps else None,
        "comuna_code": max(set(comunas), key=comunas.count) if comunas else None,
        "fixed_source": int(fixed),
    })
    status = _status(db, inc, members)
    if status != inc["status"]:
        inc["status"], inc["status_changed_at"] = status, _stamp(now)
    inc["updated_at"] = _stamp(now)
    db.execute("UPDATE incidents SET status=?, status_changed_at=?, first_seen_at=?, last_seen_at=?, lat=?, lon=?, min_lat=?, "
               "max_lat=?, min_lon=?, max_lon=?, n_obs=?, n_reliable=?, sensors=?, max_frp=?, comuna_code=?, fixed_source=?, "
               "updated_at=? WHERE id=?",
               (inc["status"], inc["status_changed_at"], inc["first_seen_at"], inc["last_seen_at"], inc["lat"], inc["lon"],
                inc["min_lat"], inc["max_lat"], inc["min_lon"], inc["max_lon"], inc["n_obs"], inc["n_reliable"], inc["sensors"],
                inc["max_frp"], inc["comuna_code"], inc["fixed_source"], inc["updated_at"], incident_id))
    return inc


def update(db: Database, observations: list[dict[str, Any]], now: datetime | None = None) -> list[dict[str, Any]]:
    """Asigna las observaciones nuevas a incidentes (creando o fusionando) y devuelve los incidentes tocados."""
    now = now or datetime.now(timezone.utc)
    touched: set[str] = set()
    for obs in sorted(observations, key=lambda o: o["observed_at"]):
        if db.one("SELECT 1 FROM incident_observations WHERE observation_id = ?", (obs["id"],)):
            continue
        when = _t(obs["observed_at"])
        matches = [inc for inc in _candidates(db, obs, when) if _touches(db, inc, obs)]
        if matches:
            target = matches[0]["id"]
            for other in matches[1:]:  # la detección une dos incidentes: se fusionan en el más antiguo
                db.execute("UPDATE incident_observations SET incident_id = ? WHERE incident_id = ?", (target, other["id"]))
                # El id borrado queda como alias: los enlaces a su ficha guardados en avisos siguen abriendo.
                db.execute("INSERT OR REPLACE INTO incident_merges(dead_id, live_id, merged_at) VALUES (?,?,?)",
                           (other["id"], target, _stamp(now)))
                db.execute("DELETE FROM incidents WHERE id = ?", (other["id"],))
                touched.discard(other["id"])
        else:
            target = uuid.uuid4().hex[:12]
            stamp = obs["observed_at"]
            db.execute("INSERT INTO incidents(id, status, status_changed_at, first_seen_at, last_seen_at, lat, lon, min_lat, max_lat, "
                       "min_lon, max_lon, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                       (target, "anomalia", _stamp(now), stamp, stamp, obs["lat"], obs["lon"], obs["lat"], obs["lat"],
                        obs["lon"], obs["lon"], _stamp(now)))
        db.execute("INSERT OR IGNORE INTO incident_observations(observation_id, incident_id) VALUES (?, ?)", (obs["id"], target))
        touched.add(target)
    return [_refresh(db, incident_id, now) for incident_id in touched]


def expire(db: Database, now: datetime | None = None) -> int:
    """Incidentes sin detecciones en 24 h pasan a «extinguido» (según satélite). Los oficiales no se tocan."""
    now = now or datetime.now(timezone.utc)
    cutoff = _stamp(now - timedelta(hours=EXTINGUISH_HOURS))
    return db.execute("UPDATE incidents SET status = 'extinguido', status_changed_at = ? "
                      "WHERE status IN ('anomalia','posible','reportado') AND official_ref IS NULL AND last_seen_at < ?",
                      (_stamp(now), cutoff))


OFFICIAL_KM = 3.0          # un incendio informado por CONAF a ≤ 3 km (más medio píxel) de la evidencia
OFFICIAL_BEFORE_H = 6      # evidencia satelital desde 6 h antes del inicio oficial (el satélite a veces lo ve primero)


def link_official(db: Database, fires: list[dict[str, Any]], now: datetime | None = None) -> int:
    """Une los incendios que informa CONAF con los incidentes de BRASA y les da su estado oficial.

    Es la única vía a «confirmado»/«controlado» y la que cierra un incidente como «extinguido» según CONAF.
    """
    now = now or datetime.now(timezone.utc)
    linked = 0
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
    db.execute("DELETE FROM incident_observations WHERE observation_id NOT IN (SELECT id FROM observations)")
    db.execute("DELETE FROM incidents WHERE last_seen_at < ? AND official_ref IS NULL "
               "AND id NOT IN (SELECT incident_id FROM incident_observations)", (cutoff,))


def incident_of(db: Database, observation_id: str) -> dict[str, Any] | None:
    return db.one("SELECT i.* FROM incidents i JOIN incident_observations io ON io.incident_id = i.id "
                  "WHERE io.observation_id = ?", (observation_id,))


def members(db: Database, incident_id: str) -> list[dict[str, Any]]:
    return _members(db, incident_id)

"""Cicatrices de la temporada: unión por comuna de las huellas de detecciones (AGUA-01).

Cada incidente aporta la unión de sus píxeles calientes confiables (medio píxel de radio
por sensor, el mismo criterio de la ficha del incidente y de los casos históricos), y las
huellas se unen por comuna. NO es el perímetro oficial ni el área quemada que medirá el
dNBR de Sentinel-2: es la zona donde los satélites vieron calor, base del futuro riesgo
de aluvión post-incendio (docs/ALUVIONES.md).
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from typing import Any

from shapely import transform
from shapely.geometry import Point, mapping, shape
from shapely.ops import unary_union

from backend import cases as cases_mod
from backend import incidents as incidents_mod
from backend.db import Database
from backend.geo import territory

# Tope de incidentes por consulta: la cicatriz es un producto de temporada y cada
# incidente exige traer sus observaciones; con más, la respuesta lo declara.
MAX_INCIDENTS = 300


def _coherent_coords(obs: dict[str, Any]) -> bool:
    """lat/lon finitas y dentro del mundo: un dato corrupto no puede llevar la
    cicatriz fuera de EPSG:4326 ni deformar la unión de su comuna."""
    try:
        lat, lon = float(obs["lat"]), float(obs["lon"])
    except (TypeError, ValueError, KeyError):
        return False
    return math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180


def _incident_footprint(members: list[dict[str, Any]]):
    """Unión de los píxeles calientes confiables del incidente, en grados (WGS84)."""
    good = [o for o in members if cases_mod.usable(o) and _coherent_coords(o)]
    if not good:
        return None
    lat0 = sum(o["lat"] for o in good) / len(good)
    lon0 = sum(o["lon"] for o in good) / len(good)
    plane = cases_mod.LocalPlane(lat0, lon0)
    shapes = [Point(*plane.to_km(o["lon"], o["lat"])).buffer(cases_mod.HALF_PIXEL_KM.get(o.get("sensor"), 0.5), quad_segs=3) for o in good]
    # 100 m de tolerancia: baja el número de vértices sin cambiar la forma a escala comunal.
    return transform(unary_union(shapes).simplify(0.1), plane.to_deg)


def _to_km(plane: cases_mod.LocalPlane):
    """Proyección vectorizada (Nx2) al plano local de la comuna, espejo de `to_deg`."""

    def project(xy):
        return (xy - (plane.lon0, plane.lat0)) * (plane.kx, plane.ky)

    return project


# Una huella cuenta para la ladera solo si cae en este disco. Más lejos, aunque sea
# la misma comuna, es otra cuenca (AGUA-02).
RADIO_CERCANO_KM = 5.0

# Las huellas guardadas duran 400 días: el aluvión post-incendio pasa de un año, así que la
# ventana de 365 del cruce necesita holgura (Quebrada Honda aluvionó 283 días después del
# incendio Plaza Sur; la retención de observaciones de 45 días no lo habría visto).
FOOTPRINT_DAYS = 400
CONAF_MIN_HA = 10.0  # el cruce solo mira incendios de CONAF de esta superficie en adelante


def _since(days: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _dias_desde(at: str | None) -> int | None:
    """Días enteros desde una marca `…T…Z` hasta ahora; None si no se puede leer."""
    if not at:
        return None
    try:
        momento = datetime.strptime(at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return max(0, (datetime.now(timezone.utc) - momento).days)


def _footprint_ha(footprint) -> float:
    """Área de una huella en grados, en hectáreas, medida en el plano local de su centro."""
    centro = footprint.centroid
    plane = cases_mod.LocalPlane(centro.y, centro.x)
    return transform(footprint, _to_km(plane)).area * 100.0


def snapshot_footprints(db: Database, since: str) -> int:
    """Guarda en `scar_footprints` la huella de cada incidente vivo (AGUA-01).

    Upsert de los incidentes `status != 'descartado' AND fixed_source = 0` con
    `last_seen_at >= since`. La huella solo se recalcula cuando cambió `last_seen_at`:
    el incidente no crece hacia atrás. Si un incidente guardado pasa después a descartado
    o a fuente fija, su fila se borra: no es suelo quemado. La fila sobrevive a la
    retención que borra observaciones e incidentes — para eso existe la tabla.
    """
    db.execute(
        "DELETE FROM scar_footprints WHERE incident_id IN "
        "(SELECT id FROM incidents WHERE status = 'descartado' OR fixed_source != 0)"
    )
    rows = db.query(
        "SELECT id, first_seen_at, last_seen_at, min_lat, max_lat, min_lon, max_lon FROM incidents "
        "WHERE status != 'descartado' AND fixed_source = 0 AND last_seen_at >= ? "
        "ORDER BY last_seen_at DESC LIMIT ?",
        (since, MAX_INCIDENTS),
    )
    stored = {
        r["incident_id"]: r["last_seen_at"]
        for r in db.query("SELECT incident_id, last_seen_at FROM scar_footprints")
    }
    n = 0
    for row in rows:
        if stored.get(row["id"]) == row["last_seen_at"]:
            continue
        footprint = _incident_footprint(incidents_mod.members(db, row["id"]))
        if footprint is None or footprint.is_empty:
            continue
        db.execute(
            "INSERT INTO scar_footprints(incident_id, first_seen_at, last_seen_at, "
            "min_lat, max_lat, min_lon, max_lon, ha, geojson) VALUES (?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(incident_id) DO UPDATE SET first_seen_at = excluded.first_seen_at, "
            "last_seen_at = excluded.last_seen_at, min_lat = excluded.min_lat, max_lat = excluded.max_lat, "
            "min_lon = excluded.min_lon, max_lon = excluded.max_lon, ha = excluded.ha, geojson = excluded.geojson",
            (
                row["id"], row["first_seen_at"], row["last_seen_at"],
                row["min_lat"], row["max_lat"], row["min_lon"], row["max_lon"],
                round(_footprint_ha(footprint), 1),
                json.dumps(mapping(footprint), separators=(",", ":")),
            ),
        )
        n += 1
    return n


def prune_footprints(db: Database, days: int = FOOTPRINT_DAYS) -> int:
    """Borra las huellas guardadas más viejas que `days` (400 por defecto)."""
    return db.execute("DELETE FROM scar_footprints WHERE last_seen_at < ?", (_since(days),))


def _satelite_cerca(db: Database, lat: float, lon: float, days: int, radio_km: float) -> dict[str, Any]:
    """Huellas satelitales en el disco del punto: hectáreas y la `last_seen_at` más reciente.

    Lee primero `scar_footprints` (la huella sobrevive a la retención de 45 días) y calcula
    al vuelo la de los incidentes vivos que todavía no tienen fila guardada.
    """
    since = _since(days)
    # La caja incluye el medio píxel ABI (1,5 km): el bbox del incidente es el centro
    # de las detecciones, y la huella se extiende un poco más.
    margen = radio_km + 2.0
    dlat = margen / 110.574
    dlon = margen / (111.320 * max(math.cos(math.radians(lat)), 0.2))
    guardadas = db.query(
        "SELECT incident_id, last_seen_at, geojson FROM scar_footprints WHERE last_seen_at >= ? "
        "AND max_lat >= ? AND min_lat <= ? AND max_lon >= ? AND min_lon <= ? "
        "ORDER BY last_seen_at DESC LIMIT ?",
        (since, lat - dlat, lat + dlat, lon - dlon, lon + dlon, MAX_INCIDENTS),
    )
    cubiertas = {r["incident_id"] for r in guardadas}
    candidatas = [(shape(json.loads(r["geojson"])), r["last_seen_at"]) for r in guardadas]
    vivas = db.query(
        "SELECT id, last_seen_at FROM incidents WHERE status != 'descartado' AND fixed_source = 0 "
        "AND last_seen_at >= ? AND max_lat >= ? AND min_lat <= ? AND max_lon >= ? AND min_lon <= ? "
        "ORDER BY last_seen_at DESC LIMIT ?",
        (since, lat - dlat, lat + dlat, lon - dlon, lon + dlon, MAX_INCIDENTS),
    )
    for row in vivas:
        if row["id"] in cubiertas:
            continue
        footprint = _incident_footprint(incidents_mod.members(db, row["id"]))
        if footprint is not None and not footprint.is_empty:
            candidatas.append((footprint, row["last_seen_at"]))
    plane = cases_mod.LocalPlane(lat, lon)
    disco = Point(0.0, 0.0).buffer(radio_km, quad_segs=6)
    total = 0.0
    ultimo_at: str | None = None
    for footprint, seen_at in candidatas:
        cruce = transform(footprint, _to_km(plane)).intersection(disco)
        if cruce.is_empty:
            continue
        total += cruce.area * 100.0
        ultimo_at = max(ultimo_at, seen_at) if ultimo_at else seen_at
    return {"ha": round(total, 1), "ultimo_at": ultimo_at}


def scar_ha_cerca(
    db: Database,
    lat: float,
    lon: float,
    days: int = 180,
    radio_km: float = RADIO_CERCANO_KM,
) -> float:
    """Hectáreas de huella de calor a ≤ `radio_km` del punto, en los últimos `days` días.

    Intersecta la huella de cada incidente (píxeles confiables, igual que `season_scars`)
    con el disco en el plano local del punto. No suma la comuna: una cicatriz a 30 km
    no marca esta ladera. 0.0 si no hay nada en el disco.
    """
    if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
        return 0.0
    if radio_km <= 0:
        return 0.0
    return _satelite_cerca(db, lat, lon, days, radio_km)["ha"]


def conaf_ha_cerca(
    db: Database,
    lat: float,
    lon: float,
    days: int = 365,
    radio_km: float = RADIO_CERCANO_KM,
    min_ha: float = CONAF_MIN_HA,
) -> dict[str, Any]:
    """Hectáreas quemadas según CONAF a ≤ `radio_km` del punto, en los últimos `days` días.

    Lee `conaf_cicatrices` (temporada anterior) y `official_fires` (temporada en curso),
    sin duplicar los ids, y aproxima cada incendio como un disco de área equivalente —
    radio ``sqrt(ha / 100 / π)`` km— centrado en su punto de inicio. Es una aproximación:
    el punto que publica CONAF es donde empezó el fuego, no su centro, y el disco puede
    tocar lugares que el incendio real no quemó (o al revés). Devuelve ``{"ha", "incendio"}``,
    donde `incendio` es el de mayor superficie intersectada, o None.
    """
    vacio = {"ha": 0.0, "incendio": None}
    if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
        return vacio
    if radio_km <= 0:
        return vacio
    since = _since(days)
    rows = db.query(
        "SELECT id, nombre, comuna, lat, lon, ha, inicio FROM conaf_cicatrices WHERE inicio >= ? AND ha >= ?",
        (since, min_ha),
    )
    cubiertos = {r["id"] for r in rows}
    rows += [
        r
        for r in db.query(
            "SELECT id, name AS nombre, comuna, lat, lon, area_ha AS ha, started_at AS inicio "
            "FROM official_fires WHERE started_at >= ? AND area_ha >= ?",
            (since, min_ha),
        )
        if r["id"] not in cubiertos
    ]
    plane = cases_mod.LocalPlane(lat, lon)
    disco = Point(0.0, 0.0).buffer(radio_km, quad_segs=6)
    total = 0.0
    mejor: dict[str, Any] | None = None
    mejor_ha = 0.0
    for row in rows:
        r_km = math.sqrt(row["ha"] / 100.0 / math.pi)
        x, y = plane.to_km(row["lon"], row["lat"])
        if math.hypot(x, y) > radio_km + r_km:
            continue
        cruce = Point(x, y).buffer(r_km, quad_segs=6).intersection(disco)
        if cruce.is_empty:
            continue
        ha = cruce.area * 100.0
        total += ha
        if ha > mejor_ha:
            mejor, mejor_ha = row, ha
    incendio = None
    if mejor is not None:
        incendio = {"id": mejor["id"], "nombre": mejor["nombre"], "comuna": mejor["comuna"],
                    "inicio": mejor["inicio"], "ha": mejor["ha"]}
    return {"ha": round(total, 1), "incendio": incendio}


def cicatriz_cerca(db: Database, lat: float, lon: float, days: int = 365) -> dict[str, Any]:
    """La cicatriz en un punto, juntando las dos fuentes en una sola lectura (AGUA-01).

    ``ha`` es el máximo de la huella satelital y de la superficie CONAF cercana, no la suma:
    un mismo incendio puede estar en las dos fuentes y no se cuenta dos veces. ``dias_desde``
    son los días enteros desde el `inicio` del incendio de CONAF informado, o desde el
    `last_seen_at` de la huella satelital más reciente si no hay incendio de CONAF.
    """
    satelite = _satelite_cerca(db, lat, lon, days, RADIO_CERCANO_KM)
    conaf = conaf_ha_cerca(db, lat, lon, days=days)
    ha_satelite, ha_conaf = satelite["ha"], conaf["ha"]
    fuente = None
    if ha_satelite or ha_conaf:
        fuente = "conaf" if ha_conaf >= ha_satelite else "satelite"
    incendio = conaf["incendio"]
    if incendio is not None:
        dias = _dias_desde(incendio.get("inicio"))
    else:
        dias = _dias_desde(satelite["ultimo_at"])
    return {
        "ha": max(ha_satelite, ha_conaf),
        "ha_satelite": ha_satelite,
        "ha_conaf": ha_conaf,
        "incendio": incendio,
        "dias_desde": dias,
        "fuente": fuente,
    }


def season_scars(db: Database, days: int, comuna_code: int | None = None) -> dict[str, Any]:
    """FeatureCollection: una geometría por comuna con la huella unida de sus incidentes.

    Entran los incidentes vistos en la ventana que no fueron descartados ni marcados como
    fuente de calor fija probable (volcanes, industria: calor sin suelo quemado). También
    entran las anomalías: una detección suelta que no alcanzó el umbral de «posible» sigue
    siendo una zona donde el satélite vio calor, y eso es lo que mide la cicatriz, no la
    superficie quemada con evidencia (SCARS-02). Los incidentes sin comuna asignada quedan
    fuera de la geometría a propósito —la atribución por cercanía es una decisión abierta
    (FUEGO-61)— pero se cuentan en `incidents_examined` y la respuesta declara cuántos son
    en `sin_comuna`, para que la capa no subestime el suelo quemado en silencio.

    Con `comuna_code` el filtro va en la consulta, no después: la ficha de una sola
    comuna no paga el tope de temporada de las demás.
    """
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    sql = (
        "SELECT id, comuna_code, first_seen_at, last_seen_at FROM incidents "
        "WHERE status != 'descartado' AND fixed_source = 0 AND last_seen_at >= ? "
    )
    params: list[Any] = [since]
    if comuna_code is not None:
        sql += "AND comuna_code = ? "
        params.append(comuna_code)
    sql += "ORDER BY last_seen_at DESC LIMIT ?"
    params.append(MAX_INCIDENTS + 1)
    rows = db.query(sql, tuple(params))
    truncated = len(rows) > MAX_INCIDENTS
    rows = rows[:MAX_INCIDENTS]
    t = territory()
    by_comuna: dict[int, dict[str, Any]] = {}
    sin_comuna = 0
    for row in rows:
        if row["comuna_code"] is None:
            sin_comuna += 1
            continue
        footprint = _incident_footprint(incidents_mod.members(db, row["id"]))
        if footprint is None:
            continue
        group = by_comuna.setdefault(
            row["comuna_code"], {"geoms": [], "n_incidentes": 0, "desde": row["first_seen_at"], "hasta": row["last_seen_at"]}
        )
        group["geoms"].append(footprint)
        group["n_incidentes"] += 1
        group["desde"] = min(group["desde"], row["first_seen_at"])
        group["hasta"] = max(group["hasta"], row["last_seen_at"])
    features = []
    for code, group in sorted(by_comuna.items()):
        comuna = t.by_code.get(code)
        if comuna is None:
            continue
        scar = unary_union(group["geoms"])
        # El área se mide en el plano local centrado en la comuna, no en grados.
        plane = cases_mod.LocalPlane(comuna.center[1], comuna.center[0])
        ha = transform(scar, _to_km(plane)).area * 100
        features.append(
            {
                "type": "Feature",
                "geometry": json.loads(json.dumps(mapping(scar)), parse_float=lambda v: round(float(v), 5)),
                "properties": {
                    "comuna": comuna.name,
                    "comuna_code": code,
                    "region": comuna.region,
                    "ha": round(ha),
                    "n_incidentes": group["n_incidentes"],
                    "desde": group["desde"],
                    "hasta": group["hasta"],
                },
            }
        )
    return {
        "type": "FeatureCollection",
        "features": features,
        "incidents_examined": len(rows),
        "incidents_limit": MAX_INCIDENTS,
        "incidents_truncated": truncated,
        "sin_comuna": sin_comuna,
    }

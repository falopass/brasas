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
from shapely.geometry import Point, mapping
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
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    # La caja incluye el medio píxel ABI (1,5 km): el bbox del incidente es el centro
    # de las detecciones, y la huella se extiende un poco más.
    margen = radio_km + 2.0
    dlat = margen / 110.574
    dlon = margen / (111.320 * max(math.cos(math.radians(lat)), 0.2))
    rows = db.query(
        "SELECT id FROM incidents WHERE status != 'descartado' AND fixed_source = 0 "
        "AND last_seen_at >= ? AND max_lat >= ? AND min_lat <= ? AND max_lon >= ? AND min_lon <= ? "
        "ORDER BY last_seen_at DESC LIMIT ?",
        (since, lat - dlat, lat + dlat, lon - dlon, lon + dlon, MAX_INCIDENTS),
    )
    if not rows:
        return 0.0
    plane = cases_mod.LocalPlane(lat, lon)
    disco = Point(0.0, 0.0).buffer(radio_km, quad_segs=6)
    total = 0.0
    for row in rows:
        footprint = _incident_footprint(incidents_mod.members(db, row["id"]))
        if footprint is None or footprint.is_empty:
            continue
        cruce = transform(footprint, _to_km(plane)).intersection(disco)
        if not cruce.is_empty:
            total += cruce.area * 100.0
    return round(total, 1)


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

"""Cicatrices de la temporada: unión por comuna de las huellas de detecciones (AGUA-01).

Cada incidente aporta la unión de sus píxeles calientes confiables (medio píxel de radio
por sensor, el mismo criterio de la ficha del incidente y de los casos históricos), y las
huellas se unen por comuna. NO es el perímetro oficial ni el área quemada que medirá el
dNBR de Sentinel-2: es la zona donde los satélites vieron calor, base del futuro riesgo
de aluvión post-incendio (docs/ALUVIONES.md).
"""

from __future__ import annotations

import json
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


def _incident_footprint(members: list[dict[str, Any]]):
    """Unión de los píxeles calientes confiables del incidente, en grados (WGS84)."""
    good = [o for o in members if cases_mod.usable(o)]
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


def season_scars(db: Database, days: int) -> dict[str, Any]:
    """FeatureCollection: una geometría por comuna con la huella unida de sus incidentes.

    Entran los incidentes vistos en la ventana que no fueron descartados ni marcados como
    fuente de calor fija probable (volcanes, industria: calor sin suelo quemado).
    """
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = db.query(
        "SELECT id, comuna_code, first_seen_at, last_seen_at FROM incidents "
        "WHERE status != 'descartado' AND fixed_source = 0 AND last_seen_at >= ? "
        "ORDER BY last_seen_at DESC LIMIT ?",
        (since, MAX_INCIDENTS + 1),
    )
    truncated = len(rows) > MAX_INCIDENTS
    rows = rows[:MAX_INCIDENTS]
    t = territory()
    by_comuna: dict[int, dict[str, Any]] = {}
    for row in rows:
        if row["comuna_code"] is None:
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
    }

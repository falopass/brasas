"""Reconstrucción de casos históricos: detecciones reales + reanálisis + huella acumulada.

La "huella de detecciones" es la unión de los píxeles calientes observados hasta cada hora
(medio píxel de radio por sensor). NO es el perímetro oficial ni el área quemada: muestra dónde
y cuándo los satélites registraron calor. Los vacíos entre pasadas no se interpolan.

El catálogo (cases.json) se relee cuando cambian el mtime, el tamaño o el inodo del archivo,
porque los scripts de reconstrucción lo regeneran en caliente, sin reiniciar el proceso.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Any

import numpy as np
from shapely import transform
from shapely.geometry import Point, mapping
from shapely.ops import unary_union

from backend.settings import ROOT

DATA = ROOT / "web" / "data"
CONF_FROM_CODE = {2: "alta", 1: "media", 0: "baja"}
HALF_PIXEL_KM = {"ABI": 1.5, "VIIRS": 0.19, "MODIS": 0.5}
SECONDARY_KM = 5.0
TIMELINE_VERSION = 4


def parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def fmt(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


@lru_cache(maxsize=2)
def _catalog_file(mtime_ns: int, size: int, ino: int) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    # Los metadatos solo forman la clave, igual que en _timeline_file: si el rebuild cambia
    # cases.json (o lo reemplaza por otro archivo, nuevo inodo), la entrada vieja se relee.
    data = json.loads((DATA / "cases.json").read_text(encoding="utf-8"))
    return data, {c["id"]: c for c in data["cases"]}


def _catalog() -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    stat = (DATA / "cases.json").stat()
    return _catalog_file(stat.st_mtime_ns, stat.st_size, stat.st_ino)


def catalog() -> dict[str, Any]:
    """Catálogo publicado; sale de una caché en memoria compartida: los consumidores no deben mutarlo."""
    return _catalog()[0]


def get_case(case_id: str) -> dict[str, Any] | None:
    return _catalog()[1].get(case_id)


def load_goes(case: dict[str, Any]) -> list[dict[str, Any]]:
    """Detecciones GOES precalculadas (scripts/build_case_goes.py) como observaciones normalizadas."""
    path = DATA / "cases" / f"{case['id']}.goes.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    start = parse_utc(data["start_utc"])
    satellite = f"GOES-{case['goes']['satellite'][1:]}" if case.get("goes") else "GOES"
    out = []
    for minute, lat, lon, frp, bright, conf in data["rows"]:
        at = start + timedelta(minutes=minute)
        out.append({"id": f"{satellite}:{minute}:{lat}:{lon}", "lat": lat, "lon": lon, "observed_at": fmt(at),
                    "frp_mw": frp, "brightness_k": bright, "confidence": CONF_FROM_CODE[conf],
                    "sensor": "ABI", "satellite": satellite, "source": f"{satellite.replace('-', '')}_FDCF",
                    "resolution_m": 2000})
    return out


@lru_cache(maxsize=8)
def _timeline_file(case_id: str, mtime_ns: int, size: int, ino: int, version: int) -> dict[str, Any] | None:
    # Los metadatos solo forman la clave: si el rebuild cambia el archivo (o lo reemplaza por otro,
    # nuevo inodo) o sube TIMELINE_VERSION, la entrada vieja deja de encontrarse y se relee.
    data = json.loads((DATA / "cases" / f"{case_id}.timeline.json").read_text(encoding="utf-8"))
    # El chequeo va dentro para que una versión vieja cachee None y no retenga el JSON parseado.
    return data if data.get("version") == TIMELINE_VERSION else None


def static_timeline(case: dict[str, Any]) -> dict[str, Any] | None:
    """Línea temporal precalculada (scripts/build_case_timeline.py), si existe y es de la versión actual.

    El dict sale de una caché en memoria y se comparte entre llamadas: los consumidores no deben mutarlo.
    """
    path = DATA / "cases" / f"{case['id']}.timeline.json"
    try:
        stat = path.stat()
    except FileNotFoundError:
        return None
    return _timeline_file(case["id"], stat.st_mtime_ns, stat.st_size, stat.st_ino, TIMELINE_VERSION)


def goes_scans(case: dict[str, Any]) -> list[dict[str, Any]]:
    path = DATA / "cases" / f"{case['id']}.goes.json"
    return json.loads(path.read_text(encoding="utf-8"))["scans"] if path.exists() else []


class LocalPlane:
    """Proyección equirectangular local en km: suficiente para huellas de decenas de km."""

    def __init__(self, lat0: float, lon0: float):
        self.lat0, self.lon0 = lat0, lon0
        self.kx = 111.320 * math.cos(math.radians(lat0))
        self.ky = 110.574

    def to_km(self, lon: float, lat: float) -> tuple[float, float]:
        return (lon - self.lon0) * self.kx, (lat - self.lat0) * self.ky

    def to_deg(self, xy: np.ndarray) -> np.ndarray:
        """Versión vectorizada (Nx2) para shapely.transform: reemplaza la firma escalar de shapely.ops.transform."""
        return xy / np.array([self.kx, self.ky]) + np.array([self.lon0, self.lat0])


def usable(obs: dict[str, Any]) -> bool:
    return obs.get("confidence") in {"alta", "media", "nominal"}


def build_timeline(case: dict[str, Any], observations: list[dict[str, Any]], max_frames: int = 80) -> dict[str, Any]:
    """Línea temporal horaria: conteos por hora, huella acumulada, cuadros y eventos derivados.

    `expansion_km` por hora: distancia de Hausdorff entre la huella acumulada de la hora y la de la
    hora anterior, en km (cuánto se extendió lo observado); null hasta que exista huella previa.
    `acum_mj`: energía radiativa estimada, suma corrida de frp_max × 3600 s (1 MW = 1 MJ/s). Supone
    el máximo de la hora sostenido durante toda la hora y solo suma horas con dato FRP: sobreestima
    si el fuego varía dentro de la hora, así que parte en null y nunca en 0.
    """
    start, end = parse_utc(case["start_utc"]), parse_utc(case["end_utc"])
    total_hours = int((end - start).total_seconds() // 3600)
    step = max(1, math.ceil(total_hours / max_frames))
    west, south, east, north = case["bbox"]
    plane = LocalPlane((south + north) / 2, (west + east) / 2)
    diag_km = math.hypot(*plane.to_km(east, north)) * 2
    tolerance_km = max(0.15, diag_km / 300)
    digits = 4 if diag_km < 120 else 3
    inside = [o for o in observations if west <= o["lon"] <= east and south <= o["lat"] <= north]
    inside.sort(key=lambda o: o["observed_at"])

    by_hour: dict[int, list[dict[str, Any]]] = {}
    for obs in inside:
        index = int((parse_utc(obs["observed_at"]) - start).total_seconds() // 3600)
        if 0 <= index < total_hours:
            by_hour.setdefault(index, []).append(obs)

    footprint = None
    prev_footprint = None
    acum_mj = None
    hours: list[dict[str, Any]] = []
    frames: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    secondary_points: list[tuple[float, float]] = []
    previous_area = 0.0
    best_growth: tuple[float, datetime | None] = (0.0, None)
    best_frp: tuple[float, datetime | None] = (0.0, None)
    best_count: tuple[int, datetime | None] = (0, None)
    best_expansion: tuple[float, datetime | None] = (0.0, None)
    for h in range(total_hours):
        moment = start + timedelta(hours=h)
        batch = by_hour.get(h, [])
        good = [o for o in batch if usable(o)]
        new_shapes = []
        for obs in good:
            x, y = plane.to_km(obs["lon"], obs["lat"])
            if footprint is not None and h >= 2 and len(secondary_points) < 8:
                distance = footprint.distance(Point(x, y))
                far_from_known = all(math.hypot(x - sx, y - sy) > 2 * SECONDARY_KM for sx, sy in secondary_points)
                if distance > SECONDARY_KM and far_from_known:
                    secondary_points.append((x, y))
                    events.append({"t": obs["observed_at"], "kind": "secundario", "lat": obs["lat"], "lon": obs["lon"],
                                   "label": f"Calor a {distance:.0f} km de la huella previa: posible foco nuevo o salto"})
            new_shapes.append(Point(x, y).buffer(HALF_PIXEL_KM.get(obs.get("sensor"), 0.5), quad_segs=3))
        if new_shapes:
            merged = unary_union(new_shapes)
            if footprint is None:
                first = good[0]
                events.append({"t": first["observed_at"], "kind": "inicio", "lat": first["lat"], "lon": first["lon"],
                               "label": f"Primera detección satelital confiable ({first['satellite']})"})
                footprint = merged
            else:
                footprint = unary_union([footprint, merged])
        area_ha = footprint.area * 100 if footprint is not None else 0.0
        growth = max(area_ha - previous_area, 0.0)
        previous_area = area_ha
        frp_values = [o["frp_mw"] for o in batch if o.get("frp_mw") is not None]
        frp_max = max(frp_values) if frp_values else None
        expansion_km = None
        if footprint is not None and prev_footprint is not None:
            expansion_km = round(footprint.hausdorff_distance(prev_footprint), 2)
        prev_footprint = footprint
        if frp_max is not None:
            acum_mj = (acum_mj or 0.0) + frp_max * 3600.0
        if growth > best_growth[0]:
            best_growth = (growth, moment)
        if frp_max and frp_max > best_frp[0]:
            best_frp = (frp_max, moment)
        if len(good) > best_count[0]:
            best_count = (len(good), moment)
        if expansion_km is not None and expansion_km > best_expansion[0]:
            best_expansion = (expansion_km, moment)
        hours.append({
            "t": fmt(moment), "n": len(batch), "n_good": len(good),
            "n_goes": sum(o.get("sensor") == "ABI" for o in batch),
            "n_polar": sum(o.get("sensor") in {"VIIRS", "MODIS"} for o in batch),
            "frp_max": round(frp_max, 1) if frp_max else None,
            "footprint_ha": round(area_ha), "growth_ha": round(growth),
            "expansion_km": expansion_km,
            "acum_mj": round(acum_mj) if acum_mj is not None else None,
        })
        if footprint is not None and (h % step == step - 1 or h == total_hours - 1):
            geom = transform(footprint.simplify(tolerance_km), plane.to_deg)
            frames.append({"t": fmt(moment + timedelta(hours=1)), "area_ha": round(area_ha),
                           "geometry": json.loads(json.dumps(mapping(geom)), parse_float=lambda v: round(float(v), digits))})
    if best_growth[1] is not None:
        events.append({"t": fmt(best_growth[1]), "kind": "crecimiento",
                       "label": f"Mayor expansión de la huella: +{best_growth[0]:,.0f} ha en una hora".replace(",", ".")})
    if best_expansion[1] is not None:
        events.append({"t": fmt(best_expansion[1]), "kind": "expansion",
                       "label": f"Mayor expansión de la huella en distancia: {best_expansion[0]:.1f} km en una hora".replace(".", ",")})
    if best_frp[1] is not None:
        events.append({"t": fmt(best_frp[1]), "kind": "frp", "label": f"Potencia radiativa máxima: {best_frp[0]:,.0f} MW".replace(",", ".")})
    if best_count[1] is not None:
        events.append({"t": fmt(best_count[1]), "kind": "actividad", "label": f"Hora con más píxeles calientes: {best_count[0]}"})
    # Los eventos por hora llevan el inicio de la hora: dentro de la misma hora, la primera detección va antes.
    events.sort(key=lambda e: (e["t"][:13], e["kind"] != "inicio", e["t"]))
    return {
        "version": TIMELINE_VERSION, "step_hours": step, "hours": hours, "frames": frames, "events": events,
        "expansion_max_km": round(best_expansion[0], 2) if best_expansion[1] is not None else None,
        "energia_mj": round(acum_mj) if acum_mj is not None else None,
        "frp_note": ("Energía estimada sumando el FRP máximo de cada hora como si se sostuviera la hora entera "
                     "(MW × 3600 s = MJ); solo cuenta horas con dato FRP, así que es una cota gruesa."),
        "footprint_note": ("Unión de los píxeles calientes observados hasta cada hora (medio píxel de radio por sensor). "
                           "No es perímetro oficial ni área quemada: con GOES (píxel de 2-3 km) sobreestima la superficie."),
        "counts": {"goes": sum(o.get("sensor") == "ABI" for o in inside),
                   "polar": sum(o.get("sensor") in {"VIIRS", "MODIS"} for o in inside)},
    }

"""Territorio de Chile: comunas reales (BCN), regiones, distancias y rumbos."""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from shapely import STRtree
from shapely.geometry import Point, shape

from backend.settings import ROOT

EARTH_RADIUS_KM = 6371.0088
CARDINALS = ["norte", "noreste", "este", "sureste", "sur", "suroeste", "oeste", "noroeste"]

# Zonas de navegación. Las regiones salen de los límites reales; se agregan vistas de conjunto e islas.
EXTRA_ZONES: dict[str, dict[str, Any]] = {
    "chile": {"label": "Chile continental", "bbox": [-75.8, -56.0, -66.4, -17.5], "camera": [-71.0, -36.0, 2600000]},
    "juan-fernandez": {"label": "Archipiélago Juan Fernández", "bbox": [-80.9, -34.0, -78.7, -33.5], "camera": [-79.6, -33.7, 160000]},
    "rapa-nui": {"label": "Rapa Nui", "bbox": [-109.47, -27.21, -109.21, -27.05], "camera": [-109.35, -27.12, 60000]},
}


@dataclass(frozen=True)
class Comuna:
    code: int
    name: str
    provincia: str
    region_code: int
    region: str
    center: tuple[float, float]  # lon, lat
    bbox: tuple[float, float, float, float]

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "name": self.name, "provincia": self.provincia,
                "region_code": self.region_code, "region": self.region,
                "center": list(self.center), "bbox": list(self.bbox)}


class Territory:
    def __init__(self, comunas_geojson: dict[str, Any], regiones_geojson: dict[str, Any]):
        self.comunas: list[Comuna] = []
        geoms = []
        for feature in comunas_geojson["features"]:
            p = feature["properties"]
            self.comunas.append(Comuna(p["code"], p["name"], p["provincia"], p["region_code"], p["region"],
                                       tuple(p["center"]), tuple(p["bbox"])))
            geoms.append(shape(feature["geometry"]))
        self._geoms = geoms
        self._tree = STRtree(geoms)
        self.by_code = {c.code: c for c in self.comunas}
        self.regions = {f["properties"]["code"]: f["properties"] for f in regiones_geojson["features"]}

    def locate(self, lat: float, lon: float, tolerance_deg: float = 0.01) -> Comuna | None:
        """Comuna que contiene el punto. Con tolerancia pequeña para la costa simplificada."""
        point = Point(lon, lat)
        hits = self._tree.query(point, predicate="intersects")
        if len(hits):
            return self.comunas[int(hits[0])]
        nearest = self._tree.query(point.buffer(tolerance_deg), predicate="intersects")
        if len(nearest):
            best = min(nearest, key=lambda i: self._geoms[int(i)].distance(point))
            return self.comunas[int(best)]
        return None

    def zones(self) -> dict[str, dict[str, Any]]:
        zones = {"chile": EXTRA_ZONES["chile"]}
        north_to_south = sorted(self.regions.values(), key=lambda r: -r["bbox"][3])
        for region in north_to_south:
            w, s, e, n = region["bbox"]
            if region["code"] == 5:  # Valparaíso incluye islas oceánicas: se usa el continente
                w, s, e, n = -72.0, -33.97, -70.0, -32.0
            if region["code"] == 12:  # Magallanes: excluye la Antártica en la vista
                s = max(s, -56.0)
            span = max(e - w, (n - s) * 0.8)
            zones[f"region-{region['code']}"] = {
                "label": region["name"], "region_code": region["code"], "bbox": [w, s, e, n],
                "camera": [round((w + e) / 2, 3), round((s + n) / 2, 3), int(min(1400000, max(160000, span * 95000)))],
            }
        zones["juan-fernandez"] = EXTRA_ZONES["juan-fernandez"]
        zones["rapa-nui"] = EXTRA_ZONES["rapa-nui"]
        return zones


@lru_cache(maxsize=1)
def territory() -> Territory:
    data = ROOT / "web" / "data"
    return Territory(json.loads((data / "comunas.geojson").read_text(encoding="utf-8")),
                     json.loads((data / "regiones.geojson").read_text(encoding="utf-8")))


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Rumbo inicial desde el punto 1 hacia el punto 2, en grados desde el norte (0-360)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def cardinal(deg: float) -> str:
    return CARDINALS[int(((deg % 360) + 22.5) // 45) % 8]


def angle_diff(a: float, b: float) -> float:
    """Diferencia angular mínima entre dos rumbos (0-180)."""
    return abs((a - b + 180) % 360 - 180)


def is_upwind(place_to_fire_bearing: float, wind_from_deg: float | None, wind_kmh: float | None,
              tolerance: float = 45.0, min_wind_kmh: float = 8.0) -> bool:
    """El foco está a barlovento del lugar: el viento sopla DESDE el foco HACIA el lugar.

    La dirección meteorológica del viento indica de dónde viene. Si viene desde el rumbo
    en que está el foco (±tolerancia) y supera un mínimo, el humo y las pavesas avanzan hacia el lugar.
    """
    if wind_from_deg is None or wind_kmh is None or wind_kmh < min_wind_kmh:
        return False
    return angle_diff(place_to_fire_bearing, wind_from_deg) <= tolerance

"""Territorio de Chile: comunas reales (BCN), regiones, distancias y rumbos."""
from __future__ import annotations

import json
import math
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from shapely import STRtree
from shapely.geometry import Point, shape
from shapely.ops import unary_union

from backend.cases import HALF_PIXEL_KM, LocalPlane
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

    def nearest(self, lat: float, lon: float, max_km: float = 3.0) -> Comuna | None:
        """La comuna más cercana al punto: la que lo contiene, o la del borde a ≤ `max_km`.

        Rescate para puntos chilenos que `locate` deja sin comuna al caer en los huecos del
        trazado simplificado (precordillera, límites comunales, costa). Más lejos de `max_km`
        se devuelve None: a esa distancia no se distingue Chile rural del extranjero o el mar
        abierto, y asignar una comuna sería inventarla.
        """
        point = Point(lon, lat)
        hits = self._tree.query(point, predicate="intersects")
        if len(hits):
            return self.comunas[int(hits[0])]
        # El grado de longitud vale menos km al sur: la caja candidata usa el peor caso y
        # la elección se hace midiendo de verdad al borde, no en grados.
        pad = max_km / max(20.0, 111.3 * math.cos(math.radians(lat)))
        near = self._tree.query(point.buffer(pad), predicate="intersects")
        best = min(near, key=lambda i: _edge_distance_km(lat, lon, self._geoms[int(i)]), default=None)
        if best is not None and _edge_distance_km(lat, lon, self._geoms[int(best)]) <= max_km:
            return self.comunas[int(best)]
        return None

    def comunas_in(self, geometry) -> list[Comuna]:
        """Comunas que tocan una geometría (el polígono de un aviso CAP), de norte a sur."""
        hits = self._tree.query(geometry, predicate="intersects")
        found = [self.comunas[int(i)] for i in hits]
        found.sort(key=lambda c: (-c.center[1], c.code))
        return found

    def comunas_named(self, text: str) -> list[Comuna]:
        """Comunas que nombra el texto de una zona cuando el aviso no trae polígono.

        Se acepta lo que se puede afirmar sin inventar: la región escrita antes de «:»
        («Magallanes: Insular Norte») o el nombre exacto de una comuna («Juan Fernández»).
        No se buscan coincidencias parciales: atribuir un aviso a la comuna equivocada es peor
        que decir solo la región.
        """
        if not text:
            return []
        normalized = _fold(text)
        head = _fold(text.split(":", 1)[0]) if ":" in text else normalized
        for region in self.regions.values():
            name = _fold(region["name"])
            if name and (head == name or normalized == name):
                found = [c for c in self.comunas if c.region_code == region["code"]]
                found.sort(key=lambda c: (-c.center[1], c.code))
                return found
        for comuna in self.comunas:
            if normalized == _fold(comuna.name):
                return [comuna]
        return []

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


@lru_cache(maxsize=1)
def _snaspe_areas() -> tuple[dict[str, Any], ...]:
    """Áreas protegidas SNASPE (CONAF) con su geometría, cargadas una vez por proceso."""
    path = ROOT / "web" / "data" / "snaspe.json"
    if not path.exists():
        return ()
    data = json.loads(path.read_text(encoding="utf-8"))
    areas = []
    for item in data.get("items", []):
        areas.append({"name": item["name"], "category": item.get("category"),
                      "region": item.get("region"), "geom": shape(item["geometry"])})
    return tuple(areas)


def protected_areas_near(lat: float, lon: float, max_km: float = 5.0) -> list[dict[str, Any]]:
    """Áreas protegidas que contienen el punto o cuyo borde queda a ≤ `max_km`, por distancia.

    La distancia es al borde del polígono (un punto dentro de un «hueco» del área queda
    a la distancia del borde del hueco).
    """
    point = Point(lon, lat)
    pad_lat = max_km / 110.6
    pad_lon = max_km / max(20.0, 111.3 * math.cos(math.radians(lat)))
    found = []
    for area in _snaspe_areas():
        geom = area["geom"]
        minx, miny, maxx, maxy = geom.bounds
        if not (minx - pad_lon <= lon <= maxx + pad_lon and miny - pad_lat <= lat <= maxy + pad_lat):
            continue
        hit = {k: area[k] for k in ("name", "category", "region")}
        if geom.covers(point):
            found.append(hit | {"inside": True, "distance_km": 0.0})
            continue
        distance = _edge_distance_km(lat, lon, geom)
        if distance <= max_km:
            found.append(hit | {"inside": False, "distance_km": round(distance, 1)})
    return sorted(found, key=lambda h: h["distance_km"])


def _edge_distance_km(lat: float, lon: float, geom) -> float:
    """Distancia mínima del punto al borde de un (Multi)Polígono, en km.

    Proyección equirectangular local para interpolar el punto más cercano de cada segmento y
    `haversine_km` para medir: suficiente a la escala de pocos km de una ficha.
    """
    kx = math.cos(math.radians(lat))
    best = math.inf
    polys = [geom] if geom.geom_type == "Polygon" else list(getattr(geom, "geoms", []))
    for poly in polys:
        for ring in (poly.exterior, *poly.interiors):
            ax, ay = ring.coords[0]
            for vx, vy in ring.coords[1:]:
                dx, dy = (vx - ax) * kx, vy - ay
                px, py = (lon - ax) * kx, lat - ay
                dd = dx * dx + dy * dy
                t = 0.0 if dd == 0 else max(0.0, min(1.0, (px * dx + py * dy) / dd))
                best = min(best, haversine_km(lat, lon, ay + t * (vy - ay), ax + t * (vx - ax)))
                ax, ay = vx, vy
    return best


def incident_hull(members: list[dict[str, Any]], simplify_deg: float = 0.005,
                  max_points: int = 200) -> list[list[float]] | None:
    """Huella aproximada de un incidente: anillo [lon, lat] cerrado, o None si hay < 3 detecciones.

    La misma huella de las fichas de caso (unión de los píxeles calientes, medio píxel de radio
    por sensor) sobre un plano local en km, simplificada a ~`simplify_deg` grados y con tope de
    `max_points` vértices. Si la unión queda en partes separadas, se devuelve la mayor.
    No es el perímetro oficial ni el área quemada.
    """
    if len(members) < 3:
        return None
    plane = LocalPlane(sum(m["lat"] for m in members) / len(members),
                       sum(m["lon"] for m in members) / len(members))
    merged = unary_union([Point(*plane.to_km(m["lon"], m["lat"]))
                          .buffer(HALF_PIXEL_KM.get(m.get("sensor"), 0.5), quad_segs=3)
                          for m in members])
    poly = merged if merged.geom_type == "Polygon" else max(merged.geoms, key=lambda g: g.area)
    tolerance = simplify_deg * 110.6
    while True:
        simplified = poly.simplify(tolerance)
        coords = simplified.exterior.coords if simplified.geom_type == "Polygon" else poly.exterior.coords
        if len(coords) <= max_points or tolerance >= 5.0:
            break
        tolerance *= 2
    return [[round(plane.lon0 + x / plane.kx, 4), round(plane.lat0 + y / plane.ky, 4)] for x, y in coords]


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


def _fold(text: str) -> str:
    """Texto comparable: minúsculas, sin tildes y con espacios simples."""
    normalized = unicodedata.normalize("NFKD", text.casefold())
    return " ".join("".join(ch for ch in normalized if not unicodedata.combining(ch)).split())


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

"""Perímetro oficial de incendios: capa «Perimetro_final» del catálogo ArcGIS de GEPRIF-CONAF.

Es la misma organización del Botón Rojo y del reporte de incendios (`services5/A1ELWse9bRAi2JiV`).
Cada polígono es el perímetro final de un incendio (`ID_IF`, región, superficie en hectáreas y fecha
de edición): se muestra en la ficha del incidente como estado final, nunca como avance hora a hora
(regla de interpretación n.º 4 de docs/FUENTES.md).

La capa se consulta sin clave, pero la declaración «uso público citando a CONAF» solo aparece en
algunos tableros de la organización, no en los servicios: por eso la consulta está apagada por
defecto (`CONAF_PERIMETRO_ENABLED`) hasta la autorización formal de OFI-03. BRASA solo hace
consultas `Query` de lectura; nunca escribe en el servicio.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

import httpx

from backend.geo import haversine_km

PERIMETER_URL = "https://services5.arcgis.com/A1ELWse9bRAi2JiV/arcgis/rest/services/Perimetro_final/FeatureServer/0/query"
# Ítem ArcGIS del servicio (serviceItemId de la capa): el enlace público para la atribución.
PERIMETER_PAGE_URL = "https://www.arcgis.com/home/item.html?id=913b74c0d56d4ce58c0811d56d08a04b"
PERIMETER_SOURCE = "CONAF · Perímetro final (GEPRIF)"
OUT_FIELDS = "ID_IF,REGION,Superficie_hectareas,Patron_propagacion,EditDate"
ENVELOPE_PAD_DEG = 0.2  # ~20 km alrededor del punto informado por CONAF
SIMPLIFY_DEG = 0.0008  # ~90 m: la capa devuelve el polígono simplificado y la ficha pesa menos


class ConafDeiError(Exception):
    pass


def _iso(ms: Any) -> str | None:
    """`EditDate` llega como milisegundos epoch (UTC); se publica como fecha ISO."""
    if not isinstance(ms, (int, float)):
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _perimeter(feature: dict[str, Any]) -> dict[str, Any] | None:
    attrs = feature.get("properties") or {}
    geometry = feature.get("geometry")
    if not geometry:
        return None
    area = attrs.get("Superficie_hectareas")
    return {
        "id_if": (str(attrs.get("ID_IF") or "").strip() or None),
        "region": attrs.get("REGION") or None,
        "area_ha": round(float(area), 1) if isinstance(area, (int, float)) else None,
        "pattern": attrs.get("Patron_propagacion") or None,
        "edited_at": _iso(attrs.get("EditDate")),
        "geometry": geometry,
    }


async def fetch_perimeters(client: httpx.AsyncClient, lat: float, lon: float) -> list[dict[str, Any]]:
    """Perímetros cuyo envelope toca un cuadro de ±ENVELOPE_PAD_DEG alrededor del punto.

    Con `f=geojson` la respuesta ya es un FeatureCollection en WGS84; `maxAllowableOffset`
    le pide al servicio la geometría simplificada.
    """
    params = {
        "where": "1=1",
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "geometry": f"{lon - ENVELOPE_PAD_DEG},{lat - ENVELOPE_PAD_DEG},{lon + ENVELOPE_PAD_DEG},{lat + ENVELOPE_PAD_DEG}",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": OUT_FIELDS,
        "returnGeometry": "true",
        "outSR": "4326",
        "maxAllowableOffset": str(SIMPLIFY_DEG),
        "f": "geojson",
    }
    try:
        response = await client.get(PERIMETER_URL, params=params, timeout=40)
        response.raise_for_status()
        data = response.json()
    except (httpx.RequestError, httpx.HTTPStatusError, ValueError) as exc:
        raise ConafDeiError(f"CONAF Perimetro_final no respondió ({type(exc).__name__}).") from exc
    if "error" in data:
        raise ConafDeiError(f"CONAF Perimetro_final devolvió un error ({data['error'].get('code')}).")
    return [p for p in (_perimeter(f) for f in data.get("features", [])) if p]


def _rings(geometry: dict[str, Any]) -> list[list[list[float]]]:
    """Anillos [lon, lat] de un Polygon o MultiPolygon GeoJSON."""
    coords = geometry.get("coordinates") or []
    if geometry.get("type") == "Polygon":
        return list(coords)
    if geometry.get("type") == "MultiPolygon":
        return [ring for poly in coords for ring in poly]
    return []


def _inside(ring: list[list[float]], lat: float, lon: float) -> bool:
    """Punto dentro del anillo (par/impar). Los vértices vienen [lon, lat] o [lon, lat, alt]."""
    inside = False
    j = len(ring) - 1
    for i, point in enumerate(ring):
        xi, yi = point[0], point[1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def distance_km(geometry: dict[str, Any], lat: float, lon: float) -> float:
    """0 si el punto cae dentro del polígono; si no, distancia al borde más cercano.

    La distancia se mide punto-segmento sobre cada arista del anillo, con la misma
    proyección equirectangular local de `_edge_distance_km` en backend/geo.py: medir
    a los vértices inflaba la distancia en hasta medio paso de simplificación
    (~45 m con SIMPLIFY_DEG) y podía elegir el polígono equivocado.
    """
    rings = _rings(geometry)
    if not rings:
        return float("inf")
    # Par/impar sobre todos los anillos: los hoyos anulan el interior como corresponde.
    crossings = sum(1 for ring in rings if _inside(ring, lat, lon))
    if crossings % 2 == 1:
        return 0.0
    kx = math.cos(math.radians(lat))
    best = float("inf")
    for ring in rings:
        ax, ay = ring[-1][0], ring[-1][1]
        for point in ring:
            vx, vy = point[0], point[1]
            dx, dy = (vx - ax) * kx, vy - ay
            px, py = (lon - ax) * kx, lat - ay
            dd = dx * dx + dy * dy
            t = 0.0 if dd == 0 else max(0.0, min(1.0, (px * dx + py * dy) / dd))
            best = min(best, haversine_km(lat, lon, ay + t * (vy - ay), ax + t * (vx - ax)))
            ax, ay = vx, vy
    return best


def _priority(feature: dict[str, Any]) -> tuple[str, float]:
    """Orden de desempate de pick_perimeter: más reciente primero, más grande después."""
    return (feature.get("edited_at") or "", feature.get("area_ha") or 0.0)


def pick_perimeter(features: list[dict[str, Any]], lat: float, lon: float) -> dict[str, Any] | None:
    """El perímetro que contiene el punto informado; si ninguno, el más cercano.

    A distancia igual gana el `edited_at` más reciente (la capa guarda dos versiones
    del mismo incendio: la última edición es la vigente) y, si persiste el empate, el
    de mayor `area_ha` (el polígono principal cuando dos incendios se tocan). Sin este
    criterio el desempate era el orden de llegada del FeatureCollection.
    """
    best, best_km = None, float("inf")
    for feature in features:
        d = distance_km(feature["geometry"], lat, lon)
        if d < best_km or (d == best_km and best is not None and _priority(feature) > _priority(best)):
            best, best_km = feature, d
    return best

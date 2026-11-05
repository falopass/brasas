"""OpenStreetMap vía Overpass: puntos de encuentro, hospitales y cuarteles cercanos a un lugar,
y la infraestructura crítica a sotavento de un incendio (OSM-SOTAVENTO).

La cobertura de OSM en Chile es buena en ciudades y desigual en zonas rurales: la ausencia
de un punto en el mapa no significa que no exista. Los puntos de encuentro oficiales los
define cada municipio y SENAPRED. Solo se devuelven puntos dentro del territorio chileno.

El filtro de territorio se aplica en `parse()` y no en la vista: la consulta es por radio
y el radio no respeta fronteras, así que cerca de la cordillera Overpass devuelve lugares de
Argentina. Descartarlos acá evita que el dato ajeno entre a la caché de 24 h y llegue a la
lista del vecino.
"""

from __future__ import annotations

import math
import time
from typing import Any

import httpx

from backend.geo import EARTH_RADIUS_KM, angle_diff, bearing_deg, cardinal, haversine_km, territory
from backend.providers import _retry

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
SOURCE = "OpenStreetMap · Overpass API"
LICENSE = "OpenStreetMap (ODbL)"

KINDS = {
    "assembly_point": "Punto de encuentro",
    "hospital": "Hospital",
    "clinic": "Centro de salud",
    "fire_station": "Cuartel de Bomberos",
    "police": "Carabineros",
}

CRITICAL_CATEGORIES = ("escuelas", "salud", "energia", "agua")

# (clave, valor) de OSM → (categoría, etiqueta en castellano). El valor es el `kind`.
CRITICAL_TAGS: dict[tuple[str, str], tuple[str, str]] = {
    ("amenity", "school"): ("escuelas", "Escuela"),
    ("amenity", "kindergarten"): ("escuelas", "Jardín infantil"),
    ("amenity", "hospital"): ("salud", "Hospital"),
    ("amenity", "clinic"): ("salud", "Centro de salud"),
    ("amenity", "doctors"): ("salud", "Consulta médica"),
    ("power", "substation"): ("energia", "Subestación eléctrica"),
    ("power", "plant"): ("energia", "Planta de energía"),
    ("power", "line"): ("energia", "Línea eléctrica"),
    ("man_made", "water_works"): ("agua", "Planta de agua potable"),
    ("man_made", "wastewater_plant"): ("agua", "Planta de tratamiento"),
    ("man_made", "water_tower"): ("agua", "Copa de agua"),
}

_INFRA_CACHE: dict[tuple[float, float, int], tuple[float, list[dict[str, Any]]]] = {}
INFRA_CACHE_TTL_S = 1800
_INFRA_CACHE_MAX = 256
# La caché agrupa por celda de 0,01°: dos puntos de la misma celda pueden estar a 1,54 km.
# Se consulta ese margen de más y el filtro final mide desde el punto pedido, sin perder
# elementos del borde de los 5 km.
_INFRA_CACHE_PAD_M = 1600


class OverpassError(Exception):
    pass


def build_query(lat: float, lon: float, radius_m: int) -> str:
    around = f"(around:{radius_m},{lat:.5f},{lon:.5f})"
    return (
        "[out:json][timeout:25];("
        f'nwr["emergency"="assembly_point"]{around};'
        f'nwr["amenity"~"^(hospital|clinic|fire_station|police)$"]{around};'
        ");out center 200;"
    )


def build_critical_query(lat: float, lon: float, radius_m: int = 5000) -> str:
    """Nodos, vías y relaciones de infraestructura crítica en un radio (por defecto 5 km).

    Sin límite de resultados: un `out ... 200` recorta la lista y los conteos dirían que no
    hay escuelas donde solo se cortaron los tramos eléctricos. Las líneas van con geometría
    (`out geom`) porque el centro de su caja envolvente puede quedar fuera del radio.
    """
    around = f"(around:{radius_m},{lat:.5f},{lon:.5f})"
    return (
        "[out:json][timeout:20];("
        f'nwr["amenity"~"^(school|kindergarten|hospital|clinic|doctors)$"]{around};'
        f'nwr["power"~"^(substation|plant)$"]{around};'
        f'nwr["man_made"~"^(water_works|wastewater_plant|water_tower)$"]{around};'
        ")->.puntos;"
        f'(nwr["power"="line"]{around};)->.lineas;'
        ".puntos out center;"
        ".lineas out geom;"
    )


def parse(elements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    try:
        country = territory()
    except Exception:  # comunas ausentes o ilegibles: mejor sin puntos que con puntos de otro país
        return []
    result = []
    for el in elements:
        tags = el.get("tags") or {}
        kind = "assembly_point" if tags.get("emergency") == "assembly_point" else tags.get("amenity")
        if kind not in KINDS:
            continue
        lat = el.get("lat") or (el.get("center") or {}).get("lat")
        lon = el.get("lon") or (el.get("center") or {}).get("lon")
        if lat is None or lon is None:
            continue
        lat, lon = float(lat), float(lon)
        if country.locate(lat, lon) is None:
            continue
        result.append(
            {
                "id": f"{el.get('type')}/{el.get('id')}",
                "kind": kind,
                "kind_label": KINDS[kind],
                "name": tags.get("name") or KINDS[kind],
                "lat": lat,
                "lon": lon,
            }
        )
    return result


def classify_critical_tags(tags: dict[str, Any] | None) -> tuple[str, str, str] | None:
    """`(categoría, kind, etiqueta)` o None si el elemento no es infraestructura crítica."""
    if not tags:
        return None
    for (key, value), (category, label) in CRITICAL_TAGS.items():
        if tags.get(key) == value:
            return category, value, label
    return None


def _geometry_points(el: dict[str, Any]) -> list[tuple[float, float]]:
    """Vértices de una vía o relación pedida con `out geom`."""
    if el.get("type") == "relation":
        raw = [p for member in el.get("members") or [] for p in member.get("geometry") or []]
    else:
        raw = el.get("geometry") or []
    return [(float(p["lat"]), float(p["lon"])) for p in raw if p.get("lat") is not None and p.get("lon") is not None]


def _nearest_on_line(lat: float, lon: float, geometry: list[tuple[float, float]]) -> tuple[float, float, float]:
    """Punto de la polilínea más cercano a `(lat, lon)` y su distancia en km.

    Proyección plana local: a pocos kilómetros el error frente a la esfera es despreciable.
    """
    if len(geometry) == 1:
        return geometry[0][0], geometry[0][1], haversine_km(lat, lon, *geometry[0])
    coslat = math.cos(math.radians(lat))
    km_deg = EARTH_RADIUS_KM * math.pi / 180.0
    best: tuple[float, float, float] | None = None
    for (alat, alon), (blat, blon) in zip(geometry, geometry[1:]):
        ax, ay = (alon - lon) * coslat * km_deg, (alat - lat) * km_deg
        bx, by = (blon - lon) * coslat * km_deg, (blat - lat) * km_deg
        dx, dy = bx - ax, by - ay
        seg2 = dx * dx + dy * dy
        t = 0.0 if not seg2 else max(0.0, min(1.0, -(ax * dx + ay * dy) / seg2))
        px, py = ax + t * dx, ay + t * dy
        if best is None or px * px + py * py < best[0]:
            best = (px * px + py * py, alat + t * (blat - alat), alon + t * (blon - alon))
    plat, plon = best[1], best[2]
    return plat, plon, haversine_km(lat, lon, plat, plon)


def parse_critical(elements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Infraestructura crítica con centro o geometría, solo dentro del territorio chileno."""
    try:
        country = territory()
    except Exception:  # igual que parse(): sin territorio no se publican puntos de otro país
        return []
    result = []
    for el in elements:
        classified = classify_critical_tags(el.get("tags") or {})
        if classified is None:
            continue
        category, kind, kind_label = classified
        geometry = _geometry_points(el)
        lat = el.get("lat") or (el.get("center") or {}).get("lat")
        lon = el.get("lon") or (el.get("center") or {}).get("lon")
        if (lat is None or lon is None) and geometry:
            lat, lon = geometry[0]
        if lat is None or lon is None:
            continue
        lat, lon = float(lat), float(lon)
        if country.locate(lat, lon) is None:
            continue
        entry = {
            "id": f"{el.get('type', 'node')}/{el.get('id', len(result))}",
            "category": category,
            "kind": kind,
            "kind_label": kind_label,
            "name": (el.get("tags") or {}).get("name") or kind_label,
            "lat": lat,
            "lon": lon,
        }
        if geometry:
            entry["geometry"] = geometry
        result.append(entry)
    return result


def _wind_advance(wind_dir_deg: float | None) -> tuple[float | None, str | None]:
    """Rumbo hacia donde avanza el viento: `(desde + 180) % 360`, y su punto cardinal."""
    if wind_dir_deg is None:
        return None, None
    advance = (float(wind_dir_deg) + 180.0) % 360.0
    return advance, cardinal(advance)


def filter_downwind_infrastructure(
    lat: float,
    lon: float,
    wind_dir_deg: float | None,
    items: list[dict[str, Any]],
    radius_km: float = 5.0,
    cone_deg: float = 60.0,
) -> dict[str, Any]:
    """Qué infraestructura cae a sotavento.

    `wind_dir_deg` es la dirección meteorológica (desde dónde sopla). El humo avanza hacia
    `(wind_dir_deg + 180) % 360`. Un elemento queda `downwind` si su distancia es <= `radius_km`
    y el ángulo con ese rumbo es <= `cone_deg` (±60° con el valor por defecto). Sin viento no
    hay cono: se listan los que están dentro del radio, con `downwind` en falso.
    """
    advance, advance_cardinal = _wind_advance(wind_dir_deg)
    counts = {cat: 0 for cat in CRITICAL_CATEGORIES}
    counts_radius = {cat: 0 for cat in CRITICAL_CATEGORIES}
    downwind_items: list[dict[str, Any]] = []
    in_radius: list[dict[str, Any]] = []

    for raw in items:
        geometry = raw.get("geometry")
        if geometry:
            ilat, ilon, dist_km = _nearest_on_line(lat, lon, geometry)
        else:
            ilat, ilon = raw.get("lat"), raw.get("lon")
            if ilat is None or ilon is None:
                continue
            ilat, ilon = float(ilat), float(ilon)
            dist_km = haversine_km(lat, lon, ilat, ilon)
        category, kind, kind_label = raw.get("category"), raw.get("kind"), raw.get("kind_label")
        if category not in counts:
            classified = classify_critical_tags(raw.get("tags"))
            if classified is None:
                continue
            category, kind, kind_label = classified
        if dist_km > radius_km:
            continue
        brg = bearing_deg(lat, lon, ilat, ilon)
        is_downwind = advance is not None and angle_diff(brg, advance) <= cone_deg
        name = str(raw.get("name") or kind_label or category).strip() or str(kind_label or category)
        entry = {
            "id": raw.get("id") or f"osm/{len(in_radius)}",
            "name": name,
            "category": category,
            "kind": kind or category,
            "kind_label": kind_label or name,
            "lat": ilat,
            "lon": ilon,
            "distance_km": round(dist_km, 2),
            "bearing_deg": round(brg, 1),
            "direction": cardinal(brg),
            "downwind": is_downwind,
        }
        in_radius.append(entry)
        counts_radius[category] += 1
        if is_downwind:
            counts[category] += 1
            downwind_items.append(entry)

    in_radius.sort(key=lambda item: item["distance_km"])
    downwind_items.sort(key=lambda item: item["distance_km"])
    shown = downwind_items if advance is not None else in_radius
    return {
        "status": "ok",
        "lat": lat,
        "lon": lon,
        "radius_km": radius_km,
        "cone_deg": cone_deg,
        "wind_dir_deg": round(float(wind_dir_deg), 1) if wind_dir_deg is not None else None,
        "wind_advance_deg": round(advance, 1) if advance is not None else None,
        "wind_to": f"hacia el {advance_cardinal}" if advance_cardinal else None,
        "counts": counts,
        "counts_radius": counts_radius,
        "total_downwind": len(downwind_items),
        "total_radius": len(in_radius),
        "items": shown[:25],
        "source": SOURCE,
        "license": LICENSE,
        "note": (
            "Infraestructura registrada en OpenStreetMap dentro de 5 km hacia donde sopla el viento. "
            "El mapa colaborativo puede estar incompleto en zonas rurales."
            if advance is not None
            else "Sin dirección de viento: registros de OpenStreetMap dentro de 5 km, sin cono de sotavento."
        ),
    }


def _unavailable(lat: float, lon: float, wind_dir_deg: float | None, radius_km: float, cone_deg: float) -> dict[str, Any]:
    """La fuente no respondió: no se publican ceros, que se leerían como «no hay nada»."""
    advance, advance_cardinal = _wind_advance(wind_dir_deg)
    return {
        "status": "unavailable",
        "lat": lat,
        "lon": lon,
        "radius_km": radius_km,
        "cone_deg": cone_deg,
        "wind_dir_deg": round(float(wind_dir_deg), 1) if wind_dir_deg is not None else None,
        "wind_advance_deg": round(advance, 1) if advance is not None else None,
        "wind_to": f"hacia el {advance_cardinal}" if advance_cardinal else None,
        "counts": None,
        "counts_radius": None,
        "total_downwind": None,
        "total_radius": None,
        "items": [],
        "source": SOURCE,
        "license": LICENSE,
        "note": "Consulta de OpenStreetMap no disponible en este momento.",
    }


TIMEOUT_S = 20
# 3 intentos en total; un 429 pasajero de Overpass suele ceder en segundos
WAITS_S = (1.0, 3.0)


async def nearby(client: httpx.AsyncClient, lat: float, lon: float, radius_m: int = 12000) -> list[dict[str, Any]]:
    query = build_query(lat, lon, radius_m)
    try:
        response = await _retry.request(client, "POST", OVERPASS_URL, data={"data": query}, timeout=TIMEOUT_S, delays=WAITS_S)
        return parse(response.json().get("elements") or [])
    except _retry.Failure as exc:
        raise OverpassError(f"OpenStreetMap/Overpass no respondió ({type(exc.cause).__name__}).") from exc
    except ValueError as exc:
        # Un 4xx que no es 429 no se reintenta: es un problema de la consulta, no de la red.
        raise OverpassError(f"OpenStreetMap/Overpass no respondió ({type(exc).__name__}).") from exc


async def fetch_critical_infrastructure(
    lat: float,
    lon: float,
    wind_dir_deg: float | None = None,
    radius_m: int = 5000,
    cone_deg: float = 60.0,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Infraestructura crítica en `radius_m` y cuáles quedan a sotavento.

    La consulta se hace con 1600 m de margen sobre la celda de 0,01° y el filtro final mide
    desde el punto pedido: dos puntos de la misma celda comparten caché sin perder elementos
    del borde. Si Overpass falla o agota el tiempo, se sirve la caché vencida; si no hay
    ninguna, `status` queda en `unavailable` y los conteos en null.
    """
    radius_km = radius_m / 1000.0
    cell = (round(lat, 2), round(lon, 2), int(radius_m))
    now = time.monotonic()
    cached = _INFRA_CACHE.get(cell)
    items: list[dict[str, Any]] | None = None
    if cached and (now - cached[0]) < INFRA_CACHE_TTL_S:
        items = cached[1]
    else:
        query = build_critical_query(lat, lon, radius_m + _INFRA_CACHE_PAD_M)
        try:
            if client is None:
                async with httpx.AsyncClient() as temp:
                    response = await _retry.request(temp, "POST", OVERPASS_URL, data={"data": query}, timeout=TIMEOUT_S, delays=WAITS_S)
            else:
                response = await _retry.request(client, "POST", OVERPASS_URL, data={"data": query}, timeout=TIMEOUT_S, delays=WAITS_S)
            payload = response.json()
            if payload.get("remark"):
                # Overpass avisa así un timeout o falta de memoria: la lista viene truncada.
                raise ValueError(str(payload["remark"]))
            items = parse_critical(payload.get("elements") or [])
            if len(_INFRA_CACHE) >= _INFRA_CACHE_MAX:
                _INFRA_CACHE.clear()
            _INFRA_CACHE[cell] = (now, items)
        except (_retry.Failure, ValueError, httpx.HTTPError, KeyError, TypeError):
            if cached:
                items = cached[1]
            else:
                return _unavailable(lat, lon, wind_dir_deg, radius_km, cone_deg)
    return filter_downwind_infrastructure(lat, lon, wind_dir_deg, items or [], radius_km=radius_km, cone_deg=cone_deg)

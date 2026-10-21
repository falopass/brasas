"""OpenStreetMap vía Overpass: puntos de encuentro, hospitales y cuarteles cercanos a un lugar.

La cobertura de OSM en Chile es buena en ciudades y desigual en zonas rurales: la ausencia
de un punto en el mapa no significa que no exista. Los puntos de encuentro oficiales los
define cada municipio y SENAPRED. Solo se devuelven puntos dentro del territorio chileno.

El filtro de territorio se aplica en el proveedor y no en la vista: la consulta es por radio
y el radio no respeta fronteras, así que cerca de la cordillera Overpass devuelve lugares de
Argentina. Descartarlos acá evita que el dato ajeno entre a la caché de 24 h y llegue a la
lista del vecino.
"""

from __future__ import annotations

from typing import Any

import httpx

from backend.geo import territory
from backend.providers import _retry

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

KINDS = {
    "assembly_point": "Punto de encuentro",
    "hospital": "Hospital",
    "clinic": "Centro de salud",
    "fire_station": "Cuartel de Bomberos",
    "police": "Carabineros",
}


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


def parse(elements: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
        result.append(
            {
                "id": f"{el.get('type')}/{el.get('id')}",
                "kind": kind,
                "kind_label": KINDS[kind],
                "name": tags.get("name") or KINDS[kind],
                "lat": float(lat),
                "lon": float(lon),
            }
        )
    return result


TIMEOUT_S = 20
# 3 intentos en total; un 429 pasajero de Overpass suele ceder en segundos
WAITS_S = (1.0, 3.0)


def _only_chile(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Descarta puntos fuera del territorio chileno, con la misma regla que los focos de calor."""
    try:
        country = territory()
    except Exception:  # comunas ausentes o ilegibles: mejor sin puntos que con puntos de otro país
        return []
    return [p for p in points if country.locate(p["lat"], p["lon"]) is not None]


async def nearby(client: httpx.AsyncClient, lat: float, lon: float, radius_m: int = 12000) -> list[dict[str, Any]]:
    query = build_query(lat, lon, radius_m)
    try:
        response = await _retry.request(client, "POST", OVERPASS_URL, data={"data": query}, timeout=TIMEOUT_S, delays=WAITS_S)
        return _only_chile(parse(response.json().get("elements") or []))
    except _retry.Failure as exc:
        raise OverpassError(f"OpenStreetMap/Overpass no respondió ({type(exc.cause).__name__}).") from exc
    except ValueError as exc:
        # Un 4xx que no es 429 no se reintenta: es un problema de la consulta, no de la red.
        raise OverpassError(f"OpenStreetMap/Overpass no respondió ({type(exc).__name__}).") from exc

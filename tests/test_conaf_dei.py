"""Contrato unitario del proveedor del perímetro oficial de CONAF (GEPRIF «Perimetro_final»).

`backend/providers/conaf_dei.py` decide qué polígono oficial se publica en la ficha del
incidente: traduce `EditDate` (epoch ms UTC) a ISO, la superficie en hectáreas y los
anillos GeoJSON `[lon, lat]` con hoyos (par/impar sobre todos los anillos), y elige
«el que contiene el punto; si ninguno, el más cercano». Pruebas con datos armados a
mano, sin red: `fetch_perimeters` corre contra `httpx.MockTransport`.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from backend.geo import haversine_km
from backend.providers import conaf_dei
from tests.conftest import json_response

EDIT_MS = 1772461422369  # EditDate de la capa viene en milisegundos epoch UTC


def _square(lon: float, lat: float, half: float = 0.05) -> dict:
    ring = [
        [lon - half, lat - half],
        [lon + half, lat - half],
        [lon + half, lat + half],
        [lon - half, lat + half],
        [lon - half, lat - half],
    ]
    return {"type": "Polygon", "coordinates": [ring]}


def _feature(id_if: str = "612-SAN CARLOS", lon: float = -71.40, lat: float = -33.06, area: object = 639.6) -> dict:
    properties = {"ID_IF": id_if, "REGION": "VALPO", "Patron_propagacion": "Viento", "EditDate": EDIT_MS}
    if area is not None:
        properties["Superficie_hectareas"] = area
    return {"type": "Feature", "geometry": _square(lon, lat), "properties": properties}


def _geojson(*features: dict) -> dict:
    return {"type": "FeatureCollection", "features": list(features)}


def _norm(id_if: str, lon: float, lat: float) -> dict:
    """La forma normalizada que consume pick_perimeter (salida de fetch_perimeters)."""
    return {"id_if": id_if, "region": None, "area_ha": None, "pattern": None, "edited_at": None, "geometry": _square(lon, lat)}


def _fetch(payload, status: int = 200):
    async def go():
        def handler(request: httpx.Request) -> httpx.Response:
            if status != 200:
                return httpx.Response(status)
            if isinstance(payload, str):
                return httpx.Response(200, content=payload.encode(), headers={"content-type": "application/json"})
            return json_response(payload)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await conaf_dei.fetch_perimeters(client, -33.06, -71.40)

    return asyncio.run(go())


# ----------------------------------------------------------------------- _iso (EditDate → ISO UTC)


def test_iso_converts_epoch_ms_to_utc():
    # 2026-03-01T12:00:00Z en milisegundos epoch: EditDate es UTC, no hora local de Chile.
    assert conaf_dei._iso(1772366400000) == "2026-03-01T12:00:00Z"
    assert conaf_dei._iso(EDIT_MS).endswith("Z")
    assert conaf_dei._iso(1772366400000.0) == "2026-03-01T12:00:00Z"  # también acepta float


def test_iso_rejects_non_numeric_values():
    assert conaf_dei._iso(None) is None
    assert conaf_dei._iso("2026-03-01") is None
    assert conaf_dei._iso("1772366400000") is None


# ----------------------------------------------------------------------- _perimeter (feature → ficha)


def test_perimeter_returns_none_without_geometry():
    assert conaf_dei._perimeter({"type": "Feature", "properties": {"ID_IF": "1"}}) is None
    assert conaf_dei._perimeter({"type": "Feature", "geometry": None, "properties": {"ID_IF": "1"}}) is None


def test_perimeter_keeps_hectares_and_survives_a_missing_area():
    p = conaf_dei._perimeter(_feature())
    assert p["area_ha"] == 639.6  # hectáreas tal como las publica CONAF; en m² serían 6.396.000
    sin_area = conaf_dei._perimeter(_feature(area=None))
    assert sin_area is not None and sin_area["area_ha"] is None
    texto = conaf_dei._perimeter(_feature(area="639,6"))
    assert texto["area_ha"] is None  # un texto no se adivina: queda None, no revienta
    redondeo = conaf_dei._perimeter(_feature(area=639.67))
    assert redondeo["area_ha"] == 639.7
    assert p["id_if"] == "612-SAN CARLOS" and p["edited_at"] and p["edited_at"].endswith("Z")


# ----------------------------------------------------------------------- distance_km (anillos [lon, lat])


def test_distance_is_zero_inside_and_vertex_distance_outside():
    square = _square(-71.40, -33.06)
    assert conaf_dei.distance_km(square, -33.06, -71.40) == 0.0
    # Afuera: la distancia es al vértice más cercano (shortcut documentado, no al segmento).
    d = conaf_dei.distance_km(square, -33.06, -71.20)
    assert d == pytest.approx(haversine_km(-33.06, -71.20, -33.11, -71.35), abs=1e-9)
    assert conaf_dei.distance_km({"type": "Point", "coordinates": [-71.4, -33.06]}, -33.06, -71.40) == float("inf")


def test_vertices_are_lon_lat_not_lat_lon():
    """Si los vértices se leyeran [lat, lon], el punto (-33.06, -71.40) quedaría afuera:
    con el orden invertido el cuadrado estaría centrado en lat -71.4 (en la Antártica)."""
    square = _square(-71.40, -33.06)
    assert conaf_dei._inside(square["coordinates"][0], -33.06, -71.40) is True
    assert conaf_dei._inside(square["coordinates"][0], -71.40, -33.06) is False


def test_a_real_hole_cancels_the_interior():
    """Contrato de `crossings % 2`: el punto en el hoyo toca dos anillos (par) → fuera."""
    ring = _square(-71.40, -33.06)["coordinates"][0]
    hole = [[-71.41, -33.07], [-71.39, -33.07], [-71.39, -33.05], [-71.41, -33.05], [-71.41, -33.07]]
    donut = {"type": "Polygon", "coordinates": [ring, hole]}
    assert conaf_dei.distance_km(donut, -33.06, -71.40) > 0  # en el hueco no cuenta como dentro
    assert conaf_dei.distance_km(donut, -33.09, -71.40) == 0.0  # en la banda del anillo sí
    assert conaf_dei.distance_km(donut, -33.06, -71.40) == pytest.approx(
        haversine_km(-33.06, -71.40, -33.07, -71.41), abs=1e-9
    )  # y la distancia mide al borde del hoyo


def test_multipolygon_with_two_parts():
    ring_a = _square(-71.40, -33.06)["coordinates"][0]
    ring_b = _square(-71.00, -33.06)["coordinates"][0]
    multi = {"type": "MultiPolygon", "coordinates": [[ring_a], [ring_b]]}
    assert conaf_dei.distance_km(multi, -33.06, -71.40) == 0.0  # dentro de la primera parte
    assert conaf_dei.distance_km(multi, -33.06, -71.00) == 0.0  # dentro de la segunda parte
    assert conaf_dei.distance_km(multi, -33.06, -71.20) > 0  # entre ambas: fuera


# ----------------------------------------------------------------------- pick_perimeter


def test_pick_prefers_the_polygon_containing_the_point_over_a_closer_one():
    here = _norm("A", -71.40, -33.06)  # contiene al punto
    near = _norm("B", -71.55, -33.06)  # no lo contiene pero su borde queda a ~10 km
    assert conaf_dei.pick_perimeter([near, here], -33.06, -71.40)["id_if"] == "A"


def test_pick_chooses_the_closest_when_nothing_contains_the_point():
    near = _norm("B", -71.55, -33.06)
    far = _norm("C", -70.0, -33.0)
    picked = conaf_dei.pick_perimeter([far, near], -33.20, -71.40)
    assert picked["id_if"] == "B"
    assert conaf_dei.pick_perimeter([], -33.06, -71.40) is None


# ----------------------------------------------------------------------- fetch_perimeters (errores)


def test_fetch_raises_conaf_dei_error_on_http_500():
    with pytest.raises(conaf_dei.ConafDeiError):
        _fetch(None, status=500)


def test_fetch_raises_conaf_dei_error_on_invalid_json():
    with pytest.raises(conaf_dei.ConafDeiError):
        _fetch("esto no es json")


def test_fetch_raises_conaf_dei_error_on_arcgis_error_payload():
    with pytest.raises(conaf_dei.ConafDeiError, match="499"):
        _fetch({"error": {"code": 499, "message": "Token Required"}})


def test_fetch_drops_features_without_geometry():
    found = _fetch(_geojson(_feature(), {"type": "Feature", "properties": {"ID_IF": "sin-geometria"}}))
    assert [p["id_if"] for p in found] == ["612-SAN CARLOS"]


def test_fetch_queries_with_a_lon_lat_envelope_in_epsg_4326():
    """El envelope va `lon_min,lat_min,lon_max,lat_max` y la consulta entera en WGS84:
    invertido pediría perímetros en el Pacífico y devolvería vacío sin que se note."""

    async def go():
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen.update(dict(request.url.params))
            return json_response(_geojson())

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await conaf_dei.fetch_perimeters(client, -33.06, -71.40)
        return seen

    seen = asyncio.run(go())
    w, s, e, n = (float(v) for v in seen["geometry"].split(","))
    pad = conaf_dei.ENVELOPE_PAD_DEG
    assert (w, s, e, n) == pytest.approx((-71.40 - pad, -33.06 - pad, -71.40 + pad, -33.06 + pad), abs=1e-9)
    assert seen["inSR"] == "4326" and seen["outSR"] == "4326" and seen["f"] == "geojson"

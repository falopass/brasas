"""Proveedor OpenStreetMap/Overpass: consulta, parseo y reintentos ante un 429 pasajero."""

import asyncio

import httpx
import pytest

from backend.providers import overpass

BODY = {
    "elements": [
        {"type": "node", "id": 10, "lat": -35.426, "lon": -71.665, "tags": {"amenity": "hospital", "name": "Hospital de Talca"}},
        {"type": "way", "id": 20, "center": {"lat": -35.42, "lon": -71.65}, "tags": {"emergency": "assembly_point"}},
    ]
}


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_query_carries_radius_and_five_decimal_coords():
    query = overpass.build_query(-35.4267891, -71.6654321, 12000)
    assert "(around:12000,-35.42679,-71.66543)" in query
    assert '"emergency"="assembly_point"' in query
    assert '"amenity"~"^(hospital|clinic|fire_station|police)$"' in query


def test_parse_keeps_node_way_and_relation_with_center():
    elements = [
        {"type": "node", "id": 10, "lat": -35.4, "lon": -71.6, "tags": {"amenity": "hospital", "name": "Hospital"}},
        {"type": "way", "id": 20, "center": {"lat": -35.41, "lon": -71.61}, "tags": {"amenity": "fire_station"}},
        {"type": "relation", "id": 30, "center": {"lat": -35.42, "lon": -71.62}, "tags": {"emergency": "assembly_point", "name": "Plaza"}},
    ]
    result = overpass.parse(elements)
    assert [p["kind"] for p in result] == ["hospital", "fire_station", "assembly_point"]
    assert result[0]["id"] == "node/10" and result[0]["kind_label"] == "Hospital"
    assert result[1]["name"] == "Cuartel de Bomberos"  # sin nombre propio: la etiqueta del tipo
    assert result[2]["id"] == "relation/30" and result[2]["lat"] == -35.42


def test_parse_discards_unknown_amenity_and_missing_coords():
    elements = [
        {"type": "node", "id": 40, "lat": -35.43, "lon": -71.63, "tags": {"amenity": "school"}},
        {"type": "node", "id": 50, "tags": {"amenity": "clinic"}},
        {"type": "way", "id": 60, "tags": {"amenity": "hospital"}},  # ni lat/lon ni center
    ]
    assert overpass.parse(elements) == []


def test_429_then_200_returns_points(monkeypatch):
    monkeypatch.setattr(overpass, "WAITS_S", (0, 0))
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(429) if len(calls) == 1 else httpx.Response(200, json=BODY)

    async def run():
        async with _client(handler) as client:
            return await overpass.nearby(client, -35.43, -71.66)

    points = asyncio.run(run())
    assert len(calls) == 2
    assert [p["name"] for p in points] == ["Hospital de Talca", "Punto de encuentro"]
    assert calls[0].extensions["timeout"]["read"] == 20  # timeout explícito por solicitud


def test_three_failures_raise_overpass_error(monkeypatch):
    monkeypatch.setattr(overpass, "WAITS_S", (0, 0))
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(503)

    async def run():
        async with _client(handler) as client:
            await overpass.nearby(client, -35.43, -71.66)

    with pytest.raises(overpass.OverpassError):
        asyncio.run(run())
    assert len(calls) == 3


def test_connect_timeout_is_retried_then_raises(monkeypatch):
    monkeypatch.setattr(overpass, "WAITS_S", (0, 0))
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        raise httpx.ConnectTimeout("se agotó la conexión", request=request)

    async def run():
        async with _client(handler) as client:
            await overpass.nearby(client, -35.43, -71.66)

    with pytest.raises(overpass.OverpassError):
        asyncio.run(run())
    assert len(calls) == 3


def test_404_is_not_retried(monkeypatch):
    monkeypatch.setattr(overpass, "WAITS_S", (0, 0))
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(404)

    async def run():
        async with _client(handler) as client:
            await overpass.nearby(client, -35.43, -71.66)

    with pytest.raises(overpass.OverpassError):
        asyncio.run(run())
    assert len(calls) == 1


def test_500_is_retried_three_times_then_raises(monkeypatch):
    monkeypatch.setattr(overpass, "WAITS_S", (0, 0))
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(500)

    async def run():
        async with _client(handler) as client:
            await overpass.nearby(client, -35.43, -71.66)

    with pytest.raises(overpass.OverpassError):
        asyncio.run(run())
    assert len(calls) == 3


def test_429_is_retried_three_times_then_raises(monkeypatch):
    monkeypatch.setattr(overpass, "WAITS_S", (0, 0))
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(429)

    async def run():
        async with _client(handler) as client:
            await overpass.nearby(client, -35.43, -71.66)

    with pytest.raises(overpass.OverpassError):
        asyncio.run(run())
    assert len(calls) == 3


# Frontera: un lugar de borde recibe puntos de países vecinos si no se filtra por territorio.
BORDER_BODY = {
    "elements": [
        {"type": "node", "id": 101, "lat": -40.1, "lon": -71.5, "tags": {"amenity": "hospital", "name": "Hospital de Argentina"}},
        {"type": "node", "id": 102, "lat": -39.282, "lon": -71.976, "tags": {"amenity": "hospital", "name": "Hospital de Pucón"}},
        {"type": "node", "id": 103, "lat": -39.278, "lon": -72.227, "tags": {"amenity": "fire_station", "name": "Cuartel de Villarrica"}},
    ]
}

VISVIRI_BODY = {
    "elements": [
        {"type": "node", "id": 201, "lat": -17.594, "lon": -69.481, "tags": {"amenity": "clinic", "name": "Posta de Visviri"}},
        {"type": "node", "id": 202, "lat": -17.57, "lon": -69.38, "tags": {"amenity": "hospital", "name": "Hospital de Bolivia"}},
        {"type": "node", "id": 203, "lat": -17.52, "lon": -69.52, "tags": {"amenity": "police", "name": "Comisaría de Perú"}},
    ]
}


def _nearby_with(body):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    async def run():
        async with _client(handler) as client:
            return await overpass.nearby(client, -39.28, -72.0)

    return asyncio.run(run())


def test_nearby_descarta_puntos_fuera_de_chile():
    points = _nearby_with(BORDER_BODY)
    assert len(points) == 2
    assert [p["name"] for p in points] == ["Hospital de Pucón", "Cuartel de Villarrica"]
    assert all((p["lat"], p["lon"]) != (-40.1, -71.5) for p in points)


def test_nearby_conserva_punto_chileno_de_borde_en_pucon():
    """Pucón (09115) está a menos de 12 km de Argentina: el filtro no lo puede descartar."""
    points = _nearby_with({"elements": [BORDER_BODY["elements"][1]]})
    assert [p["name"] for p in points] == ["Hospital de Pucón"]
    assert (points[0]["lat"], points[0]["lon"]) == (-39.282, -71.976)


def test_nearby_cerca_de_visviri_descarta_bolivia_y_peru():
    points = _nearby_with(VISVIRI_BODY)
    assert [p["name"] for p in points] == ["Posta de Visviri"]


def test_nearby_sin_comunas_cargadas_no_lanza(monkeypatch):
    from backend.geo import Territory

    monkeypatch.setattr(overpass, "territory", lambda: Territory({"features": []}, {"features": []}))
    assert _nearby_with(BORDER_BODY) == []

"""Proveedor OpenStreetMap/Overpass: consulta, parseo y reintentos ante un 429 pasajero."""
import asyncio

import httpx
import pytest

from backend.providers import overpass

BODY = {"elements": [
    {"type": "node", "id": 10, "lat": -35.426, "lon": -71.665,
     "tags": {"amenity": "hospital", "name": "Hospital de Talca"}},
    {"type": "way", "id": 20, "center": {"lat": -35.42, "lon": -71.65},
     "tags": {"emergency": "assembly_point"}},
]}


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_query_carries_radius_and_five_decimal_coords():
    query = overpass.build_query(-35.4267891, -71.6654321, 12000)
    assert "(around:12000,-35.42679,-71.66543)" in query
    assert '"emergency"="assembly_point"' in query
    assert '"amenity"~"^(hospital|clinic|fire_station|police)$"' in query


def test_parse_keeps_node_way_and_relation_with_center():
    elements = [
        {"type": "node", "id": 10, "lat": -35.4, "lon": -71.6,
         "tags": {"amenity": "hospital", "name": "Hospital"}},
        {"type": "way", "id": 20, "center": {"lat": -35.41, "lon": -71.61},
         "tags": {"amenity": "fire_station"}},
        {"type": "relation", "id": 30, "center": {"lat": -35.42, "lon": -71.62},
         "tags": {"emergency": "assembly_point", "name": "Plaza"}},
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

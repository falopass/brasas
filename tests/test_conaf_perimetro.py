"""OFI-17: perímetro oficial «Perimetro_final» de CONAF en la ficha del incidente.

La capa está tras `CONAF_PERIMETRO_ENABLED` (apagada por defecto) hasta la autorización
formal de OFI-03: la declaración «uso público citando a CONAF» está en algunos tableros
de GEPRIF, no en los servicios ArcGIS. Pruebas con fixtures, sin red.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx

from backend import incidents
from backend.providers import conaf_dei
from backend.services import stamp, utcnow
from tests.conftest import json_response
from tests.test_conaf import CSV_HEAD, fire_row
from tests.test_incidents import obs

EDIT_MS = 1772461422369  # EditDate de la capa viene en milisegundos epoch


def _square(lon: float, lat: float, half: float = 0.05) -> dict:
    ring = [
        [lon - half, lat - half],
        [lon + half, lat - half],
        [lon + half, lat + half],
        [lon - half, lat + half],
        [lon - half, lat - half],
    ]
    return {"type": "Polygon", "coordinates": [ring]}


def _feature(id_if: str = "612-SAN CARLOS", lon: float = -71.40, lat: float = -33.06, area: float = 639.6) -> dict:
    return {
        "type": "Feature",
        "geometry": _square(lon, lat),
        "properties": {
            "ID_IF": id_if,
            "REGION": "VALPO",
            "Superficie_hectareas": area,
            "Patron_propagacion": "Viento",
            "EditDate": EDIT_MS,
        },
    }


def _geojson(*features: dict) -> dict:
    return {"type": "FeatureCollection", "features": list(features)}


def _norm(id_if: str, lon: float, lat: float) -> dict:
    """La forma normalizada que consume pick_perimeter (salida de fetch_perimeters)."""
    return {"id_if": id_if, "region": None, "area_ha": None, "pattern": None, "edited_at": None, "geometry": _square(lon, lat)}


def test_pick_returns_the_polygon_containing_the_point():
    here = _norm("A", -71.40, -33.06)
    far = _norm("B", -70.0, -33.0)
    assert conaf_dei.pick_perimeter([far, here], -33.06, -71.40)["id_if"] == "A"
    # Sin contención gana el borde más cercano (el punto queda ~10 km bajo «A», ~90 km de «B»).
    assert conaf_dei.pick_perimeter([_norm("B", -70.0, -33.0), here], -33.20, -71.40)["id_if"] == "A"
    assert conaf_dei.pick_perimeter([], -33.06, -71.40) is None


def test_distance_recognizes_holes_and_multipolygons():
    ring = _square(-71.40, -33.06)["coordinates"][0]
    hole = [[-71.41, -33.07], [-71.39, -33.07], [-71.39, -33.05], [-71.41, -33.05], [-71.41, -33.07]]
    donut = {"type": "Polygon", "coordinates": [ring, hole]}
    assert conaf_dei.distance_km(donut, -33.06, -71.40) > 0  # dentro del hoyo: fuera del polígono
    assert conaf_dei.distance_km(donut, -33.10, -71.40) == 0.0  # en el anillo: dentro
    multi = {"type": "MultiPolygon", "coordinates": [[ring]]}
    assert conaf_dei.distance_km(multi, -33.06, -71.40) == 0.0


def test_fetch_uses_an_envelope_and_normalizes_fields():
    async def go():
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen.update(dict(request.url.params))
            return json_response(_geojson(_feature()))

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            found = await conaf_dei.fetch_perimeters(client, -33.06, -71.40)
        assert seen["geometryType"] == "esriGeometryEnvelope" and seen["f"] == "geojson" and seen["outSR"] == "4326"
        w, s, e, n = (float(v) for v in seen["geometry"].split(","))
        assert w < -71.40 < e and s < -33.06 < n
        [p] = found
        assert p["id_if"] == "612-SAN CARLOS" and p["area_ha"] == 639.6 and p["pattern"] == "Viento"
        assert p["edited_at"] == datetime.fromtimestamp(EDIT_MS / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        assert p["geometry"]["type"] == "Polygon"

    asyncio.run(go())


def _linked_incident(db, fire_id: str = "11"):
    """Un incidente con evidencia al lado del incendio oficial, ya confirmado por link_official."""
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    [inc] = incidents.update(db, [obs(db, "sat", -33.061, -71.401, when=now - timedelta(minutes=50))], now)
    return inc, now


def _csv(fire_id: str = "11") -> str:
    local = (datetime.now(timezone.utc) - timedelta(minutes=40)).astimezone(ZoneInfo("America/Santiago")).strftime("%Y-%m-%d %H:%M")
    return CSV_HEAD + fire_row(fire_id, "SAN CARLOS", "En combate", local, -33.06, -71.40)


def test_perimeter_is_off_by_default(make_client, web):
    """Sin el flag no se consulta la capa y la ficha no trae `official_perimeter`."""
    web.add(lambda r: "githubusercontent" in r.url.host, lambda r: httpx.Response(200, text=_csv()))
    web.add(lambda r: "arcgis.com" in r.url.host, lambda r: httpx.Response(500))
    with make_client(GOES_ENABLED="0") as client:
        svc = client.app.state.services
        inc, _ = _linked_incident(svc.db)
        result = asyncio.run(svc.ingest_official_fires())
        assert result["official_linked"] == 1 and result["official_perimeters"] == 0
        assert not any("Perimetro_final" in r.url.path for r in web.requests)
        assert client.get(f"/api/incidents/{inc['id']}").json()["official_perimeter"] is None


def test_perimeter_is_fetched_once_and_shown_in_the_detail(make_client, web):
    web.add(lambda r: "githubusercontent" in r.url.host, lambda r: httpx.Response(200, text=_csv()))
    web.add(lambda r: "Perimetro_final" in r.url.path, lambda r: json_response(_geojson(_feature())))
    with make_client(GOES_ENABLED="0", CONAF_PERIMETRO_ENABLED="1") as client:
        svc = client.app.state.services
        inc, _ = _linked_incident(svc.db)
        result = asyncio.run(svc.ingest_official_fires())
        assert result["official_linked"] == 1 and result["official_perimeters"] == 1
        blob = json.loads(svc.db.kv_get("perimetro:11"))
        assert blob["perimeter"]["id_if"] == "612-SAN CARLOS" and blob["checked_at"]
        detail = client.get(f"/api/incidents/{inc['id']}").json()
        p = detail["official_perimeter"]
        assert p["area_ha"] == 639.6 and p["geometry"]["type"] == "Polygon"
        assert p["source"]["url"].startswith("https://")
        calls = sum(1 for r in web.requests if "Perimetro_final" in r.url.path)
        asyncio.run(svc.ingest_official_fires())  # el ETag da 304 y el perímetro sigue fresco
        assert sum(1 for r in web.requests if "Perimetro_final" in r.url.path) == calls


def test_a_missing_perimeter_is_cached_and_retried_daily_not_per_cycle(make_client, web):
    web.add(lambda r: "githubusercontent" in r.url.host, lambda r: httpx.Response(200, text=_csv()))
    web.add(lambda r: "Perimetro_final" in r.url.path, lambda r: json_response(_geojson()))
    with make_client(GOES_ENABLED="0", CONAF_PERIMETRO_ENABLED="1") as client:
        svc = client.app.state.services
        _linked_incident(svc.db)
        asyncio.run(svc.ingest_official_fires())
        assert sum(1 for r in web.requests if "Perimetro_final" in r.url.path) == 1
        asyncio.run(svc.ingest_official_fires())
        assert sum(1 for r in web.requests if "Perimetro_final" in r.url.path) == 1  # «no hay» también se cachea 24 h
        # Vencido el caché vuelve a consultar y encuentra la huella.
        svc.db.kv_set("perimetro:11", json.dumps({"checked_at": stamp(utcnow() - timedelta(hours=25)), "perimeter": None}))
        asyncio.run(svc.ingest_official_fires())
        assert svc.db.kv_get("perimetro:11") and json.loads(svc.db.kv_get("perimetro:11"))["perimeter"] is None


def test_a_failed_fetch_keeps_the_last_valid_perimeter(make_client, web):
    web.add(lambda r: "githubusercontent" in r.url.host, lambda r: httpx.Response(200, text=_csv()))
    arcgis = {"down": False}
    web.add(
        lambda r: "Perimetro_final" in r.url.path, lambda r: httpx.Response(500) if arcgis["down"] else json_response(_geojson(_feature()))
    )
    with make_client(GOES_ENABLED="0", CONAF_PERIMETRO_ENABLED="1") as client:
        svc = client.app.state.services
        inc, _ = _linked_incident(svc.db)
        asyncio.run(svc.ingest_official_fires())
        saved = json.loads(svc.db.kv_get("perimetro:11"))
        # La capa cae y el caché está vencido: la ficha sigue sirviendo la última versión válida.
        arcgis["down"] = True
        saved["checked_at"] = stamp(utcnow() - timedelta(hours=25))
        svc.db.kv_set("perimetro:11", json.dumps(saved))
        asyncio.run(svc.ingest_official_fires())
        assert json.loads(svc.db.kv_get("perimetro:11"))["perimeter"]["id_if"] == "612-SAN CARLOS"
        assert client.get(f"/api/incidents/{inc['id']}").json()["official_perimeter"]["id_if"] == "612-SAN CARLOS"

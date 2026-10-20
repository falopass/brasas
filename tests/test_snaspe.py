"""Áreas protegidas SNASPE (OFI-27): forma del JSON versionado y proximidad al incidente.

El JSON lo genera scripts/local/build_snaspe.py desde la capa `SNASPE` de CONAF-GEPRIF y lo
consulta backend/geo.py para la ficha del incidente. Ninguna prueba toca la red: la
proximidad se ejercita con polígonos de fixture en memoria.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from shapely.geometry import shape

from backend import geo, incidents

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "local"))
import build_snaspe as snaspe  # noqa: E402

DATA = ROOT / "web" / "data" / "snaspe.json"

# Encuadre amplio de Chile (incluye islas oceánicas), como en test_data_files.
LON_MIN, LON_MAX = -110, -66
LAT_MIN, LAT_MAX = -56, -17

# Dos áreas de fixture: «A» es un cuadrado de ~0,1° x ~0,1° y «B» otro más al este.
AREA_A = {"type": "Polygon", "coordinates": [[[-70.6, -33.6], [-70.5, -33.6], [-70.5, -33.5], [-70.6, -33.5], [-70.6, -33.6]]]}
AREA_B = {"type": "Polygon", "coordinates": [[[-70.35, -33.6], [-70.3, -33.6], [-70.3, -33.5], [-70.35, -33.5], [-70.35, -33.6]]]}


def _fixture_areas():
    return (
        {"name": "Área A", "category": "Parque Nacional", "region": "Maule", "geom": shape(AREA_A)},
        {"name": "Área B", "category": "Reserva Nacional", "region": "Maule", "geom": shape(AREA_B)},
    )


@pytest.fixture
def areas(monkeypatch):
    monkeypatch.setattr(geo, "_snaspe_areas", _fixture_areas)


def _load():
    with open(DATA, encoding="utf-8") as f:
        return json.load(f)


def _walk_rings(geom):
    polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
    for poly in polys:
        yield from poly


def test_snaspe_json():
    data = _load()
    source = data["source"]
    assert source["name"] == "CONAF-GEPRIF"
    assert source["url"].startswith("https://services5.arcgis.com/")
    assert source["attribution"] and source["fetched_at"]

    items = data["items"]
    assert isinstance(items, list) and len(items) >= 90, f"solo {len(items)} áreas protegidas"

    seen = set()
    for i in items:
        assert set(i) == {"name", "category", "region", "geometry"}, f"claves inesperadas: {i}"
        assert i["name"] and i["name"] == i["name"].strip() and i["name"].isprintable(), f"nombre mal normalizado: {i['name']!r}"
        assert i["category"] in {"Parque Nacional", "Reserva Nacional", "Monumento Natural"}, f"categoría inesperada: {i['category']}"
        assert i["name"].upper() not in seen, f"nombre duplicado: {i['name']}"
        seen.add(i["name"].upper())
        geom = i["geometry"]
        assert geom["type"] in ("Polygon", "MultiPolygon"), f"geometría inesperada: {geom['type']}"
        for ring in _walk_rings(geom):
            assert len(ring) >= 4, f"{i['name']}: anillo con menos de 4 vértices"
            for lon, lat in ring:
                assert LAT_MIN <= lat <= LAT_MAX, f"{i['name']}: lat fuera de Chile"
                assert LON_MIN <= lon <= LON_MAX, f"{i['name']}: lon fuera de Chile"


def test_inside_polygon(areas):
    # Centro del cuadrado A (-70,55; -33,55).
    [hit] = geo.protected_areas_near(-33.55, -70.55)
    assert hit["name"] == "Área A" and hit["inside"] is True and hit["distance_km"] == 0.0
    assert hit["category"] == "Parque Nacional" and hit["region"] == "Maule"


def test_nearest_area_and_distance(areas):
    # A ~10 km del borde este de A (0,108° a lat -33,55 ≈ 10 km) y ~4 km del borde oeste de B.
    hits = geo.protected_areas_near(-33.55, -70.392, max_km=15)
    assert [h["name"] for h in hits] == ["Área B", "Área A"]
    assert hits[0]["inside"] is False and 3 <= hits[0]["distance_km"] <= 5
    assert 9 <= hits[1]["distance_km"] <= 11
    # Con el umbral por defecto (5 km) solo queda la más cercana.
    assert [h["name"] for h in geo.protected_areas_near(-33.55, -70.392)] == ["Área B"]


def test_none_near():
    # Pacífico, lejos de cualquier área protegida.
    assert geo.protected_areas_near(-30.0, -80.0) == []


def test_real_area_inside():
    # Un punto dentro de un polígono real del archivo versionado.
    conguillio = next(a for a in geo._snaspe_areas() if a["name"] == "Parque Nacional Conguillío")
    point = conguillio["geom"].representative_point()
    [hit] = geo.protected_areas_near(point.y, point.x)
    assert hit["name"] == "Parque Nacional Conguillío" and hit["inside"] is True


def test_normalize_and_dedupe():
    feat = {
        "properties": {"Nombre": "  Parque\x81 Nacional  Prueba ", "Categoria": "Parque Nacional", "Region": "  Maule "},
        "geometry": AREA_A,
    }
    item = snaspe.normalize(feat)
    assert item["name"] == "Parque Nacional Prueba" and item["region"] == "Maule"
    assert snaspe.normalize({"properties": {"Nombre": "X"}, "geometry": None}) is None
    assert (
        snaspe.normalize(
            {"properties": {"Nombre": "X", "Categoria": "Parque Nacional"}, "geometry": {"type": "Point", "coordinates": [-70, -33]}}
        )
        is None
    )

    # Dos partes del mismo nombre se publican como una sola entrada (MultiPolygon).
    other = item | {"geometry": AREA_B}
    [merged] = snaspe.dedupe([item, other])
    assert merged["name"] == "Parque Nacional Prueba" and merged["geometry"]["type"] == "MultiPolygon"
    assert len(merged["geometry"]["coordinates"]) == 2


def test_incident_detail_protected_area(make_client, monkeypatch):
    """La ficha expone `protected_area`: el área más cercana o null si no hay ninguna cerca."""
    from tests.test_incidents import obs

    monkeypatch.setattr(geo, "_snaspe_areas", _fixture_areas)
    with make_client() as client:
        db = client.app.state.services.db
        now = datetime.now(timezone.utc).replace(microsecond=0)
        [inc] = incidents.update(db, [obs(db, "a", -33.55, -70.55, when=now)], now)
        detail = client.get(f"/api/incidents/{inc['id']}").json()
        assert detail["protected_area"]["name"] == "Área A" and detail["protected_area"]["inside"] is True

        [far] = incidents.update(db, [obs(db, "b", -30.0, -80.0, when=now)], now)
        detail = client.get(f"/api/incidents/{far['id']}").json()
        assert detail["protected_area"] is None

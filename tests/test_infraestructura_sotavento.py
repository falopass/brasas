"""OSM-SOTAVENTO: infraestructura crítica a sotavento (5 km, cono ±60°)."""

from __future__ import annotations

import math

import httpx
import pytest

from backend.geo import EARTH_RADIUS_KM, angle_diff, bearing_deg, haversine_km
from backend.providers import overpass
from backend.settings import ROOT

OVERPASS_HOST = "overpass-api.de"
LAT, LON = -35.426, -71.665  # Talca, dentro del territorio


def _destino(lat: float, lon: float, rumbo: float, km: float) -> tuple[float, float]:
    distancia = km / EARTH_RADIUS_KM
    brg = math.radians(rumbo)
    p1, l1 = math.radians(lat), math.radians(lon)
    p2 = math.asin(math.sin(p1) * math.cos(distancia) + math.cos(p1) * math.sin(distancia) * math.cos(brg))
    l2 = l1 + math.atan2(
        math.sin(brg) * math.sin(distancia) * math.cos(p1),
        math.cos(distancia) - math.sin(p1) * math.sin(p2),
    )
    return math.degrees(p2), (math.degrees(l2) + 540) % 360 - 180


def _punto(lat: float, lon: float, *, kind: str = "school", name: str = "Escuela") -> dict:
    category, _, label = overpass.classify_critical_tags({"amenity": kind} if kind in {"school", "kindergarten", "hospital", "clinic", "doctors"} else {"power": kind})
    return {
        "id": f"node/{name}",
        "category": category,
        "kind": kind,
        "kind_label": label,
        "name": name,
        "lat": lat,
        "lon": lon,
    }


def test_consulta_pide_cinco_km_y_los_tags_criticos():
    query = overpass.build_critical_query(-35.42678, -71.66543)
    assert "(around:5000,-35.42678,-71.66543)" in query
    for tag in (
        "school",
        "kindergarten",
        "hospital",
        "clinic",
        "doctors",
        "substation",
        "plant",
        "line",
        "water_works",
        "wastewater_plant",
        "water_tower",
    ):
        assert tag in query


@pytest.mark.parametrize(
    ("tags", "category", "kind"),
    [
        ({"amenity": "school"}, "escuelas", "school"),
        ({"amenity": "kindergarten"}, "escuelas", "kindergarten"),
        ({"amenity": "hospital"}, "salud", "hospital"),
        ({"amenity": "clinic"}, "salud", "clinic"),
        ({"amenity": "doctors"}, "salud", "doctors"),
        ({"power": "substation"}, "energia", "substation"),
        ({"power": "plant"}, "energia", "plant"),
        ({"power": "line"}, "energia", "line"),
        ({"man_made": "water_works"}, "agua", "water_works"),
        ({"man_made": "wastewater_plant"}, "agua", "wastewater_plant"),
        ({"man_made": "water_tower"}, "agua", "water_tower"),
        ({"amenity": "cafe"}, None, None),
        ({}, None, None),
    ],
)
def test_clasifica_tags_osm(tags, category, kind):
    classified = overpass.classify_critical_tags(tags)
    if category is None:
        assert classified is None
    else:
        assert classified[0] == category and classified[1] == kind


def test_parse_critical_conserva_chile_y_descarta_el_resto():
    elements = [
        {"type": "node", "id": 1, "lat": LAT, "lon": LON, "tags": {"amenity": "school", "name": "Escuela de Talca"}},
        {"type": "way", "id": 2, "center": {"lat": LAT + 0.01, "lon": LON}, "tags": {"power": "substation"}},
        {"type": "node", "id": 3, "lat": -32.889, "lon": -68.845, "tags": {"amenity": "hospital", "name": "Hospital de Mendoza"}},
        {"type": "node", "id": 4, "lat": LAT, "lon": LON, "tags": {"amenity": "cafe", "name": "Café"}},
        {"type": "node", "id": 5, "tags": {"amenity": "clinic"}},
    ]
    rows = overpass.parse_critical(elements)
    assert [(row["kind"], row["category"]) for row in rows] == [("school", "escuelas"), ("substation", "energia")]
    assert rows[0]["name"] == "Escuela de Talca"
    assert rows[1]["name"] == "Subestación eléctrica"


def test_sotavento_usa_el_rumbo_opuesto_el_cono_y_el_tope_de_5_km():
    """(wind_dir + 180) % 360, incluido el borde del cono, y fuera lo que pasa de 5 km."""
    wind = 180.0
    advance = (wind + 180.0) % 360.0
    assert advance == 0.0
    casos = {"norte": (0, 2.0), "borde": (60, 2.0), "fuera del cono": (70, 2.0), "lejos": (0, 6.0), "sur": (180, 2.0)}
    items = []
    for nombre, (rumbo, km) in casos.items():
        plat, plon = _destino(LAT, LON, rumbo, km)
        punto = _punto(plat, plon, name=nombre)
        punto["id"] = nombre
        items.append(punto)
        assert haversine_km(LAT, LON, plat, plon) == pytest.approx(km, abs=0.05)
        assert angle_diff(bearing_deg(LAT, LON, plat, plon), advance) == pytest.approx(min(rumbo, 360 - rumbo), abs=0.5)

    body = overpass.filter_downwind_infrastructure(LAT, LON, wind, items)
    assert body["wind_advance_deg"] == 0.0
    assert body["cone_deg"] == 60.0 and body["radius_km"] == 5.0
    esperados = set()
    en_radio = 0
    for item in items:
        dist = haversine_km(LAT, LON, item["lat"], item["lon"])
        if dist > 5:
            continue
        en_radio += 1
        if angle_diff(bearing_deg(LAT, LON, item["lat"], item["lon"]), advance) <= 60:
            esperados.add(item["id"])
    assert "norte" in esperados and "sur" not in esperados and "lejos" not in esperados
    assert {item["id"] for item in body["items"]} == esperados
    assert all(item["downwind"] and item["distance_km"] <= 5 for item in body["items"])
    assert body["total_downwind"] == len(esperados) and body["total_radius"] == en_radio
    assert body["counts"]["escuelas"] == len(esperados)

    borde = next(item for item in items if item["id"] == "borde")
    diff = angle_diff(bearing_deg(LAT, LON, borde["lat"], borde["lon"]), advance)
    assert overpass.filter_downwind_infrastructure(LAT, LON, wind, [borde], cone_deg=diff)["total_downwind"] == 1
    assert overpass.filter_downwind_infrastructure(LAT, LON, wind, [borde], cone_deg=max(0.0, diff - 0.2))["total_downwind"] == 0

    lejos = next(item for item in items if item["id"] == "lejos")
    dist = haversine_km(LAT, LON, lejos["lat"], lejos["lon"])
    assert overpass.filter_downwind_infrastructure(LAT, LON, wind, [lejos], radius_km=dist)["total_radius"] == 1
    assert overpass.filter_downwind_infrastructure(LAT, LON, wind, [lejos], radius_km=dist - 0.01)["total_radius"] == 0


def _incidente(db) -> str:
    iid = "a1b2c3d4e5f6"
    stamp = "2026-11-04T15:00:00Z"
    db.execute(
        "INSERT INTO incidents(id, status, status_changed_at, first_seen_at, last_seen_at, lat, lon, "
        "min_lat, max_lat, min_lon, max_lon, n_obs, n_reliable, sensors, max_frp, comuna_code, "
        "fixed_source, official_ref, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (iid, "posible", stamp, stamp, stamp, LAT, LON, LAT, LAT, LON, LON, 2, 2, "ABI", 12.0, None, 0, None, stamp),
    )
    return iid


def _elementos():
    escuela = _destino(LAT, LON, 0, 1.5)
    hospital = _destino(LAT, LON, 180, 1.5)
    lejos = _destino(LAT, LON, 0, 6.0)
    return {
        "elements": [
            {"type": "node", "id": 10, "lat": escuela[0], "lon": escuela[1], "tags": {"amenity": "school", "name": "Escuela Norte"}},
            {"type": "node", "id": 11, "lat": hospital[0], "lon": hospital[1], "tags": {"amenity": "hospital", "name": "Hospital Sur"}},
            {"type": "node", "id": 12, "lat": lejos[0], "lon": lejos[1], "tags": {"power": "plant", "name": "Planta Lejana"}},
        ]
    }


def test_endpoint_marca_sotavento_con_overpass_simulado(make_client, web):
    overpass._INFRA_CACHE.clear()
    web.add(lambda request: request.url.host == OVERPASS_HOST, lambda request: httpx.Response(200, json=_elementos()))
    with make_client() as client:
        iid = _incidente(client.app.state.services.db)
        response = client.get(f"/api/incidents/{iid}/downwind-infrastructure", params={"wind_dir": 180})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["wind_advance_deg"] == 0.0
    assert body["source"].startswith("OpenStreetMap")
    assert [item["name"] for item in body["items"]] == ["Escuela Norte"]
    escuela = body["items"][0]
    assert escuela["downwind"] is True
    assert escuela["category"] == "escuelas"
    assert escuela["distance_km"] <= 5
    assert "bearing_deg" in escuela
    assert body["counts"]["salud"] == 0 and body["counts_radius"]["salud"] == 1
    assert body["total_radius"] == 2
    pedido = next(request for request in web.requests if request.url.host == OVERPASS_HOST)
    assert b"around%3A5000" in pedido.content or b"around:5000" in pedido.content


def test_endpoint_no_inventa_ceros_si_overpass_falla(make_client, web):
    overpass._INFRA_CACHE.clear()

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timeout", request=request)

    web.add(lambda request: request.url.host == OVERPASS_HOST, handler)
    with make_client() as client:
        iid = _incidente(client.app.state.services.db)
        response = client.get(f"/api/incidents/{iid}/downwind-infrastructure", params={"wind_dir": 90})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "unavailable"
    assert body["counts"] is None and body["total_downwind"] is None and body["total_radius"] is None
    assert body["items"] == []
    assert "OpenStreetMap" in body["note"]


def test_endpoint_vacio_si_es_un_cero_real(make_client, web):
    overpass._INFRA_CACHE.clear()
    web.add(lambda request: request.url.host == OVERPASS_HOST, lambda request: httpx.Response(200, json={"elements": []}))
    with make_client() as client:
        iid = _incidente(client.app.state.services.db)
        response = client.get(f"/api/incidents/{iid}/downwind-infrastructure", params={"wind_dir": 90})
    body = response.json()
    assert response.status_code == 200 and body["status"] == "ok"
    assert body["counts"] == {"escuelas": 0, "salud": 0, "energia": 0, "agua": 0}
    assert body["total_downwind"] == 0


def test_ficha_muestra_openstreetmap_fuera_de_dual():
    """El enlace se ve en lectura sencilla y detallada: no vive dentro de dual() ni de x-tech."""
    ficha = (ROOT / "web/js/views/incendio.js").read_text(encoding="utf-8")
    api = (ROOT / "web/js/api.js").read_text(encoding="utf-8")
    bloque = ficha.split("const downwindBlock", 1)[1].split("function render", 1)[0]
    assert "downwindInfrastructure" in api and "downwindInfrastructure" in ficha
    assert "Infraestructura sensible en la dirección del viento (5 km)" in bloque
    assert "dual(" not in bloque and "x-plain" not in bloque and "x-tech" not in bloque
    assert 'href="https://www.openstreetmap.org/copyright"' in bloque
    assert ">OpenStreetMap</a>" in bloque
    assert "${downwindBlock(infra)}" in ficha

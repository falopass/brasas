"""Guarda de los perímetros oficiales de los casos de Historia (CONT-08).

Los archivos web/data/cases/<id>.perimeter.json los genera
scripts/local/build_perimetros_casos.py desde la capa
PERÍMETROS_HISTORICOS_2014_2024_CON_SEMANA_DEL_AÑO de CONAF-GEPRIF y los consume
web/js/views/casos.js como capa apagable «Perímetro oficial CONAF». Ninguna
prueba toca la red: el emparejamiento se ejercita con fixtures en memoria.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "local"))
import build_perimetros_casos as per  # noqa: E402
from backend.providers import conaf_dei  # noqa: E402

DATA = ROOT / "web" / "data"
CASES_DIR = DATA / "cases"

# Encuadre amplio de Chile (incluye islas oceánicas), como en test_data_files.
LON_MIN, LON_MAX = -110, -66
LAT_MIN, LAT_MAX = -56, -17

MS_2017_01_20 = 1484870400000  # inicio oficial de «320 - LAS MAQUINAS»

CASE_FIRE = {
    "id": "las-maquinas-2017",
    "title": "Incendio Las Máquinas 2017",
    "scope": "fire",
    "start_utc": "2017-01-18T12:00:00Z",
    "end_utc": "2017-02-05T12:00:00Z",
    "bbox": [-72.75, -36.15, -71.85, -35.15],
}
CASE_COMPLEX = {
    "id": "vina-del-mar-2024",
    "title": "Megaincendio de Valparaíso 2024",
    "scope": "complex",
    "start_utc": "2024-02-02T12:00:00Z",
    "end_utc": "2024-02-05T12:00:00Z",
    "bbox": [-71.75, -33.25, -71.2, -32.95],
}


def _props(nombre="320 - LAS MAQUINAS", inicio=MS_2017_01_20, temporada="2016-2017", ha=100.0):
    return {"FID": 1, "Nombre": nombre, "inicio": inicio, "Temporada": temporada, "HA": ha}


def _feature(props=None, geom=None):
    return {
        "type": "Feature",
        "properties": props if props is not None else _props(),
        "geometry": geom
        if geom is not None
        else {"type": "Polygon", "coordinates": [[[-72.0, -35.5], [-72.0, -35.4], [-71.9, -35.4], [-71.9, -35.5], [-72.0, -35.5]]]},
    }


def _iter_coords(geom):
    """Todos los pares [lon, lat] de un Polygon o MultiPolygon."""
    coords = geom["coordinates"]
    if geom["type"] == "Polygon":
        coords = [coords]
    return (pair for poly in coords for ring in poly for pair in ring)


# ------------------------------------------------------------------ empareje (sin red)


def test_season_of():
    # Temporada de ocurrencia julio–junio, como la usa la capa.
    assert per.season_of(datetime(2023, 2, 5)) == "2022-2023"
    assert per.season_of(datetime(2023, 7, 1)) == "2023-2024"
    assert per.season_of(datetime(2023, 6, 30)) == "2022-2023"
    assert per.season_of(datetime(2014, 4, 12)) == "2013-2014"


def test_feature_name_quita_correlativo():
    assert per.feature_name({"Nombre": "320 - LAS MAQUINAS"}) == "LAS MAQUINAS"
    assert per.feature_name({"Nombre": "SAN PEDRO"}) == "SAN PEDRO"


def test_matches_fire_scope():
    # Temporada + fecha en ventana + una palabra significativa en común.
    assert per.matches(CASE_FIRE, _props())
    # Incendio vecino de la misma temporada y ventana: sin nombre en común, no calza.
    assert not per.matches(CASE_FIRE, _props(nombre="321 - SANTA CRUZ", ha=15589.2))
    # Temporada distinta ni siquiera entra a la comparación.
    assert not per.matches(CASE_FIRE, _props(temporada="2017-2018"))
    # Fuera de la ventana de ±5 días alrededor de start/end.
    assert not per.matches(CASE_FIRE, _props(inicio=1482364800000))  # 2016-12-22
    # Sin fecha oficial no hay empareje (no se aproxima).
    assert not per.matches(CASE_FIRE, _props(inicio=None))


def test_matches_complex_sin_filtro_de_nombre():
    # En un complejo cada polígono es un foco distinto: no se exige nombre compartido.
    props = _props(nombre="COMPLEJO LAS TABLAS- RESERVA LAGO PEÑUELAS", inicio=1706832000000, temporada="2023-2024", ha=8806.9)
    assert per.matches(CASE_COMPLEX, props)
    # Pero sí se mantienen temporada y ventana.
    assert not per.matches(CASE_COMPLEX, _props(nombre="X", inicio=1706832000000, temporada="2022-2023"))
    assert not per.matches(CASE_COMPLEX, _props(inicio=1702080000000, temporada="2023-2024"))  # dic-2023


def test_normalize():
    feat = per.normalize(_feature())
    assert feat["type"] == "Feature" and feat["geometry"]["type"] == "Polygon"
    p = feat["properties"]
    assert p["fid"] == 1 and p["nombre"] == "LAS MAQUINAS" and p["ha"] == 100.0
    assert p["inicio"] == "2017-01-20" and p["temporada"] == "2016-2017"

    # Sin geometría poligonal o sin superficie no hay nada que publicar.
    assert per.normalize(_feature(geom={"type": "Point", "coordinates": [-72, -35]})) is None
    sin_geom = _feature()
    sin_geom["geometry"] = None
    assert per.normalize(sin_geom) is None
    assert per.normalize(_feature(props=_props(ha=None))) is None

    # MultiPolygon pasa y las coordenadas quedan redondeadas a 5 decimales.
    multi = {"type": "MultiPolygon", "coordinates": [[[[-72.123456789, -35.5], [-72.1, -35.4], [-72.0, -35.5], [-72.123456789, -35.5]]]]}
    out = per.normalize(_feature(geom=multi))
    assert out["geometry"]["coordinates"][0][0][0] == [-72.12346, -35.5]


def test_build_case_sin_calce_no_inventa():
    raw = {"fetched_at": "2026-10-19T00:00:00+00:00", "features": [_feature(props=_props(nombre="321 - SANTA CRUZ"))]}
    assert per.build_case(CASE_FIRE, raw) is None


# ------------------------------------------------------------------ archivos publicados


def test_perimetros_publicados():
    files = sorted(CASES_DIR.glob("*.perimeter.json"))
    assert files, "no hay archivos de perímetro en web/data/cases"
    catalog = json.loads((DATA / "cases.json").read_text(encoding="utf-8"))
    by_id = {c["id"]: c for c in catalog["cases"]}

    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        cid = path.name.removesuffix(".perimeter.json")
        ctx = f"{path.name}"
        assert data["type"] == "FeatureCollection", ctx
        assert data["case_id"] == cid, f"{ctx}: case_id {data['case_id']!r} no calza con el nombre"
        assert cid in by_id, f"{ctx}: no existe el caso en cases.json"
        assert by_id[cid].get("perimeter") is True, f"{ctx}: falta «perimeter: true» en cases.json"

        # Toda geometría publicada declara su fuente, licencia y fecha de consulta.
        assert data["source"]["name"] == "CONAF — GEPRIF", ctx
        assert "CONAF" in data["source"]["attribution"], ctx
        assert data["source"]["url"].startswith("https://services5.arcgis.com/"), ctx
        assert "CONAF" in data["license"], ctx
        datetime.fromisoformat(data["fetched_at"])  # ISO válido
        assert data["match"]["inicio_desde"] <= data["match"]["inicio_hasta"], ctx

        assert data["features"], f"{ctx}: FeatureCollection sin features"
        seen_fids = set()
        for feature in data["features"]:
            assert feature["type"] == "Feature", ctx
            geom = feature["geometry"]
            assert geom["type"] in ("Polygon", "MultiPolygon"), f"{ctx}: {geom['type']}"
            for lon, lat in _iter_coords(geom):
                assert LON_MIN <= lon <= LON_MAX, f"{ctx}: lon {lon} fuera de Chile"
                assert LAT_MIN <= lat <= LAT_MAX, f"{ctx}: lat {lat} fuera de Chile"
            p = feature["properties"]
            assert p["fid"] not in seen_fids, f"{ctx}: fid repetido {p['fid']}"
            seen_fids.add(p["fid"])
            assert p["nombre"] and p["inicio"] and p["temporada"], f"{ctx}: propiedades incompletas {p}"
            assert isinstance(p["ha"], (int, float)) and p["ha"] > 0, f"{ctx}: ha inválida {p}"


# ------------------------------------------------- pick_perimeter (backend/providers/conaf_dei.py)


def _norm_conaf(id_if: str, geom: dict, edited_at: str | None = None, ha: float | None = None) -> dict:
    """La forma normalizada que consume pick_perimeter (salida de fetch_perimeters)."""
    return {"id_if": id_if, "region": None, "area_ha": ha, "pattern": None, "edited_at": edited_at, "geometry": geom}


def test_distance_tolera_anillos_con_altitud():
    """GeoJSON [lon, lat, alt] es legal y ArcGIS lo devuelve: no debe lanzar ni cambiar el resultado."""
    ring2 = [[-72.0, -35.5], [-72.0, -35.4], [-71.9, -35.4], [-71.9, -35.5], [-72.0, -35.5]]
    ring3 = [[lon, lat, 640.0] for lon, lat in ring2]
    geom2 = {"type": "Polygon", "coordinates": [ring2]}
    geom3 = {"type": "Polygon", "coordinates": [ring3]}
    assert conaf_dei.distance_km(geom3, -35.45, -71.95) == conaf_dei.distance_km(geom2, -35.45, -71.95) == 0.0
    assert conaf_dei.distance_km(geom3, -35.30, -71.95) == conaf_dei.distance_km(geom2, -35.30, -71.95)


def test_distance_mide_al_borde_no_al_vertice():
    """Un punto a 10 m del punto medio de una arista de ~90 m debe dar ~0,010 km, no los ~0,046 km
    que costaba medir al vértice más cercano (la capa llega simplificada a SIMPLIFY_DEG ≈ 90 m)."""
    ring = [[-0.0004, -0.0004], [0.0004, -0.0004], [0.0004, 0.0004], [-0.0004, 0.0004], [-0.0004, -0.0004]]
    geom = {"type": "Polygon", "coordinates": [ring]}
    # 10 m al sur del punto medio de la arista sur (lat ≈ −0.0004°, 1° lat ≈ 110,6 km).
    lat = -0.0004 - 10 / 110_600
    d = conaf_dei.distance_km(geom, lat, 0.0)
    assert 0.005 <= d <= 0.015, f"esperaba ~0,010 km y dio {d} km"


def test_pick_desempata_por_fecha_de_edicion_y_superficie():
    geom = {"type": "Polygon", "coordinates": [[[-72.0, -35.5], [-72.0, -35.4], [-71.9, -35.4], [-71.9, -35.5], [-72.0, -35.5]]]}
    lat, lon = -35.45, -71.95  # dentro de ambos: distancia 0 para los dos
    viejo = _norm_conaf("viejo", geom, edited_at="2024-02-03T10:00:00Z", ha=100.0)
    nuevo = _norm_conaf("nuevo", geom, edited_at="2024-02-04T10:00:00Z", ha=50.0)
    assert conaf_dei.pick_perimeter([viejo, nuevo], lat, lon)["id_if"] == "nuevo"
    # Misma fecha: gana el de mayor superficie.
    chico = _norm_conaf("chico", geom, edited_at="2024-02-04T10:00:00Z", ha=50.0)
    grande = _norm_conaf("grande", geom, edited_at="2024-02-04T10:00:00Z", ha=200.0)
    assert conaf_dei.pick_perimeter([chico, grande], lat, lon)["id_if"] == "grande"


def test_flag_perimeter_consistente():
    """«perimeter: true» en cases.json marca exactamente los casos con archivo publicado."""
    catalog = json.loads((DATA / "cases.json").read_text(encoding="utf-8"))
    for case in catalog["cases"]:
        exists = (CASES_DIR / f"{case['id']}.perimeter.json").exists()
        assert bool(case.get("perimeter")) == exists, (
            f"{case['id']}: flag perimeter={case.get('perimeter')} pero el archivo {'no existe' if case.get('perimeter') else 'existe'}"
        )

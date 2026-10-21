"""Guarda de los incendios nominados (OFI-19): forma del JSON versionado y normalización.

El JSON lo genera scripts/local/build_incendios_nominados.py desde la capa
PUNTOS_DE_INICIO_2002_2024_MAYOR_A_50_HA de CONAF-GEPRIF y lo consume
web/js/views/casos.js. Ninguna prueba toca la red: la normalización se ejercita
con una fixture en memoria.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "local"))
import build_incendios_nominados as nom  # noqa: E402

from backend.geo import _fold  # noqa: E402

DATA = ROOT / "web" / "data" / "incendios-nominados.json"
COMUNAS_INDEX = ROOT / "web" / "data" / "comunas-index.json"
SEASON_RE = re.compile(r"^(\d{4})-(\d{4})$")

# Encuadre amplio de Chile (incluye islas oceánicas), como en test_data_files.
LON_MIN, LON_MAX = -110, -66
LAT_MIN, LAT_MAX = -56, -17


def _load():
    with open(DATA, encoding="utf-8") as f:
        return json.load(f)


def _feat(nombre="EL  SAUCE ", comuna=" Coquimbo", temporada="2002-2003", superficie=65.5, x=-71.288333, y=-30.103889):
    return {
        "attributes": {"Nombre": nombre, "Comuna": comuna, "Temporada": temporada, "Superficie": superficie},
        "geometry": {"x": x, "y": y},
    }


def test_incendios_nominados_json():
    data = _load()
    source = data["source"]
    assert source["name"] == "CONAF-GEPRIF"
    assert source["url"].startswith("https://services5.arcgis.com/")
    assert source["attribution"] and source["fetched_at"]

    items = data["items"]
    assert isinstance(items, list) and len(items) >= 2500, f"solo {len(items)} incendios nominados"

    seen, seasons = set(), set()
    for i in items:
        assert set(i) == {"name", "comuna", "season", "ha", "lat", "lon"}, f"claves inesperadas: {i}"
        assert i["name"] and i["name"] == i["name"].strip(), f"nombre mal normalizado: {i}"
        assert i["comuna"] and i["comuna"] == i["comuna"].strip(), f"comuna mal normalizada: {i}"

        m = SEASON_RE.match(i["season"])
        assert m, f"temporada inválida: {i['season']!r}"
        assert int(m.group(2)) == int(m.group(1)) + 1, f"temporada no continua: {i['season']}"
        assert 2002 <= int(m.group(1)) <= 2023, f"temporada fuera de 2002-2024: {i['season']}"
        seasons.add(i["season"])

        assert isinstance(i["ha"], (int, float)) and i["ha"] > 0, f"superficie inválida: {i}"
        assert LAT_MIN <= i["lat"] <= LAT_MAX, f"lat fuera de Chile: {i}"
        assert LON_MIN <= i["lon"] <= LON_MAX, f"lon fuera de Chile: {i}"

        key = (i["name"].upper(), i["season"], i["comuna"].upper())
        assert key not in seen, f"duplicado nombre+temporada+comuna: {key}"
        seen.add(key)

    assert min(seasons) == "2002-2003" and max(seasons) == "2023-2024", "faltan temporadas del rango publicado"


def test_cobertura_declarada_es_la_de_los_datos():
    """OFI-206: la cobertura publicada es el rango real y la nota no promete temporadas que no están."""
    data = _load()
    coverage = data["coverage"]
    seasons = sorted({i["season"] for i in data["items"]})
    assert coverage == {"from": seasons[0], "to": seasons[-1]}, f"cobertura {coverage} no calza con los datos"
    assert coverage["to"] == "2023-2024", "la capa GEPRIF termina en 2023-2024; si cambió, actualiza el rango y la nota"
    assert f"temporadas {coverage['from']} a {coverage['to']}" in data["note"], "la nota debe repetir la cobertura real"


def test_coverage_of_usa_el_rango_real():
    items = [
        {"season": "2010-2011"},
        {"season": "2002-2003"},
        {"season": "2023-2024"},
    ]
    assert nom.coverage_of(items) == {"from": "2002-2003", "to": "2023-2024"}
    with pytest.raises(ValueError, match="sin temporadas"):
        nom.coverage_of([])


def test_toda_comuna_existe_en_el_indice():
    """Cada `comuna` publicada, plegada como en backend/geo.py, está en el índice territorial
    (BCN): si no, la búsqueda por comuna de la vista Historia no encuentra esos incendios."""
    items = _load()["items"]
    index_names = {_fold(c["name"]) for c in json.loads(COMUNAS_INDEX.read_text(encoding="utf-8"))}
    missing = sorted({_fold(i["comuna"]) for i in items if _fold(i["comuna"]) not in index_names})
    assert missing == [], f"{len(items)} ítems, comunas fuera del índice: {missing}"
    assert not [i for i in items if i["comuna"] == "Llay-Llay"], "quedaron filas con «Llay-Llay»"


def test_normalize():
    item = nom.normalize(_feat())
    assert item == {"name": "EL SAUCE", "comuna": "Coquimbo", "season": "2002-2003", "ha": 65.5, "lat": -30.103889, "lon": -71.288333}

    # Lo incompleto o fuera de rango se omite; nunca se publica un dato inventado.
    assert nom.normalize(_feat(nombre="  ")) is None
    assert nom.normalize(_feat(comuna=None)) is None
    assert nom.normalize(_feat(temporada="2002")) is None
    assert nom.normalize(_feat(temporada="1999-2000")) is None
    assert nom.normalize(_feat(temporada="2024-2025")) is None
    assert nom.normalize(_feat(superficie=None)) is None
    assert nom.normalize(_feat(x=None)) is None
    sin_geom = _feat()
    del sin_geom["geometry"]
    assert nom.normalize(sin_geom) is None


def test_dedupe_keeps_largest():
    items = [
        {"name": "CHOQUE", "comuna": "Tirúa", "season": "2014-2015", "ha": 139.2, "lat": -38.3, "lon": -73.4},
        {"name": "Choque", "comuna": "TIRÚA", "season": "2014-2015", "ha": 2826.0, "lat": -38.2, "lon": -73.3},
        {"name": "OTRO", "comuna": "Tirúa", "season": "2014-2015", "ha": 60.0, "lat": -38.3, "lon": -73.4},
    ]
    out = nom.dedupe(items)
    assert len(out) == 2
    assert out[0]["name"] == "Choque" and out[0]["ha"] == 2826.0

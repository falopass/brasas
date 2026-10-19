"""Guarda de forma de los datos versionados del frontend (web/data).

Valida lo mínimo que los consumidores asumen: web/js/views/casos.js (cases.json),
web/js/map.js y views/mapa.js (comunas-index.json) y backend/incidents.py
(persistent_hotspots.json). Solo stdlib; los datos no se editan aquí.
"""

import json
from datetime import datetime
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "web" / "data"

# Encuadre amplio de Chile (incluye islas oceánicas) usado por el mapa.
LON_MIN, LON_MAX = -110, -66
LAT_MIN, LAT_MAX = -56, -17


def _load(name):
    with open(DATA / name, encoding="utf-8") as f:
        return json.load(f)


def _parse_ts(value, context):
    assert isinstance(value, str) and value, f"{context}: timestamp vacío"
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _check_bbox(bbox, context):
    assert isinstance(bbox, list) and len(bbox) == 4, f"{context}: bbox no tiene 4 números"
    west, south, east, north = bbox
    assert all(isinstance(v, (int, float)) for v in bbox), f"{context}: bbox con no numéricos"
    assert west < east, f"{context}: bbox oeste >= este ({bbox})"
    assert south < north, f"{context}: bbox sur >= norte ({bbox})"


def test_cases_json():
    data = _load("cases.json")
    assert isinstance(data, dict), "cases.json debe ser un objeto"
    cases = data["cases"]
    assert isinstance(cases, list) and cases, "cases debe ser lista no vacía"

    seen = set()
    for case in cases:
        cid = case["id"]
        assert cid and isinstance(cid, str), "caso sin id"
        assert cid not in seen, f"id duplicado: {cid}"
        seen.add(cid)

        start = _parse_ts(case["start_utc"], f"caso {cid}")
        end = _parse_ts(case["end_utc"], f"caso {cid}")
        assert start < end, f"caso {cid}: start_utc >= end_utc"

        _check_bbox(case["bbox"], f"caso {cid}")

        for figure in case.get("figures", []):
            for rev in figure.get("revisions", []):
                assert rev.get("source"), f"caso {cid}: revisión sin source"
                url = rev.get("url", "")
                assert url.startswith("https://"), f"caso {cid}: url insegura {url!r}"


def test_comunas_index_json():
    comunas = _load("comunas-index.json")
    assert isinstance(comunas, list), "comunas-index.json debe ser lista"
    assert len(comunas) >= 300, f"solo {len(comunas)} comunas"

    seen = set()
    for c in comunas:
        code = c["code"]
        assert isinstance(code, int), f"comuna {c}: code no entero"
        assert code not in seen, f"code duplicado: {code}"
        seen.add(code)

        name = c["name"]
        region = c["region"]
        assert name and isinstance(name, str), f"comuna {code}: name vacío"
        assert region and isinstance(region, str), f"comuna {code}: region vacía"

        lon, lat = c["center"]
        assert len(c["center"]) == 2, f"comuna {code}: center no es par"
        assert LON_MIN <= lon <= LON_MAX, f"comuna {code}: lon {lon} fuera de Chile"
        assert LAT_MIN <= lat <= LAT_MAX, f"comuna {code}: lat {lat} fuera de Chile"

        _check_bbox(c["bbox"], f"comuna {code}")
        west, south, east, north = c["bbox"]
        assert LON_MIN <= west <= LON_MAX and LON_MIN <= east <= LON_MAX, (
            f"comuna {code}: bbox lon fuera de Chile"
        )
        assert LAT_MIN <= south <= LAT_MAX and LAT_MIN <= north <= LAT_MAX, (
            f"comuna {code}: bbox lat fuera de Chile"
        )


def test_persistent_hotspots_json():
    data = _load("persistent_hotspots.json")
    sources = data["sources"]
    assert isinstance(sources, list) and sources, "sources debe ser lista no vacía"

    for s in sources:
        name = s["name"]
        assert name, "fuente sin name"
        assert s["kind"], f"{name}: kind vacío"
        assert s["source"], f"{name}: source vacío"
        assert s["radius_km"] > 0, f"{name}: radius_km <= 0"
        lat, lon = s["lat"], s["lon"]
        assert isinstance(lat, (int, float)) and isinstance(lon, (int, float)), (
            f"{name}: lat/lon no numéricos"
        )
        assert LON_MIN <= lon <= LON_MAX, f"{name}: lon {lon} fuera de Chile"
        assert LAT_MIN <= lat <= LAT_MAX, f"{name}: lat {lat} fuera de Chile"

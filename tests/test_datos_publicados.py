"""Contrato de los JSON versionados en web/data que consumen las vistas.

Cada validador es una función pura: recibe el JSON ya cargado y lanza
ValueError con un mensaje claro si la forma no es la que las vistas y el
backend asumen. Las pruebas parametrizadas los corren sobre los datos
reales, y cada validador tiene una prueba con payload roto para demostrar
que la guarda sirve.

Distinto de tests/test_data_files.py: aquí el contrato es explícito
(ValueError, no assert) y cubre también rain_normals y prioritarias.
"""

import json
import re
from datetime import datetime
from pathlib import Path

import pytest

DATA = Path(__file__).resolve().parent.parent / "web" / "data"

# Encuadre de Chile incluyendo islas oceánicas.
LON_MIN, LON_MAX = -110, -66
LAT_MIN, LAT_MAX = -56, -17

# Las cifras históricas también llevan fechas parciales ("2023", "2017-02")
# o marcas editoriales ("s. f.", "posterior"): se exige string no vacío y,
# cuando tiene forma ISO parcial, que sus componentes sean válidos.
_DATE_RE = re.compile(r"^\d{4}(-\d{2})?(-\d{2})?$")


def _load(name):
    with open(DATA / name, encoding="utf-8") as f:
        return json.load(f)


def _fail(context, msg):
    raise ValueError(f"{context}: {msg}")


def _parse_iso_utc(value, context):
    if not isinstance(value, str) or not value:
        _fail(context, f"timestamp vacío o no string: {value!r}")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        _fail(context, f"timestamp no ISO: {value!r}")
    if dt.tzinfo is None:
        _fail(context, f"timestamp sin zona UTC: {value!r}")
    return dt


def _check_bbox(bbox, context):
    if not isinstance(bbox, list) or len(bbox) != 4:
        _fail(context, f"bbox debe ser lista de 4 números: {bbox!r}")
    if any(not isinstance(v, (int, float)) or isinstance(v, bool) for v in bbox):
        _fail(context, f"bbox con valores no numéricos: {bbox!r}")
    west, south, east, north = bbox
    if east <= west:
        _fail(context, f"bbox este <= oeste: {bbox!r}")
    if north <= south:
        _fail(context, f"bbox norte <= sur: {bbox!r}")


def _check_date(value, context):
    if not isinstance(value, str) or not value.strip():
        _fail(context, f"fecha vacía: {value!r}")
    if _DATE_RE.match(value):
        parts = value.split("-")
        if len(parts) >= 2 and not (1 <= int(parts[1]) <= 12):
            _fail(context, f"mes inválido en fecha: {value!r}")
        if len(parts) == 3:
            try:
                datetime.strptime(value, "%Y-%m-%d")
            except ValueError:
                _fail(context, f"fecha inválida: {value!r}")


def _check_url(value, context):
    if not isinstance(value, str) or not (
        value.startswith("https://") or value.startswith("http://")
    ):
        _fail(context, f"url no http/https: {value!r}")


def _check_in_chile(lat, lon, context):
    if not (LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX):
        _fail(context, f"punto fuera de Chile: lat={lat!r} lon={lon!r}")


def validate_cases(data):
    """cases.json: catálogo de casos históricos (vista Historia)."""
    if not isinstance(data, dict):
        _fail("cases.json", "debe ser un objeto")
    cases = data.get("cases")
    if not isinstance(cases, list) or not cases:
        _fail("cases.json", "'cases' debe ser lista no vacía")

    seen = set()
    for case in cases:
        cid = case.get("id")
        if not cid or not isinstance(cid, str):
            _fail("cases.json", f"caso sin id: {case!r:.80}")
        if cid in seen:
            _fail("cases.json", f"id duplicado: {cid}")
        seen.add(cid)
        ctx = f"caso {cid}"

        if not case.get("title"):
            _fail(ctx, "sin title")
        start = _parse_iso_utc(case.get("start_utc"), ctx)
        end = _parse_iso_utc(case.get("end_utc"), ctx)
        if start >= end:
            _fail(ctx, "start_utc >= end_utc")
        _check_bbox(case.get("bbox"), ctx)

        for figure in case.get("figures", []):
            # Las cifras publicadas viven en las revisiones de cada figure.
            revisions = figure.get("revisions", [figure])
            for rev in revisions:
                rctx = f"{ctx} cifra {figure.get('key', '?')}"
                if "value" not in rev:
                    _fail(rctx, "revisión sin value")
                if not rev.get("source"):
                    _fail(rctx, "revisión sin source")
                _check_url(rev.get("url"), rctx)
                _check_date(rev.get("date"), rctx)
    return data


def validate_comunas_index(data, geojson=None):
    """comunas-index.json: índice del buscador; debe calcar comunas.geojson."""
    if not isinstance(data, list) or not data:
        _fail("comunas-index.json", "debe ser lista no vacía")

    seen = set()
    for comuna in data:
        code = comuna.get("code")
        ctx = f"comuna {code!r}"
        if not isinstance(code, int) or isinstance(code, bool):
            _fail(ctx, "code no entero")
        if code in seen:
            _fail(ctx, "code duplicado")
        seen.add(code)
        if not comuna.get("name"):
            _fail(ctx, "name vacío")

        center = comuna.get("center")
        if not isinstance(center, list) or len(center) != 2:
            _fail(ctx, f"center debe ser [lon, lat]: {center!r}")
        lon, lat = center
        _check_in_chile(lat, lon, ctx)
        _check_bbox(comuna.get("bbox"), ctx)

    if geojson is not None:
        geo_codes = {f["properties"]["code"] for f in geojson.get("features", [])}
        if seen != geo_codes:
            _fail(
                "comunas-index.json",
                f"códigos no coinciden con comunas.geojson "
                f"(solo índice: {sorted(seen - geo_codes)}, "
                f"solo geojson: {sorted(geo_codes - seen)})",
            )
    return data


def validate_rain_normals(data, comunas_index=None):
    """rain_normals.json: 365 normales diarias por celda comunal."""
    cells = data.get("cells") if isinstance(data, dict) else None
    if not isinstance(cells, dict) or not cells:
        _fail("rain_normals.json", "'cells' debe ser objeto no vacío")

    for key, values in cells.items():
        ctx = f"celda {key!r}"
        if not str(key).isdigit():
            _fail(ctx, "clave no numérica")
        if not isinstance(values, list) or len(values) != 365:
            _fail(ctx, f"debe tener 365 valores, tiene {len(values)}")
        for i, v in enumerate(values):
            if not isinstance(v, (int, float)) or isinstance(v, bool):
                _fail(ctx, f"valor {i} no numérico: {v!r}")

    if comunas_index is not None:
        codes = {c["code"] for c in comunas_index}
        unknown = [k for k in cells if int(k) not in codes]
        if unknown:
            _fail(
                "rain_normals.json",
                f"celdas sin comuna en comunas-index: {sorted(unknown)}",
            )
    return data


def validate_persistent_hotspots(data):
    """persistent_hotspots.json: fuentes fijas que silencian avisos."""
    sources = data.get("sources") if isinstance(data, dict) else None
    if not isinstance(sources, list) or not sources:
        _fail("persistent_hotspots.json", "'sources' debe ser lista no vacía")
    for point in sources:
        ctx = f"punto {point.get('name', '?')!r}"
        lat, lon = point.get("lat"), point.get("lon")
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            _fail(ctx, f"lat/lon no numéricos: {lat!r}, {lon!r}")
        _check_in_chile(lat, lon, ctx)
        if not point.get("source"):
            _fail(ctx, "sin source")
    return data


def validate_prioritarias(data):
    """prioritarias.json: lista de comunas prioritarias servida por API."""
    if isinstance(data, dict):
        items = data.get("comunas") or data.get("items") or []
    else:
        items = data
    if not isinstance(items, list):
        _fail("prioritarias.json", "la lista de comunas no es lista")
    for item in items:
        if not (item.get("code") or item.get("name")):
            _fail("prioritarias.json", f"elemento sin code ni name: {item!r}")
    return data


def _validate_rain_with_index(data):
    return validate_rain_normals(data, _load("comunas-index.json"))


def _validate_index_with_geojson(data):
    return validate_comunas_index(data, _load("comunas.geojson"))


@pytest.mark.parametrize(
    "filename,validator",
    [
        ("cases.json", validate_cases),
        ("comunas-index.json", _validate_index_with_geojson),
        ("rain_normals.json", _validate_rain_with_index),
        ("persistent_hotspots.json", validate_persistent_hotspots),
        ("prioritarias.json", validate_prioritarias),
    ],
    ids=lambda p: p if isinstance(p, str) else None,
)
def test_datos_publicados(filename, validator):
    validator(_load(filename))


# --- Payloads rotos: cada guarda debe lanzar ValueError ---


def _case_ok():
    return {
        "cases": [
            {
                "id": "caso-1",
                "title": "Caso",
                "start_utc": "2026-01-01T00:00:00Z",
                "end_utc": "2026-01-02T00:00:00Z",
                "bbox": [-73.0, -37.0, -72.0, -36.0],
                "figures": [
                    {
                        "key": "deaths",
                        "revisions": [
                            {
                                "value": "1",
                                "source": "CONAF",
                                "url": "https://example.cl",
                                "date": "2026-01-02",
                            }
                        ],
                    }
                ],
            }
        ]
    }


def test_cases_rechaza_cifra_sin_source():
    broken = _case_ok()
    del broken["cases"][0]["figures"][0]["revisions"][0]["source"]
    with pytest.raises(ValueError, match="source"):
        validate_cases(broken)


def test_cases_rechaza_id_duplicado():
    broken = _case_ok()
    broken["cases"].append(dict(broken["cases"][0]))
    with pytest.raises(ValueError, match="duplicado"):
        validate_cases(broken)


def test_cases_rechaza_bbox_invertido():
    broken = _case_ok()
    broken["cases"][0]["bbox"] = [-72.0, -37.0, -73.0, -36.0]
    with pytest.raises(ValueError, match="este <= oeste"):
        validate_cases(broken)


def test_comunas_index_rechaza_code_duplicado():
    ok = [
        {"code": 1101, "name": "A", "center": [-70.0, -20.0], "bbox": [-71, -21, -69, -19]},
        {"code": 1102, "name": "B", "center": [-70.0, -30.0], "bbox": [-71, -31, -69, -29]},
    ]
    validate_comunas_index(ok)
    broken = [dict(ok[0]), dict(ok[0])]
    with pytest.raises(ValueError, match="duplicado"):
        validate_comunas_index(broken)


def test_comunas_index_rechaza_center_fuera_de_chile():
    broken = [
        {"code": 1, "name": "X", "center": [-70.0, 10.0], "bbox": [-71, 9, -69, 11]}
    ]
    with pytest.raises(ValueError, match="fuera de Chile"):
        validate_comunas_index(broken)


def test_comunas_index_rechaza_codigos_que_no_calzan_geojson():
    index = [
        {"code": 1, "name": "X", "center": [-70.0, -30.0], "bbox": [-71, -31, -69, -29]}
    ]
    geojson = {"features": [{"properties": {"code": 2}}]}
    with pytest.raises(ValueError, match="no coinciden"):
        validate_comunas_index(index, geojson)


def test_rain_normals_rechaza_celda_corta():
    with pytest.raises(ValueError, match="365"):
        validate_rain_normals({"cells": {"1101": [0.0] * 364}})


def test_rain_normals_rechaza_booleano():
    with pytest.raises(ValueError, match="no numérico"):
        validate_rain_normals({"cells": {"1101": [True] * 365}})


def test_rain_normals_rechaza_codigo_desconocido():
    index = [{"code": 1101}]
    with pytest.raises(ValueError, match="sin comuna"):
        validate_rain_normals({"cells": {"9999": [0.0] * 365}}, index)


def test_persistent_hotspots_rechaza_punto_sin_source():
    broken = {"sources": [{"name": "X", "lat": -33.0, "lon": -70.0}]}
    with pytest.raises(ValueError, match="sin source"):
        validate_persistent_hotspots(broken)


def test_persistent_hotspots_rechaza_punto_fuera_de_chile():
    broken = {
        "sources": [{"name": "X", "lat": 10.0, "lon": -70.0, "source": "ref"}]
    }
    with pytest.raises(ValueError, match="fuera de Chile"):
        validate_persistent_hotspots(broken)


def test_prioritarias_rechaza_elemento_sin_identidad():
    with pytest.raises(ValueError, match="code ni name"):
        validate_prioritarias({"comunas": [{"foo": 1}]})


def test_prioritarias_acepta_lista_vacia():
    validate_prioritarias({"comunas": []})
    validate_prioritarias([])

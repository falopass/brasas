"""Contrato de los JSON versionados en web/data que consumen las vistas.

Cada validador es una función pura: recibe el JSON ya cargado y lanza
ValueError con un mensaje claro si la forma no es la que las vistas y el
backend asumen. Las pruebas parametrizadas los corren sobre los datos
reales, y cada validador tiene una prueba con payload roto para demostrar
que la guarda sirve.

Distinto de tests/test_data_files.py: aquí el contrato es explícito
(ValueError, no assert) y cubre también rain_normals, prioritarias,
censo_2024, interfaz y temporada-2526.
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
_GVP_RE = re.compile(r"^Smithsonian GVP \d{6}\b")
_INDUSTRY_FIELDS = ("source_url", "coordinate_source", "fetched_at", "last_verified", "valid_from", "valid_to")


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
    if not isinstance(value, str) or not (value.startswith("https://") or value.startswith("http://")):
        _fail(context, f"url no http/https: {value!r}")


def _check_in_chile(lat, lon, context):
    if not (LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX):
        _fail(context, f"punto fuera de Chile: lat={lat!r} lon={lon!r}")


def _check_meta(data, filename):
    """Cabecera común de los JSON oficiales: objeto con source, license y fetched_at."""
    if not isinstance(data, dict):
        _fail(filename, "debe ser un objeto")
    for field in ("source", "license"):
        if not isinstance(data.get(field), str) or not data[field].strip():
            _fail(filename, f"'{field}' vacío o no string")
    _parse_iso_utc(data.get("fetched_at"), filename)


def _check_code(value, context):
    """CUT de comuna sin el cero inicial: entero de 4 o 5 dígitos (1101 a 16305)."""
    if not isinstance(value, int) or isinstance(value, bool):
        _fail(context, f"code no entero: {value!r}")
    if not 1000 <= value <= 99999:
        _fail(context, f"code fuera del rango CUT: {value!r}")


def _check_nonneg(value, context, field):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        _fail(context, f"'{field}' no numérico: {value!r}")
    if value < 0:
        _fail(context, f"'{field}' negativo: {value!r}")


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
        source = point.get("source")
        if not isinstance(source, str) or not source:
            _fail(ctx, "sin source")
        if not (_GVP_RE.match(source) or "https://" in source):
            _fail(ctx, f"source sin ficha GVP ni URL https: {source!r}")
        if point.get("kind") != "volcan":
            for field in _INDUSTRY_FIELDS:
                if field not in point:
                    _fail(ctx, f"fuente no volcánica sin {field}")
            for field in ("source_url", "coordinate_source"):
                _check_url(point[field], ctx)
            for field in ("fetched_at", "last_verified"):
                _check_date(point[field], ctx)
            if point["valid_to"] is not None:
                _check_date(point["valid_to"], ctx)
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


def validate_censo_2024(data):
    """censo_2024.json: población, viviendas y hogares del INE por comuna."""
    _check_meta(data, "censo_2024.json")
    comunas = data.get("comunas")
    if not isinstance(comunas, list) or len(comunas) < 300:
        _fail("censo_2024.json", f"'comunas' debe ser lista de 300+: {comunas!r:.80}")

    seen = set()
    for comuna in comunas:
        code = comuna.get("code")
        ctx = f"censo_2024.json comuna {code!r}"
        _check_code(code, ctx)
        if code in seen:
            _fail(ctx, "code duplicado")
        seen.add(code)
        if not comuna.get("name"):
            _fail(ctx, "name vacío")
        for field in ("poblacion", "viviendas", "hogares"):
            _check_nonneg(comuna.get(field), ctx, field)
    return data


def validate_interfaz(data, comunas_index=None):
    """interfaz.json: hectáreas y porcentaje en zona urbano-forestal por comuna."""
    _check_meta(data, "interfaz.json")
    comunas = data.get("comunas")
    if not isinstance(comunas, dict) or len(comunas) < 300:
        _fail("interfaz.json", f"'comunas' debe ser objeto de 300+: {comunas!r:.80}")

    for key, zona in comunas.items():
        ctx = f"interfaz.json comuna {key!r}"
        if not isinstance(key, str) or not key.isdigit():
            _fail(ctx, "clave no numérica")
        _check_nonneg(zona.get("ha_interfaz"), ctx, "ha_interfaz")
        pct = zona.get("pct_comuna")
        if not isinstance(pct, (int, float)) or isinstance(pct, bool):
            _fail(ctx, f"'pct_comuna' no numérico: {pct!r}")
        if not 0 <= pct <= 100:
            _fail(ctx, f"'pct_comuna' fuera de [0, 100]: {pct!r}")

    if comunas_index is not None:
        codes = {c["code"] for c in comunas_index}
        unknown = [k for k in comunas if int(k) not in codes]
        if unknown:
            _fail(
                "interfaz.json",
                f"claves sin comuna en comunas-index: {sorted(unknown)}",
            )
    return data


def validate_temporada_2526(data):
    """temporada-2526.json: incendios y hectáreas de CONAF por comuna y región."""
    _check_meta(data, "temporada-2526.json")
    temporada = data.get("temporada")
    if not isinstance(temporada, str) or not re.fullmatch(r"\d{4}-\d{4}", temporada):
        _fail("temporada-2526.json", f"'temporada' sin forma AAAA-AAAA: {temporada!r}")
    # Son las comunas con incendios de la temporada, no el país completo:
    # basta con que ambas listas existan y no vengan vacías.
    if not isinstance(data.get("regiones"), list) or not data["regiones"]:
        _fail("temporada-2526.json", "'regiones' debe ser lista no vacía")
    comunas = data.get("comunas")
    if not isinstance(comunas, list) or not comunas:
        _fail("temporada-2526.json", "'comunas' debe ser lista no vacía")

    seen = set()
    for comuna in comunas:
        code = comuna.get("code")
        ctx = f"temporada-2526.json comuna {code!r}"
        _check_code(code, ctx)
        if code in seen:
            _fail(ctx, "code duplicado")
        seen.add(code)
        if not comuna.get("name"):
            _fail(ctx, "name vacío")
        for field in ("incendios", "hectareas", "max_ha"):
            _check_nonneg(comuna.get(field), ctx, field)
    return data


def _validate_rain_with_index(data):
    return validate_rain_normals(data, _load("comunas-index.json"))


def _validate_index_with_geojson(data):
    return validate_comunas_index(data, _load("comunas.geojson"))


def _validate_interfaz_with_index(data):
    return validate_interfaz(data, _load("comunas-index.json"))


@pytest.mark.parametrize(
    "filename,validator",
    [
        ("cases.json", validate_cases),
        ("censo_2024.json", validate_censo_2024),
        ("comunas-index.json", _validate_index_with_geojson),
        ("interfaz.json", _validate_interfaz_with_index),
        ("rain_normals.json", _validate_rain_with_index),
        ("persistent_hotspots.json", validate_persistent_hotspots),
        ("prioritarias.json", validate_prioritarias),
        ("temporada-2526.json", validate_temporada_2526),
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
    broken = [{"code": 1, "name": "X", "center": [-70.0, 10.0], "bbox": [-71, 9, -69, 11]}]
    with pytest.raises(ValueError, match="fuera de Chile"):
        validate_comunas_index(broken)


def test_comunas_index_rechaza_codigos_que_no_calzan_geojson():
    index = [{"code": 1, "name": "X", "center": [-70.0, -30.0], "bbox": [-71, -31, -69, -29]}]
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
    broken = {"sources": [{"name": "X", "lat": 10.0, "lon": -70.0, "source": "ref"}]}
    with pytest.raises(ValueError, match="fuera de Chile"):
        validate_persistent_hotspots(broken)


def test_persistent_hotspots_rechaza_source_sin_url_ni_gvp():
    broken = {"sources": [{"name": "X", "kind": "volcan", "lat": -33.0, "lon": -70.0, "source": "internet"}]}
    with pytest.raises(ValueError, match="sin ficha GVP ni URL"):
        validate_persistent_hotspots(broken)


def _industry_ok():
    return {
        "sources": [
            {
                "name": "Planta de prueba",
                "kind": "industria",
                "lat": -33.0,
                "lon": -70.0,
                "radius_km": 3,
                "source": "https://example.cl/planta",
                "source_url": "https://example.cl/planta",
                "coordinate_source": "https://example.cl/rca",
                "fetched_at": "2026-10-21",
                "last_verified": "2026-10-21",
                "valid_from": "2020-01-01",
                "valid_to": None,
            }
        ]
    }


def test_persistent_hotspots_acepta_industria_con_fuente_completa():
    validate_persistent_hotspots(_industry_ok())


def test_persistent_hotspots_rechaza_industria_sin_coordenada_oficial():
    broken = _industry_ok()
    del broken["sources"][0]["coordinate_source"]
    with pytest.raises(ValueError, match="coordinate_source"):
        validate_persistent_hotspots(broken)


def test_persistent_hotspots_rechaza_industria_sin_ventana_de_validez():
    broken = _industry_ok()
    del broken["sources"][0]["valid_from"]
    with pytest.raises(ValueError, match="valid_from"):
        validate_persistent_hotspots(broken)


def test_prioritarias_rechaza_elemento_sin_identidad():
    with pytest.raises(ValueError, match="code ni name"):
        validate_prioritarias({"comunas": [{"foo": 1}]})


def test_prioritarias_acepta_lista_vacia():
    validate_prioritarias({"comunas": []})
    validate_prioritarias([])


def _censo_ok():
    return {
        "source": "https://example.cl/censo",
        "license": "CC BY-SA 4.0",
        "fetched_at": "2026-10-19T13:09:49+00:00",
        "comunas": [
            {
                "code": 1000 + i,
                "name": f"Comuna {i}",
                "poblacion": 1,
                "viviendas": 1,
                "hogares": 1,
            }
            for i in range(300)
        ],
    }


def _interfaz_ok():
    return {
        "source": "https://example.cl/interfaz",
        "license": "CONAF",
        "fetched_at": "2026-10-20T05:50:56+00:00",
        "comunas": {str(1000 + i): {"ha_interfaz": 1.5, "pct_comuna": 0.5} for i in range(300)},
    }


def _temporada_ok():
    return {
        "source": "https://example.cl/temporada.csv",
        "license": "CONAF",
        "fetched_at": "2026-10-19T22:34:11+00:00",
        "temporada": "2025-2026",
        "regiones": [{"name": "Maule", "incendios": 1, "hectareas": 1.0, "mes_peak": "2026-01", "comuna_top": "Molina"}],
        "comunas": [
            {
                "code": 1000 + i,
                "name": f"Comuna {i}",
                "region": "Maule",
                "incendios": 1,
                "hectareas": 1.0,
                "mes_peak": "2026-01",
                "max_ha": 1.0,
            }
            for i in range(10)
        ],
    }


def test_censo_rechaza_source_vacio():
    broken = _censo_ok()
    broken["source"] = ""
    with pytest.raises(ValueError, match="'source'"):
        validate_censo_2024(broken)


def test_censo_rechaza_fetched_at_no_iso():
    broken = _censo_ok()
    broken["fetched_at"] = "ayer"
    with pytest.raises(ValueError, match="timestamp no ISO"):
        validate_censo_2024(broken)


def test_censo_rechaza_pocas_comunas():
    broken = _censo_ok()
    broken["comunas"] = broken["comunas"][:10]
    with pytest.raises(ValueError, match="300"):
        validate_censo_2024(broken)


def test_censo_rechaza_code_duplicado():
    broken = _censo_ok()
    broken["comunas"][1]["code"] = broken["comunas"][0]["code"]
    with pytest.raises(ValueError, match="duplicado"):
        validate_censo_2024(broken)


def test_censo_rechaza_code_no_entero():
    broken = _censo_ok()
    broken["comunas"][0]["code"] = "01101"
    with pytest.raises(ValueError, match="code no entero"):
        validate_censo_2024(broken)


def test_censo_rechaza_poblacion_negativa():
    broken = _censo_ok()
    broken["comunas"][0]["poblacion"] = -5
    with pytest.raises(ValueError, match="'poblacion' negativo"):
        validate_censo_2024(broken)


def test_censo_rechaza_viviendas_booleanas():
    broken = _censo_ok()
    broken["comunas"][0]["viviendas"] = True
    with pytest.raises(ValueError, match="'viviendas' no numérico"):
        validate_censo_2024(broken)


def test_interfaz_rechaza_pct_fuera_de_rango():
    broken = _interfaz_ok()
    broken["comunas"]["1000"]["pct_comuna"] = 120.0
    with pytest.raises(ValueError, match=r"\[0, 100\]"):
        validate_interfaz(broken)


def test_interfaz_rechaza_ha_negativa():
    broken = _interfaz_ok()
    broken["comunas"]["1000"]["ha_interfaz"] = -0.1
    with pytest.raises(ValueError, match="'ha_interfaz' negativo"):
        validate_interfaz(broken)


def test_interfaz_rechaza_clave_sin_comuna_en_index():
    data = _interfaz_ok()
    index = [{"code": 1000 + i} for i in range(1, 300)]
    with pytest.raises(ValueError, match="sin comuna en comunas-index"):
        validate_interfaz(data, index)


def test_temporada_rechaza_etiqueta_sin_forma():
    broken = _temporada_ok()
    broken["temporada"] = "2025/26"
    with pytest.raises(ValueError, match="AAAA-AAAA"):
        validate_temporada_2526(broken)


def test_temporada_rechaza_sin_regiones():
    broken = _temporada_ok()
    del broken["regiones"]
    with pytest.raises(ValueError, match="'regiones'"):
        validate_temporada_2526(broken)


def test_temporada_rechaza_cifra_booleana():
    broken = _temporada_ok()
    broken["comunas"][0]["incendios"] = True
    with pytest.raises(ValueError, match="'incendios' no numérico"):
        validate_temporada_2526(broken)

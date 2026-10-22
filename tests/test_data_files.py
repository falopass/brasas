"""Guarda de forma de los datos versionados del frontend (web/data).

Valida lo mínimo que los consumidores asumen: comunas-index.json y los GeoJSON
del mapa, el peso que precachea el service worker y la forma de temporada-2526.
El resto de los JSON tiene su propia guarda: cases.json en test_cases_figuras.py
y test_casos_catalogo.py; persistent_hotspots.json en test_volcanes_fuentes.py;
censo_2024.json en test_censo.py; interfaz.json en test_interfaz.py y
rain_normals.json en test_rain.py.
"""

import json
import re
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "web" / "data"

# Encuadre amplio de Chile (incluye islas oceánicas) usado por el mapa.
LON_MIN, LON_MAX = -110, -66
LAT_MIN, LAT_MAX = -56, -17


def _load(name):
    with open(DATA / name, encoding="utf-8") as f:
        return json.load(f)


def _check_bbox(bbox, context):
    assert isinstance(bbox, list) and len(bbox) == 4, f"{context}: bbox no tiene 4 números"
    west, south, east, north = bbox
    assert all(isinstance(v, (int, float)) for v in bbox), f"{context}: bbox con no numéricos"
    assert west < east, f"{context}: bbox oeste >= este ({bbox})"
    assert south < north, f"{context}: bbox sur >= norte ({bbox})"


def _check_rings(coordinates, context):
    for ring in coordinates:
        assert len(ring) >= 4, f"{context}: anillo con < 4 posiciones"
        assert ring[0] == ring[-1], f"{context}: anillo sin cerrar"


def _check_geometry(geometry, context):
    gtype = geometry["type"]
    coords = geometry["coordinates"]
    if gtype == "Polygon":
        _check_rings(coords, context)
    elif gtype == "MultiPolygon":
        for polygon in coords:
            _check_rings(polygon, context)
    else:
        raise AssertionError(f"{context}: tipo de geometría inesperado {gtype}")


def test_comunas_index_json():
    comunas = _load("comunas-index.json")
    geojson = _load("comunas.geojson")
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
        assert LON_MIN <= west <= LON_MAX and LON_MIN <= east <= LON_MAX, f"comuna {code}: bbox lon fuera de Chile"
        assert LAT_MIN <= south <= LAT_MAX and LAT_MIN <= north <= LAT_MAX, f"comuna {code}: bbox lat fuera de Chile"

    geo_codes = {f["properties"]["code"] for f in geojson["features"]}
    assert seen == geo_codes, "comunas-index.json debe calcar los códigos de comunas.geojson"


def test_geojson_publicado():
    # Los conteos (16 regiones, 345 comunas) salen de scripts/build_territory.py,
    # que genera estos archivos desde caracena/chile-geojson; si cambian,
    # regenera con ese script y actualiza el contrato.
    regiones = _load("regiones.geojson")
    assert regiones["type"] == "FeatureCollection", "regiones.geojson no es FeatureCollection"
    features = regiones["features"]
    assert len(features) == 16, f"regiones.geojson tiene {len(features)} features, esperadas 16"

    region_codes = set()
    for f in features:
        props = f["properties"]
        code = props["code"]
        assert isinstance(code, int), f"región {props}: code no entero"
        assert code not in region_codes, f"code de región duplicado: {code}"
        region_codes.add(code)
        assert props.get("name"), f"región {code}: name vacío"
        _check_geometry(f["geometry"], f"región {code}")

    comunas = _load("comunas.geojson")
    assert comunas["type"] == "FeatureCollection", "comunas.geojson no es FeatureCollection"
    features = comunas["features"]
    assert len(features) == 345, f"comunas.geojson tiene {len(features)} features, esperadas 345"

    seen = set()
    for f in features:
        props = f["properties"]
        code = props["code"]
        assert isinstance(code, int), f"comuna {props}: code no entero"
        assert code not in seen, f"code de comuna duplicado: {code}"
        seen.add(code)

        assert props.get("name"), f"comuna {code}: name vacío"
        assert props.get("region"), f"comuna {code}: region vacía"
        assert props.get("region_code") in region_codes, (
            f"comuna {code}: region_code {props.get('region_code')} no existe en regiones.geojson"
        )

        _check_bbox(props["bbox"], f"comuna {code}")
        west, south, east, north = props["bbox"]
        assert LON_MIN <= west <= LON_MAX and LON_MIN <= east <= LON_MAX, f"comuna {code}: bbox lon fuera de Chile"
        assert LAT_MIN <= south <= LAT_MAX and LAT_MIN <= north <= LAT_MAX, f"comuna {code}: bbox lat fuera de Chile"

        center = props["center"]
        assert isinstance(center, list) and len(center) == 2, f"comuna {code}: center no es par"
        assert all(isinstance(v, (int, float)) for v in center), f"comuna {code}: center no numérico"

        _check_geometry(f["geometry"], f"comuna {code}")


def test_peso_web_data():
    # web/sw.js precachea estos archivos: si alguno crece, revisa el generador
    # (scripts/build_territory.py) o muévelo a carga diferida.
    archivos = [p for p in DATA.iterdir() if p.is_file()]
    assert archivos, "web/data está vacío"
    for p in archivos:
        size_mb = p.stat().st_size / 1024 / 1024
        assert size_mb <= 2.5, (
            f"{p.name} pesa {size_mb:.2f} MB (> 2,5 MB): si crece, revisa el generador "
            "o muévelo a carga diferida; el service worker lo precachea"
        )
    total_mb = sum(p.stat().st_size for p in archivos) / 1024 / 1024
    assert total_mb <= 4, (
        f"web/data pesa {total_mb:.2f} MB en total (> 4 MB): si crece, revisa el generador "
        "o muévelo a carga diferida; el service worker lo precachea"
    )


def test_temporada_json():
    data = _load("temporada-2526.json")
    assert data["source"].startswith("https://") and data["license"] and data["fetched_at"]
    assert re.fullmatch(r"\d{4}-\d{4}", data["temporada"]), f"temporada sin forma AAAA-AAAA: {data['temporada']!r}"
    assert data["regiones"], "temporada-2526.json sin regiones"

    codes = [c["code"] for c in data["comunas"]]
    assert len(codes) == len(set(codes)), "temporada-2526.json con códigos duplicados"
    for c in data["comunas"]:
        assert isinstance(c["code"], int) and c["name"], f"comuna inválida: {c!r}"
        for campo in ("incendios", "hectareas", "max_ha"):
            assert isinstance(c[campo], (int, float)) and not isinstance(c[campo], bool) and c[campo] >= 0, (
                f"comuna {c['code']}: {campo} inválido ({c[campo]!r})"
            )

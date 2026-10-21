"""Guarda de los perímetros oficiales versionados de la Historia (FUEGO-60).

La simplificación que hace el FeatureServer de CONAF-GEPRIF (`maxAllowableOffset`)
devuelve anillos que se cruzan entre sí (bowtie): GeoJSON no admite polígonos
auto-intersectados y el navegador los pinta con huecos, islas fantasma o los
descarta enteros. Medido el 2026-10-21 sobre `origin/main`: 92 de 111 features
inválidas (87 de 106 en Ñuble–Biobío–Araucanía 2023, 4 de 4 en Viña 2024,
1 de 1 en Las Máquinas 2017).

Esta guarda lee los `web/data/cases/<id>.perimeter.json` versionados (sin red) y
exige que cada `features[].geometry` sea un `Polygon`/`MultiPolygon` válido y no
vacío, que cada coordenada quede dentro del `bbox` de su caso en
`web/data/cases.json` con 0,2° de margen, y que `properties.ha` siga siendo el
dato oficial de CONAF (huella fijada abajo: no se recalcula).
"""

import json
from pathlib import Path

import pytest
from shapely.geometry import shape

DATA = Path(__file__).resolve().parent.parent / "web" / "data"

# Margen alrededor del bbox del caso: los polígonos emparejados por envolvente
# pueden sobresalir un poco (el empareje es espacial, no un recorte exacto).
MARGEN_BBOX = 0.2

# Huella de `properties.ha` por caso, en el orden de las features versionadas.
# Es el dato oficial de CONAF: la reparación de geometría no lo recalcula.
HA_ESPERADO = {
    "las-maquinas-2017": [192157.5],
    "nuble-biobio-araucania-2023": [
        59.9,
        6150.3,
        385.7,
        338.6,
        912.2,
        47.5,
        69.0,
        5227.2,
        4984.1,
        1312.6,
        69234.7,
        14690.4,
        4047.8,
        3452.4,
        3124.9,
        3025.1,
        2708.6,
        2631.2,
        1976.3,
        1294.3,
        974.1,
        254.5,
        253.7,
        246.1,
        224.9,
        164.2,
        88.8,
        56.9,
        26926.7,
        18153.7,
        12073.4,
        11757.8,
        6513.0,
        5769.7,
        3657.4,
        2865.6,
        2242.5,
        2150.8,
        2080.7,
        1994.5,
        1964.3,
        1670.8,
        1633.8,
        1381.5,
        1251.4,
        670.4,
        386.2,
        308.6,
        300.1,
        275.1,
        268.2,
        263.8,
        223.2,
        216.9,
        81.9,
        72.9,
        4802.3,
        4733.5,
        1308.8,
        1177.2,
        808.1,
        396.3,
        244.3,
        207.2,
        123.3,
        572.8,
        250.9,
        218.2,
        136.8,
        118.9,
        1115.0,
        982.3,
        302.1,
        297.2,
        127.3,
        1155.2,
        1074.4,
        963.2,
        379.1,
        168.9,
        964.6,
        162.2,
        97.0,
        83.3,
        265.0,
        228.0,
        129.4,
        502.9,
        1386.9,
        139.4,
        113.8,
        316.4,
        297.2,
        166.3,
        154.5,
        66.1,
        60.5,
        3819.7,
        1591.9,
        1212.4,
        459.4,
        349.1,
        729.6,
        219.9,
        59.3,
        91.5,
    ],
    "vina-del-mar-2024": [8806.9, 1474.1, 146.6, 56.1],
}

CASOS = {c["id"]: c for c in json.loads((DATA / "cases.json").read_text(encoding="utf-8"))["cases"]}
ARCHIVOS = {p.stem.replace(".perimeter", ""): p for p in (DATA / "cases").glob("*.perimeter.json")}


def _puntos(geom):
    """Itera [lon, lat] de un Polygon o MultiPolygon GeoJSON."""
    assert geom["type"] in ("Polygon", "MultiPolygon"), f"tipo inesperado: {geom['type']}"
    if geom["type"] == "Polygon":
        for anillo in geom["coordinates"]:
            yield from anillo
    else:
        for poligono in geom["coordinates"]:
            for anillo in poligono:
                yield from anillo


def test_solo_los_tres_casos_con_perimetro():
    """La guarda cubre exactamente los casos que declaran `perimeter` en el catálogo."""
    esperados = {cid for cid, caso in CASOS.items() if caso.get("perimeter")}
    assert set(ARCHIVOS) == esperados == set(HA_ESPERADO), (
        f"archivos {sorted(ARCHIVOS)}, casos con perimeter {sorted(esperados)}, huella {sorted(HA_ESPERADO)}"
    )


@pytest.mark.parametrize("case_id", sorted(HA_ESPERADO))
def test_geometrias_validas_y_no_vacias(case_id):
    doc = json.loads(ARCHIVOS[case_id].read_text(encoding="utf-8"))
    assert doc["features"], f"{case_id}: sin features"
    for i, feat in enumerate(doc["features"]):
        geom = feat["geometry"]
        assert geom["type"] in ("Polygon", "MultiPolygon"), f"{case_id} feature {i}: tipo {geom['type']}"
        forma = shape(geom)
        assert not forma.is_empty, f"{case_id} feature {i}: geometría vacía"
        assert forma.is_valid, f"{case_id} feature {i}: geometría inválida ({feat['properties'].get('nombre')})"


@pytest.mark.parametrize("case_id", sorted(HA_ESPERADO))
def test_coordenadas_dentro_del_bbox_del_caso(case_id):
    oeste, sur, este, norte = CASOS[case_id]["bbox"]
    doc = json.loads(ARCHIVOS[case_id].read_text(encoding="utf-8"))
    for i, feat in enumerate(doc["features"]):
        for lon, lat, *_ in _puntos(feat["geometry"]):
            assert oeste - MARGEN_BBOX <= lon <= este + MARGEN_BBOX, (
                f"{case_id} feature {i}: lon {lon} fuera de {oeste}..{este} (±{MARGEN_BBOX})"
            )
            assert sur - MARGEN_BBOX <= lat <= norte + MARGEN_BBOX, (
                f"{case_id} feature {i}: lat {lat} fuera de {sur}..{norte} (±{MARGEN_BBOX})"
            )


@pytest.mark.parametrize("case_id", sorted(HA_ESPERADO))
def test_superficie_oficial_sin_recalcular(case_id):
    doc = json.loads(ARCHIVOS[case_id].read_text(encoding="utf-8"))
    assert [f["properties"]["ha"] for f in doc["features"]] == HA_ESPERADO[case_id]
    fids = [f["properties"]["fid"] for f in doc["features"]]
    assert len(set(fids)) == len(fids), f"{case_id}: fid duplicado tras la reparación"

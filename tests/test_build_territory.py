"""Red de seguridad de scripts/build_territory.py: el generador del territorio «solo Chile».

Sin red: la fuente BCN se simula con GeoJSON de juguete en tmp_path y la salida se escribe
con el parámetro `out`, sin tocar web/data. Además clava los invariantes del archivo
publicado (345 comunas, códigos únicos, regiones 1-16, sin la Antártica) y que
Territory ubica puntos de Chile y rechaza los del extranjero.
"""

import json
import sys
from pathlib import Path

import pytest
from shapely.geometry import GeometryCollection, LineString, Polygon, box, mapping, shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_territory import ANTARTICA, REGION_NAMES, build, polygonal  # noqa: E402
from backend.geo import territory  # noqa: E402

DATA = ROOT / "web" / "data"


def _feature(cod_comuna: int, codregion: int, geom, nombre: str = "Comuna de prueba") -> dict:
    return {
        "type": "Feature",
        "properties": {
            "cod_comuna": cod_comuna,
            "codregion": codregion,
            "Comuna": nombre,
            "Provincia": "Provincia de prueba",
            "st_area_sh": 1e6,
        },
        "geometry": mapping(geom),
    }


def _write_sources(tmp_path: Path, features: list[dict]) -> Path:
    src = tmp_path / "src"
    src.mkdir()
    (src / "toy.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": features}), encoding="utf-8")
    return src


@pytest.fixture()
def toy_out(tmp_path: Path) -> Path:
    """Corre build() sobre datos de juguete: 2 comunas válidas, 1 duplicada y 1 Antártica."""
    src = _write_sources(
        tmp_path,
        [
            _feature(7001, 7, box(-72, -36, -71, -35), "Primera"),
            _feature(7002, 7, box(-71, -36, -70, -35), "Segunda"),
            _feature(7001, 7, box(-75, -40, -74, -39), "Duplicada"),
            _feature(ANTARTICA, 12, box(-60, -80, -59, -79), "Antártica"),
        ],
    )
    out = tmp_path / "out"
    build([src], tolerance=0.01, out=out)
    return out


def test_territorio_build_escribe_en_out_y_filtra(toy_out: Path):
    data = json.loads((toy_out / "comunas.geojson").read_text(encoding="utf-8"))
    codes = [f["properties"]["code"] for f in data["features"]]
    assert codes == [7001, 7002], "debe quedar solo las dos comunas válidas, sin duplicado ni Antártica"
    regiones = json.loads((toy_out / "regiones.geojson").read_text(encoding="utf-8"))
    assert [f["properties"]["code"] for f in regiones["features"]] == [7]
    index = json.loads((toy_out / "comunas-index.json").read_text(encoding="utf-8"))
    assert [c["code"] for c in index] == [7001, 7002]


def test_territorio_descarta_codregion_fuera_de_la_tabla(tmp_path: Path):
    src = _write_sources(tmp_path, [_feature(9999, 99, box(-68, -25, -67, -24))])
    out = tmp_path / "out"
    build([src], tolerance=0.01, out=out)
    data = json.loads((out / "comunas.geojson").read_text(encoding="utf-8"))
    assert data["features"] == [], "un codregion fuera de REGION_NAMES no publica comuna"


def test_territorio_conserva_estructura_de_la_salida(toy_out: Path):
    for name in ("comunas", "regiones"):
        data = json.loads((toy_out / f"{name}.geojson").read_text(encoding="utf-8"))
        assert data["type"] == "FeatureCollection"
        assert isinstance(data["attribution"], str) and data["attribution"]
    comunas = json.loads((toy_out / "comunas.geojson").read_text(encoding="utf-8"))
    for feature in comunas["features"]:
        props = feature["properties"]
        assert len(props["center"]) == 2
        assert len(props["bbox"]) == 4
        assert all(isinstance(v, (int, float)) for v in props["center"] + props["bbox"])


def test_polygonal_repara_y_descarta_componentes_sin_area():
    bowtie = Polygon([(0, 0), (1, 1), (1, 0), (0, 1), (0, 0)])
    assert not bowtie.is_valid
    assert polygonal(bowtie).is_valid

    con_linea = GeometryCollection([box(0, 0, 1, 1), LineString([(2, 2), (3, 3)])])
    reparada = polygonal(con_linea)
    assert reparada.is_valid and reparada.geom_type == "Polygon"
    assert reparada.area == 1


def test_polygonal_rechaza_geometria_sin_area():
    """Un polígono degenerado no se publica como línea: el build debe fallar."""
    with pytest.raises(ValueError, match="no conserva área"):
        polygonal(Polygon([(0, 0), (1, 1), (2, 2), (0, 0)]))


def test_territorio_publicado_es_valido_y_se_puede_unir():
    """MAPA-150: las capas publicadas no pueden tener topología inválida."""
    for name in ("comunas", "regiones"):
        data = json.loads((DATA / f"{name}.geojson").read_text(encoding="utf-8"))
        invalidas = [f["properties"]["name"] for f in data["features"] if not shape(f["geometry"]).is_valid]
        assert invalidas == [], f"{name}.geojson con geometrías inválidas: {invalidas}"
        union = unary_union([shape(f["geometry"]) for f in data["features"]])
        assert union.is_valid, f"{name}.geojson: la unión no es válida"


def test_territorio_publicado_tiene_345_comunas_unicas():
    data = json.loads((DATA / "comunas.geojson").read_text(encoding="utf-8"))
    codes = [f["properties"]["code"] for f in data["features"]]
    assert len(codes) == 345
    assert len(set(codes)) == 345, "cada comuna publicada con un solo code"


def test_territorio_publicado_solo_regiones_1_a_16_sin_antartica():
    data = json.loads((DATA / "comunas.geojson").read_text(encoding="utf-8"))
    for feature in data["features"]:
        props = feature["properties"]
        assert 1 <= props["region_code"] <= 16
        assert props["region_code"] in REGION_NAMES
        assert props["code"] != ANTARTICA


def test_territorio_ubica_talca_y_rechaza_el_extranjero():
    t = territory()
    assert t.locate(-35.43, -71.65) is not None, "Talca debe tener comuna"
    assert t.locate(-24.8, -65.4) is None, "Salta (Argentina) no es Chile"
    assert t.locate(-20.46, -66.83) is None, "Uyuni (Bolivia) no es Chile"


def test_territorio_ningun_centro_publicado_queda_sin_comuna():
    t = territory()
    data = json.loads((DATA / "comunas.geojson").read_text(encoding="utf-8"))
    for feature in data["features"]:
        lon, lat = feature["properties"]["center"]
        assert t.locate(lat, lon) is not None, f"centro sin comuna: {feature['properties']['name']}"

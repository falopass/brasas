"""Red de seguridad de scripts/build_territory.py: el generador del territorio «solo Chile».

Sin red: la fuente BCN se simula con GeoJSON de juguete en tmp_path y la salida se escribe
con el parámetro `out`, sin tocar web/data. Además clava que el archivo publicado no
incluya la Antártica y que todo centro publicado caiga en una comuna; la forma de los
GeoJSON y las 345 comunas las cubre test_data_files.py.
"""

import json
import sys
from pathlib import Path

import pytest
from shapely import is_valid
from shapely.geometry import Polygon, box, mapping, shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_territory import (  # noqa: E402
    ANTARTICA,
    build,
    repair_published,
    rounded,
    rounded_valid,
    valid_polygonal,
)
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
    assert data["type"] == "FeatureCollection" and data["attribution"]
    for feature in data["features"]:
        props = feature["properties"]
        assert len(props["center"]) == 2 and len(props["bbox"]) == 4
        assert all(isinstance(v, (int, float)) for v in props["center"] + props["bbox"])

    regiones = json.loads((toy_out / "regiones.geojson").read_text(encoding="utf-8"))
    assert [f["properties"]["code"] for f in regiones["features"]] == [7]
    assert regiones["type"] == "FeatureCollection" and regiones["attribution"]

    index = json.loads((toy_out / "comunas-index.json").read_text(encoding="utf-8"))
    assert [c["code"] for c in index] == [7001, 7002]
    for name, features in (("comunas", data["features"]), ("regiones", regiones["features"])):
        assert all(shape(f["geometry"]).is_valid for f in features), f"{name}: el build publicó una geometría inválida"


def test_territorio_descarta_codregion_fuera_de_la_tabla(tmp_path: Path):
    src = _write_sources(tmp_path, [_feature(9999, 99, box(-68, -25, -67, -24))])
    out = tmp_path / "out"
    build([src], tolerance=0.01, out=out)
    data = json.loads((out / "comunas.geojson").read_text(encoding="utf-8"))
    assert data["features"] == [], "un codregion fuera de REGION_NAMES no publica comuna"


def test_territorio_publicado_sin_antartica():
    """Las 345 comunas y sus regiones las cubre test_data_files.py; aquí solo el
    territorio antártico, que el mapa de incendios no debe publicar."""
    data = json.loads((DATA / "comunas.geojson").read_text(encoding="utf-8"))
    assert all(f["properties"]["code"] != ANTARTICA for f in data["features"])


def test_valid_polygonal_repara_autointerseccion():
    """MAPA-150: el «moño» que GEOS rechaza queda como polígono válido, sin líneas sueltas."""
    bowtie = Polygon([(0, 0), (1, 1), (1, 0), (0, 1)])
    assert not bowtie.is_valid
    fixed = valid_polygonal(bowtie)
    assert fixed.is_valid and fixed.geom_type in ("Polygon", "MultiPolygon")


def test_rounded_valid_repara_lo_que_el_redondeo_invalida():
    """El redondeo a 3 decimales puede invalidar una geometría que era válida."""
    geom = Polygon([(0.0015, 0.0006), (0.0014, 0.0019), (0.0005, 0.0003), (0.0009, 0.001), (0.0014, 0.0005)])
    assert geom.is_valid
    assert not shape(rounded(geom, 3)).is_valid
    fixed = shape(rounded_valid(geom, 3))
    assert fixed.is_valid and fixed.geom_type in ("Polygon", "MultiPolygon")


def test_territorio_publicado_es_valido():
    """MAPA-150: toda comuna y región publicada debe ser válida para GEOS.

    Con una geometría inválida, cualquier operación de conjunto sobre el territorio
    (unir regiones, recortar un episodio, calcular el área de un complejo) revienta.
    """
    for name in ("comunas", "regiones"):
        data = json.loads((DATA / f"{name}.geojson").read_text(encoding="utf-8"))
        invalidas = [f["properties"]["name"] for f in data["features"] if not is_valid(shape(f["geometry"]))]
        assert invalidas == [], f"{name}.geojson: geometrías inválidas {invalidas}"


def test_territorio_publicado_se_puede_unir():
    """La prueba dura de MAPA-150: unary_union de las 345 comunas no lanza TopologyException."""
    data = json.loads((DATA / "comunas.geojson").read_text(encoding="utf-8"))
    union = unary_union([shape(f["geometry"]) for f in data["features"]])
    assert not union.is_empty and union.is_valid


def test_territorio_publicado_se_pueden_unir_las_regiones():
    """La otra operación de conjunto que fallaba con las regiones inválidas."""
    data = json.loads((DATA / "regiones.geojson").read_text(encoding="utf-8"))
    union = unary_union([shape(f["geometry"]) for f in data["features"]])
    assert not union.is_empty and union.is_valid


def test_territorio_cada_centro_publicado_cae_en_su_comuna():
    """MAPA-150: reparar no reasigna ningún centro; cada comuna se sigue encontrando a sí misma."""
    t = territory()
    data = json.loads((DATA / "comunas.geojson").read_text(encoding="utf-8"))
    for feature in data["features"]:
        lon, lat = feature["properties"]["center"]
        hallada = t.locate(lat, lon)
        assert hallada is not None and hallada.code == feature["properties"]["code"], (
            f"centro de {feature['properties']['name']} cae en {hallada.name if hallada else 'ninguna comuna'}"
        )


def test_repair_published_conserva_propiedades_y_es_idempotente(tmp_path: Path):
    """MAPA-150: solo cambia la geometría inválida; propiedades y el resto del archivo quedan igual.

    Se corre sobre una copia de los archivos publicados: valida la promesa del arreglo
    (bytes del resto intactos) y que una segunda pasada no cambie nada.
    """
    original = {}
    for name in ("comunas", "regiones"):
        raw = (DATA / f"{name}.geojson").read_text(encoding="utf-8")
        (tmp_path / f"{name}.geojson").write_text(raw, encoding="utf-8")
        original[name] = json.loads(raw)
    repair_published(tmp_path)
    primera = {name: (tmp_path / f"{name}.geojson").read_text(encoding="utf-8") for name in original}
    repair_published(tmp_path)
    for name, before in original.items():
        after = json.loads(primera[name])
        assert after["type"] == before["type"]
        assert after["attribution"] == before["attribution"]
        assert len(after["features"]) == len(before["features"])
        for vieja, nueva in zip(before["features"], after["features"]):
            assert nueva["properties"] == vieja["properties"], f"{name}: cambiaron las propiedades de {vieja['properties']['name']}"
            if is_valid(shape(vieja["geometry"])):
                assert nueva["geometry"] == vieja["geometry"], f"{name}: tocó una geometría válida"
            else:
                assert is_valid(shape(nueva["geometry"])), f"{name}: {vieja['properties']['name']} sigue inválida"
        assert (tmp_path / f"{name}.geojson").read_text(encoding="utf-8") == primera[name], f"{name}: la reparación no es idempotente"


def test_repair_published_solo_toca_las_invalidas(tmp_path: Path):
    """La reparación deja intacta la comuna válida y arregla la inválida."""
    buena = _feature(7001, 7, box(-72, -36, -71, -35), "Buena")
    mala = _feature(7002, 7, Polygon([(0, 0), (1, 1), (1, 0), (0, 1)]), "Mala")
    for name in ("comunas", "regiones"):
        (tmp_path / f"{name}.geojson").write_text(
            json.dumps({"type": "FeatureCollection", "attribution": "prueba", "features": [buena, mala]}), encoding="utf-8"
        )
    repair_published(tmp_path)
    for name in ("comunas", "regiones"):
        features = json.loads((tmp_path / f"{name}.geojson").read_text(encoding="utf-8"))["features"]
        assert features[0]["geometry"] == json.loads(json.dumps(buena["geometry"])), "la geometría válida no debe cambiar"
        assert is_valid(shape(features[1]["geometry"])), f"{name}: la inválida quedó igual"


def test_territorio_ningun_centro_publicado_queda_sin_comuna():
    t = territory()
    data = json.loads((DATA / "comunas.geojson").read_text(encoding="utf-8"))
    for feature in data["features"]:
        lon, lat = feature["properties"]["center"]
        assert t.locate(lat, lon) is not None, f"centro sin comuna: {feature['properties']['name']}"

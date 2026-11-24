"""Guarda del artefacto de infraestructura crítica (MAPA-181).

Valida `web/data/infraestructura/chile.json` (metadatos de fuentes y licencias, conteos,
forma y encuadre de filas y líneas) y las funciones puras del generador
`scripts/local/build_infraestructura.py` sin importar `osmium` (solo se usa en construcción):
`parse_max_kv`, `dedupe_points`, `simplify_line` y `merge_health`.
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "local"))

from build_infraestructura import dedupe_points, in_chile, merge_health, parse_max_kv, simplify_line  # noqa: E402

DATA = ROOT / "web" / "data" / "infraestructura" / "chile.json"

# Caja de Chile continental e insular (la misma que usa el generador y el resto del repo).
LON_MIN, LON_MAX = -110.0, -66.0
LAT_MIN, LAT_MAX = -56.5, -17.2

# Clave de fila `k` -> nombre de conteo en `counts`.
KIND_A_CONTEO = {"b": "bomberos", "s": "salud", "e": "escuelas", "t": "subestaciones"}


def _load() -> dict:
    with open(DATA, encoding="utf-8") as f:
        return json.load(f)


PAYLOAD = _load()


def _en_chile(lon: float, lat: float) -> bool:
    return LON_MIN <= lon <= LON_MAX and LAT_MIN <= lat <= LAT_MAX


def test_metadatos_obligatorios():
    """`fetched_at` en ISO 8601 con zona UTC, `note` no vacío y fuentes OSM (ODbL) + DEIS (CC0 1.0)."""
    marca = datetime.fromisoformat(PAYLOAD["fetched_at"])  # falla si no es ISO 8601
    assert marca.utcoffset() == timedelta(0), "fetched_at debe declarar zona horaria UTC"
    assert PAYLOAD["note"].strip(), "note vacío: el descargo orientativo es obligatorio"

    osm = PAYLOAD["sources"]["osm"]
    assert osm["license"] == "ODbL"
    assert osm["url"] == "https://www.openstreetmap.org/copyright"

    deis = PAYLOAD["sources"]["deis"]
    assert deis["license"] == "CC0 1.0"
    assert deis["url"] == "https://datos.gob.cl/dataset/3bf4cf7c-f638-4735-9a01-f65faae4beca"


def test_fields_compactos():
    assert PAYLOAD["fields"] == ["lon", "lat", "k", "n", "s", "d"]


def test_counts_reflejan_rows_y_lines():
    """`counts` coincide con lo que hay en `rows` y `lines`, sobre umbrales mínimos razonables."""
    por_clave: dict[str, int] = {}
    for row in PAYLOAD["rows"]:
        por_clave[row[2]] = por_clave.get(row[2], 0) + 1
    for clave, conteo in KIND_A_CONTEO.items():
        assert PAYLOAD["counts"][conteo] == por_clave.get(clave, 0), f"counts.{conteo} no refleja las filas 'k={clave}'"
    assert PAYLOAD["counts"]["lineas_at"] == len(PAYLOAD["lines"])

    assert PAYLOAD["counts"]["bomberos"] >= 500
    assert PAYLOAD["counts"]["salud"] >= 1500
    assert PAYLOAD["counts"]["escuelas"] >= 5000
    assert PAYLOAD["counts"]["subestaciones"] >= 500
    assert PAYLOAD["counts"]["lineas_at"] >= 1000


def test_rows_forma_y_encuadre():
    for row in PAYLOAD["rows"]:
        assert len(row) == 6, f"fila sin los 6 campos declarados en fields: {row!r}"
        lon, lat, clave, _nombre, fuente, _detalle = row
        assert clave in KIND_A_CONTEO, f"clave de categoría inesperada: {clave!r}"
        assert fuente in ("osm", "deis"), f"fuente inesperada: {fuente!r}"
        assert _en_chile(lon, lat), f"fila fuera del encuadre de Chile: {(lon, lat)}"


def test_lines_forma_y_encuadre():
    for line in PAYLOAD["lines"]:
        assert line["kv"] >= 110, f"línea bajo el umbral de 110 kV: {line['kv']}"
        assert line["s"] == "osm", f"línea con fuente distinta de OSM: {line['s']!r}"
        assert len(line["coordinates"]) >= 2, "línea con menos de 2 coordenadas"
        for lon, lat in line["coordinates"]:
            assert _en_chile(lon, lat), f"vértice fuera del encuadre de Chile: {(lon, lat)}"


def test_deis_solo_en_salud_y_con_rural():
    """DEIS alimenta solo la categoría salud y aporta establecimientos rurales (Posta rural / CESFAM)."""
    for row in PAYLOAD["rows"]:
        if row[4] == "deis":
            assert row[2] == "s", f"registro DEIS fuera de la categoría salud: {row!r}"
    detalles_deis = {row[5] for row in PAYLOAD["rows"] if row[4] == "deis"}
    assert any(d in ("Posta rural", "CESFAM") for d in detalles_deis), (
        "sin establecimientos rurales DEIS (Posta rural / CESFAM): la cobertura rural es el aporte clave de DEIS"
    )


def test_territorio_excluye_vecinos_y_conserva_islas():
    """El recorte usa polígono comunal BCN exacto: excluye vecinos fronterizos y conserva islas."""
    assert not in_chile(-68.3234, -54.8138), "Ushuaia (Argentina) debe quedar fuera de Chile"
    assert not in_chile(-68.8458, -32.8895), "Mendoza (Argentina) debe quedar fuera de Chile"
    assert not in_chile(-70.3945, -18.3344), "Chacalluta (Perú) debe quedar fuera de Chile"
    assert not in_chile(-68.6129, -19.2721), "Pisiga (Bolivia) debe quedar fuera de Chile"
    assert not in_chile(-72.3378, -51.5378), "Río Turbio (Argentina) debe quedar fuera de Chile"
    assert in_chile(-109.427, -27.15), "Rapa Nui debe quedar dentro de Chile"
    assert in_chile(-78.833, -33.635), "Juan Fernández debe quedar dentro de Chile"
    assert in_chile(-67.61, -54.934), "Puerto Williams debe quedar dentro de Chile"

    for row in PAYLOAD["rows"]:
        assert in_chile(row[0], row[1], coastal_tol=(row[4] == "deis")), f"fila fuera del polígono chileno: {row!r}"
    for line in PAYLOAD["lines"]:
        for lon, lat in line["coordinates"]:
            assert in_chile(lon, lat), f"vértice fuera del polígono chileno: {(lon, lat)}"
    assert any(row[0] < -105.0 for row in PAYLOAD["rows"]), "Rapa Nui debe tener registros en el artefacto"
    assert any(-81.0 < row[0] < -78.0 and -34.5 < row[1] < -33.0 for row in PAYLOAD["rows"]), (
        "Juan Fernández debe tener registros en el artefacto"
    )


def test_parse_max_kv():
    assert parse_max_kv("220000;110000") == 220
    assert parse_max_kv("110.0 kV;220.0 kV") == 220
    assert parse_max_kv("110/220") == 220
    assert parse_max_kv("220 kV;110 kV") == 220
    assert parse_max_kv("66000") == 66
    assert parse_max_kv("2200") == 2
    assert parse_max_kv("110000-220000") == 0
    assert parse_max_kv("") == 0
    assert parse_max_kv(None) == 0


def test_dedupe_points_prefiere_el_punto_con_nombre():
    """Un punto anónimo a pocos metros de otro con nombre se descarta; el con nombre sobrevive."""
    anonimo = (-70.65, -33.45, "", "osm", "")
    nombrado = (-70.6501, -33.4501, "Cuartel Primera Compañía", "osm", "")
    lejano = (-70.65, -33.6, "Otro cuartel", "osm", "")
    out = dedupe_points([anonimo, nombrado, lejano], radius_m=100.0)
    assert len(out) == 2
    assert {nombre for _lon, _lat, nombre, _src, _det in out} == {"Cuartel Primera Compañía", "Otro cuartel"}


def test_dedupe_points_latitud_austral_frontera_celda():
    """A -53,16° S (Punta Arenas) dos puntos a ~91,6 m colapsan bajo radio 120 m sin perder vecindad X."""
    a = (-70.9015, -53.1626, "Liceo Polivalente Sara Braun", "osm", "")
    b = (-70.9027, -53.1622, "Centro de Estudios La Araucana", "osm", "")
    out = dedupe_points([a, b], radius_m=120.0)
    assert len(out) == 1


def test_simplify_line_conserva_extremos_y_descarta_fuera_de_chile():
    dentros = [(-70.65, -33.45), (-70.60, -33.43), (-70.55, -33.41)]
    out = simplify_line(dentros)
    assert len(out) >= 2
    assert out[0] == [-70.65, -33.45], "simplify_line debe conservar el extremo inicial"
    assert out[-1] == [-70.55, -33.41], "simplify_line debe conservar el extremo final"

    # Un vértice fuera de Chile (incluidos países vecinos como Mendoza) se descarta antes de simplificar.
    con_extranjero = simplify_line([(-70.65, -33.45), (-68.84, -32.89), (0.0, 0.0), (-70.55, -33.41)])
    assert all(_en_chile(lon, lat) for lon, lat in con_extranjero)
    assert con_extranjero[0] == [-70.65, -33.45] and con_extranjero[-1] == [-70.55, -33.41]

    # Una línea enteramente fuera de Chile no deja nada.
    assert simplify_line([(0.0, 0.0), (1.0, 1.0)]) == []


def test_merge_health_prioriza_deis_y_conserva_hospital_osm_aislado():
    """DEIS gana sobre el hospital OSM a <= 500 m; el hospital OSM aislado (> 500 m) se conserva."""
    deis = [(-70.65, -33.45, "Hospital base (DEIS)", "deis", "Hospital")]
    osm_cercano = (-70.6501, -33.4501, "Hospital base (OSM)", "osm", "Hospital")
    osm_aislado = (-70.6, -33.45, "Hospital aislado (OSM)", "osm", "Hospital")
    out = merge_health(deis, [osm_cercano, osm_aislado])
    nombres = [nombre for _lon, _lat, nombre, _src, _det in out]
    assert len(out) == 2
    assert "Hospital base (DEIS)" in nombres
    assert "Hospital base (OSM)" not in nombres, "el hospital OSM a <= 500 m de un DEIS debe ceder"
    assert "Hospital aislado (OSM)" in nombres, "el hospital OSM sin DEIS cerca debe conservarse"

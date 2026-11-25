"""Guarda del artefacto de infraestructura crítica (MAPA-181, teselas de REND-02).

Valida `web/data/infraestructura/` —el índice (metadatos de fuentes y licencias, conteos y
lista de teselas) y las teselas de 1°— reconstruyendo el artefacto nacional a partir de
ellas: forma y encuadre de filas y líneas, la partición equivalente (cada punto en su
tesela, cada línea en todas las de su caja) y las funciones puras del generador
`scripts/local/build_infraestructura.py` sin importar `osmium` (solo se usa en construcción):
`parse_max_kv`, `dedupe_points`, `simplify_line`, `merge_health` y `particionar`.
"""

import hashlib
import json
import math
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "local"))

from build_infraestructura import (  # noqa: E402
    clave_tesela,
    dedupe_points,
    in_chile,
    merge_health,
    parse_max_kv,
    particionar,
    simplify_line,
)

CARPETA = ROOT / "web" / "data" / "infraestructura"
TESELAS = CARPETA / "t"
# Una tesela es una fracción del país: si una sola vuelve a pesar como el archivo nacional
# (1,3 MB), la partición dejó de ahorrar. La más densa (Santiago) mide ~285 KB.
TESELA_MAX_BYTES = 512 * 1024

# Caja de Chile continental e insular (la misma que usa el generador y el resto del repo).
LON_MIN, LON_MAX = -110.0, -66.0
LAT_MIN, LAT_MAX = -56.5, -17.2

# Clave de fila `k` -> nombre de conteo en `counts`.
KIND_A_CONTEO = {"b": "bomberos", "s": "salud", "e": "escuelas", "t": "subestaciones"}


def _leer(ruta: Path) -> dict:
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


INDICE = _leer(CARPETA / "indice.json")
TESELA = {p.stem: _leer(p) for p in sorted(TESELAS.glob("*.json"))}


def _reconstruir() -> dict:
    """El artefacto nacional equivalente: todas las filas y cada línea una vez (por `i`)."""
    lineas: dict[int, dict] = {}
    for t in TESELA.values():
        for line in t["lines"]:
            lineas.setdefault(line["i"], line)
    payload = {k: v for k, v in INDICE.items() if k not in ("paso", "teselas")}
    payload["rows"] = [row for t in TESELA.values() for row in t["rows"]]
    payload["lines"] = [{k: v for k, v in lineas[i].items() if k != "i"} for i in sorted(lineas)]
    return payload


PAYLOAD = _reconstruir()


def _en_chile(lon: float, lat: float) -> bool:
    return LON_MIN <= lon <= LON_MAX and LAT_MIN <= lat <= LAT_MAX


def _celdas_de_la_caja(coordinates: list) -> set[str]:
    lons = [c[0] for c in coordinates]
    lats = [c[1] for c in coordinates]
    return {
        f"{lat}_{lon}"
        for lat in range(math.floor(min(lats)), math.floor(max(lats)) + 1)
        for lon in range(math.floor(min(lons)), math.floor(max(lons)) + 1)
    }


def test_indice_lista_exactamente_las_teselas_publicadas():
    assert INDICE["paso"] == 1
    assert set(INDICE["teselas"]) == set(TESELA), "índice y carpeta t/ deben listar las mismas teselas"
    for clave, t in TESELA.items():
        assert INDICE["teselas"][clave] == {"rows": len(t["rows"]), "lines": len(t["lines"])}, clave
        assert t["rows"] or t["lines"], f"tesela vacía publicada: {clave}"


def test_cada_punto_esta_en_su_tesela():
    for clave, t in TESELA.items():
        for row in t["rows"]:
            assert clave_tesela(row[0], row[1]) == clave, f"fila {row!r} fuera de su tesela {clave}"
            assert clave == f"{math.floor(row[1])}_{math.floor(row[0])}", "clave = <lat>_<lon> de la esquina suroeste"


def test_cada_linea_esta_en_todas_las_teselas_de_su_caja():
    """Un encuadre que cruza una línea también cruza su caja: pidiendo las teselas del
    encuadre y deduplicando por `i`, el mapa no pierde ningún tramo."""
    donde: dict[int, set[str]] = {}
    for clave, t in TESELA.items():
        for line in t["lines"]:
            donde.setdefault(line["i"], set()).add(clave)
            assert line == {"i": line["i"], **PAYLOAD["lines"][line["i"]]}, "las copias de una línea son idénticas"
    assert sorted(donde) == list(range(len(PAYLOAD["lines"]))), "ids de línea contiguos y sin huecos"
    for i, claves in donde.items():
        assert claves == _celdas_de_la_caja(PAYLOAD["lines"][i]["coordinates"]), f"línea {i}"


def test_las_teselas_son_una_fraccion_del_pais():
    for p in TESELAS.glob("*.json"):
        assert p.stat().st_size <= TESELA_MAX_BYTES, f"{p.name} pesa {p.stat().st_size} B"
    assert (CARPETA / "indice.json").stat().st_size <= 16 * 1024, "el índice se pide al prender la capa: debe ser liviano"
    assert not (CARPETA / "chile.json").exists(), "el archivo nacional se reemplazó por teselas"


def test_particionar_es_equivalente_y_cubre_los_bordes():
    punto = [-70.5, -33.5, "b", "Cuartel", "osm", ""]
    borde = [-71.0, -34.0, "s", "Posta", "deis", "Posta rural"]  # justo en la esquina: tesela -34_-71
    linea = {"coordinates": [[-71.5, -33.5], [-70.5, -32.5]], "kv": 220, "n": "", "s": "osm"}
    payload = {"fetched_at": "2026-11-24T01:52:13+00:00", "counts": {}, "fields": [], "rows": [punto, borde], "lines": [linea]}
    indice, teselas = particionar(payload)
    assert teselas["-34_-71"]["rows"] == [punto, borde]
    assert set(teselas) == {"-34_-71", "-34_-72", "-33_-72", "-33_-71"}
    assert all(t["lines"] == [{"i": 0, **linea}] for t in teselas.values())
    assert indice["teselas"]["-33_-72"] == {"rows": 0, "lines": 1}
    assert indice["fetched_at"] == payload["fetched_at"] and "rows" not in indice and "lines" not in indice


def test_particion_conserva_el_artefacto_original():
    """Huellas del chile.json de b65bbb4, antes de particionar, no del generador nuevo.

    Una actualización de la fuente debe renovar estas huellas con el artefacto
    nacional de entrada; una optimización no puede cambiar datos ni precisión.
    """
    def canon(valor):
        return json.dumps(valor, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()

    filas = sorted(PAYLOAD["rows"], key=canon)
    metadatos = {k: v for k, v in PAYLOAD.items() if k not in ("rows", "lines")}
    assert len(filas) == 15210 and len(PAYLOAD["lines"]) == 2009
    assert hashlib.sha256(canon(filas)).hexdigest() == "197d7860ded76acf6183e23dfecf21c68c881ddc7f07cd28a7339ae13a1ff95d"
    assert hashlib.sha256(canon(PAYLOAD["lines"])).hexdigest() == "5eb452110da8d75c4c857432b337a7450f11135a27715b96562687ad6aac67b7"
    assert hashlib.sha256(canon(metadatos)).hexdigest() == "db176ff0c3a5933a2f9c318e68e513b8a84a3bec21c195e080f3a1440873a6b9"


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

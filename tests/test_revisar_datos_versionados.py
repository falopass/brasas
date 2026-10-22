"""AUTO-45: la sonda de frescura de web/data (scripts/local/revisar_datos_versionados.py).

Cubre la clasificación sobre archivos temporales —vigente, vencido, sin reloj, exento,
sin política e ilegible— y el inventario: cada dato real de web/data debe tener política
(caduca en CADUCIDAD_DIAS o está exento en EXENTOS). Un dato nuevo no puede entrar sin ella.
"""

import fnmatch
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "local"))

import revisar_datos_versionados as rdv  # noqa: E402

HOY = datetime(2026, 10, 21, tzinfo=timezone.utc)


def _hace(dias: int) -> str:
    return (HOY - timedelta(days=dias)).isoformat()


def _escribe(directorio: Path, nombre: str, data=None, texto=None) -> Path:
    p = directorio / nombre
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(texto if texto is not None else json.dumps(data), encoding="utf-8")
    return p


def _fila(filas, nombre):
    return {f["archivo"]: f for f in filas}[nombre]


@pytest.mark.parametrize(
    "nombre, data, estado, edad, caducidad",
    [
        pytest.param("censo_2024.json", {"fetched_at": _hace(30)}, "vigente", 30, 365, id="vigente"),
        pytest.param("censo_2024.json", {"fetched_at": _hace(365)}, "vigente", 365, 365, id="al-limite"),
        pytest.param("censo_2024.json", {"fetched_at": _hace(400)}, "vencido", 400, 365, id="vencido"),
        pytest.param("temporada-2526.json", {"fetched_at": _hace(46)}, "vencido", 46, 45, id="temporada-45-dias"),
        pytest.param("interfaz.json", {"source": "https://ejemplo.cl", "datos": []}, "sin-reloj", None, 365, id="sin-reloj"),
        pytest.param("snaspe.json", {"source": {"name": "CONAF", "fetched_at": _hace(10)}}, "vigente", 10, 365, id="fecha-anidada"),
        pytest.param("prioritarias.json", {"fetched_at": "2026-10-19"}, "vigente", 2, 365, id="solo-dia"),
        pytest.param("comunas.geojson", {"type": "FeatureCollection", "features": []}, "sin-reloj", None, 365, id="geojson"),
    ],
)
def test_clasificacion(tmp_path, nombre, data, estado, edad, caducidad):
    _escribe(tmp_path, nombre, data)
    fila = _fila(rdv.revisar(tmp_path, HOY), nombre)
    assert fila["estado"] == estado and fila.get("edad_dias") == edad
    assert fila["caducidad_dias"] == caducidad


def test_json_corrupto_es_ilegible_y_no_es_vencido(tmp_path):
    _escribe(tmp_path, "censo_2024.json", texto="{esto no es json")
    assert _fila(rdv.revisar(tmp_path, HOY), "censo_2024.json")["estado"] == "ilegible"
    assert rdv.main(["--data-dir", str(tmp_path)]) == 0


def test_codigos_de_salida(tmp_path):
    vacio = tmp_path / "vacio"
    vacio.mkdir()
    assert rdv.main(["--data-dir", str(vacio)]) == 2  # sin datos no hay veredicto

    _escribe(tmp_path, "censo_2024.json", {"fetched_at": _hace(400)})
    assert rdv.main(["--data-dir", str(tmp_path), "--hoy", "2026-10-21"]) == 1
    _escribe(tmp_path, "censo_2024.json", {"fetched_at": _hace(30)})
    assert rdv.main(["--data-dir", str(tmp_path), "--hoy", "2026-10-21"]) == 0


def test_exentos_no_necesitan_fecha(tmp_path):
    _escribe(tmp_path, "persistent_hotspots.json", {"sources": []})
    _escribe(tmp_path, "cases.json", {"cases": []})
    _escribe(tmp_path, "cases/caso-2000.timeline.json", {"events": []})
    filas = rdv.revisar(tmp_path, HOY)
    for nombre in ("persistent_hotspots.json", "cases.json", "cases/caso-2000.timeline.json"):
        assert _fila(filas, nombre)["estado"] == "exento"


def test_dato_nuevo_sin_politica(tmp_path):
    _escribe(tmp_path, "dato-nuevo.json", {"fetched_at": HOY.isoformat()})
    assert _fila(rdv.revisar(tmp_path, HOY), "dato-nuevo.json")["estado"] == "sin-politica"


def test_salida_json_valida(tmp_path, capsys):
    _escribe(tmp_path, "censo_2024.json", {"fetched_at": HOY.isoformat()})
    assert rdv.main(["--data-dir", str(tmp_path), "--json", "--hoy", "2026-10-21"]) == 0
    salida = json.loads(capsys.readouterr().out)
    assert salida["hoy"] == "2026-10-21"
    assert salida["resumen"] == {"vigente": 1}
    assert salida["archivos"][0]["archivo"] == "censo_2024.json"


def test_alerta_md_solo_con_vencidos(tmp_path):
    _escribe(tmp_path, "censo_2024.json", {"fetched_at": _hace(400)})
    md = tmp_path / "alerta.md"
    assert rdv.main(["--data-dir", str(tmp_path), "--hoy", "2026-10-21", "--alerta-md", str(md)]) == 1
    cuerpo = md.read_text(encoding="utf-8")
    assert "censo_2024.json" in cuerpo and "build_censo.py" in cuerpo

    _escribe(tmp_path, "censo_2024.json", {"fetched_at": HOY.isoformat()})
    md.unlink()
    assert rdv.main(["--data-dir", str(tmp_path), "--hoy", "2026-10-21", "--alerta-md", str(md)]) == 0
    assert not md.exists()


def test_inventario_cada_dato_tiene_politica():
    filas = rdv.revisar(rdv.DATA, HOY)
    assert filas, "web/data está vacío"
    sin_politica = [f["archivo"] for f in filas if f["estado"] == "sin-politica"]
    assert not sin_politica, (
        f"{sin_politica} no tiene(n) política de frescura: declara su caducidad en "
        "CADUCIDAD_DIAS o su exención en EXENTOS (scripts/local/revisar_datos_versionados.py)"
    )
    # Guarda al revés: una fila de política que no calza con nada quedó obsoleta.
    archivos = [f["archivo"] for f in filas]
    for tabla in (rdv.CADUCIDAD_DIAS, rdv.EXENTOS):
        muertos = [p for p in tabla if not any(fnmatch.fnmatch(a, p) for a in archivos)]
        assert not muertos, f"patrones sin archivo que los use: {muertos}"
    # Y ningún dato publicado debería estar corrupto.
    assert not [f["archivo"] for f in filas if f["estado"] == "ilegible"]

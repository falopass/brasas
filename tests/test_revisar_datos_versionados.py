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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "local"))

import revisar_datos_versionados as rdv  # noqa: E402

HOY = datetime(2026, 10, 21, tzinfo=timezone.utc)


def _escribe(directorio: Path, nombre: str, data=None, texto=None) -> Path:
    p = directorio / nombre
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(texto if texto is not None else json.dumps(data), encoding="utf-8")
    return p


def _fila(filas, nombre):
    return {f["archivo"]: f for f in filas}[nombre]


def test_vigente_dentro_de_caducidad(tmp_path):
    _escribe(tmp_path, "censo_2024.json", {"fetched_at": (HOY - timedelta(days=30)).isoformat()})
    fila = _fila(rdv.revisar(tmp_path, HOY), "censo_2024.json")
    assert fila["estado"] == "vigente"
    assert fila["edad_dias"] == 30
    assert fila["caducidad_dias"] == 365


def test_al_limite_aun_vigente(tmp_path):
    _escribe(tmp_path, "censo_2024.json", {"fetched_at": (HOY - timedelta(days=365)).isoformat()})
    assert _fila(rdv.revisar(tmp_path, HOY), "censo_2024.json")["estado"] == "vigente"


def test_vencido_sale_1(tmp_path):
    _escribe(tmp_path, "censo_2024.json", {"fetched_at": (HOY - timedelta(days=400)).isoformat()})
    fila = _fila(rdv.revisar(tmp_path, HOY), "censo_2024.json")
    assert fila["estado"] == "vencido" and fila["edad_dias"] == 400
    assert rdv.main(["--data-dir", str(tmp_path), "--hoy", "2026-10-21"]) == 1


def test_temporada_caduca_a_los_45_dias(tmp_path):
    _escribe(
        tmp_path,
        "temporada-2526.json",
        {"fetched_at": (HOY - timedelta(days=46)).isoformat()},
    )
    assert _fila(rdv.revisar(tmp_path, HOY), "temporada-2526.json")["estado"] == "vencido"


def test_sin_reloj_declarado(tmp_path):
    _escribe(tmp_path, "interfaz.json", {"source": "https://ejemplo.cl", "datos": []})
    fila = _fila(rdv.revisar(tmp_path, HOY), "interfaz.json")
    assert fila["estado"] == "sin-reloj"
    assert rdv.main(["--data-dir", str(tmp_path), "--hoy", "2026-10-21"]) == 0


def test_fecha_en_source_anidada(tmp_path):
    # Convención de build_snaspe/build_historia_comunas: la fecha vive en source.fetched_at.
    _escribe(
        tmp_path,
        "snaspe.json",
        {"source": {"name": "CONAF", "fetched_at": (HOY - timedelta(days=10)).isoformat()}},
    )
    fila = _fila(rdv.revisar(tmp_path, HOY), "snaspe.json")
    assert fila["estado"] == "vigente" and fila["edad_dias"] == 10


def test_fecha_solo_dia_sin_zona(tmp_path):
    # prioritarias.json declara «2026-10-19»: se lee como medianoche UTC.
    _escribe(tmp_path, "prioritarias.json", {"fetched_at": "2026-10-19"})
    fila = _fila(rdv.revisar(tmp_path, HOY), "prioritarias.json")
    assert fila["estado"] == "vigente" and fila["edad_dias"] == 2


def test_json_corrupto_es_ilegible(tmp_path):
    _escribe(tmp_path, "censo_2024.json", texto="{esto no es json")
    fila = _fila(rdv.revisar(tmp_path, HOY), "censo_2024.json")
    assert fila["estado"] == "ilegible"
    # Ilegible no es vencido: el código de salida sigue siendo 0.
    assert rdv.main(["--data-dir", str(tmp_path)]) == 0


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


def test_geojson_tambien_se_revisa(tmp_path):
    _escribe(tmp_path, "comunas.geojson", {"type": "FeatureCollection", "features": []})
    assert _fila(rdv.revisar(tmp_path, HOY), "comunas.geojson")["estado"] == "sin-reloj"


def test_directorio_sin_datos_sale_2(tmp_path):
    assert rdv.main(["--data-dir", str(tmp_path)]) == 2


def test_salida_json_valida(tmp_path, capsys):
    _escribe(tmp_path, "censo_2024.json", {"fetched_at": HOY.isoformat()})
    assert rdv.main(["--data-dir", str(tmp_path), "--json", "--hoy", "2026-10-21"]) == 0
    salida = json.loads(capsys.readouterr().out)
    assert salida["hoy"] == "2026-10-21"
    assert salida["resumen"] == {"vigente": 1}
    assert salida["archivos"][0]["archivo"] == "censo_2024.json"


def test_alerta_md_solo_con_vencidos(tmp_path):
    _escribe(tmp_path, "censo_2024.json", {"fetched_at": (HOY - timedelta(days=400)).isoformat()})
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

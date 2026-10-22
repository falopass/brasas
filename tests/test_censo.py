"""`web/data/censo_2024.json`: archivo publicado y caché del índice (CENSO-01).

El archivo lo genera scripts/local/build_censo.py y se versiona con el repo. El índice
se cachea por la firma del archivo (mtime_ns y tamaño), así que regenerarlo hace que la
siguiente consulta lo relea. La lectura tolerante de filas vive en test_censo_ficha.py
(OFI-29).
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path

import pytest

from backend import censo
from tests.contrato_datos import validate_censo_2024

ROOT = Path(__file__).resolve().parents[1]
CENSO = json.loads((ROOT / "web" / "data" / "censo_2024.json").read_text())
INDEX = {c["code"]: c["name"] for c in json.loads((ROOT / "web" / "data" / "comunas-index.json").read_text())}
TALCA = 7101


@pytest.fixture(autouse=True)
def _limpia_cache():
    censo._cache = None
    yield
    censo._cache = None


def _fila(code: int, **cambios) -> dict:
    fila = {
        "code": code,
        "poblacion": 100,
        "viviendas": 40,
        "hogares": 30,
        "source": "https://www.ine.gob.cl/",
        "fetched_at": "2026-10-19T13:09:49+00:00",
    }
    fila.update(cambios)
    return fila


def _escribe(tmp_path: Path, monkeypatch, comunas) -> Path:
    ruta = tmp_path / "censo.json"
    ruta.write_text(json.dumps({"license": "CC BY-SA 4.0", "comunas": comunas}), encoding="utf-8")
    monkeypatch.setattr(censo, "CENSO_FILE", ruta)
    return ruta


# --- archivo publicado ---


def test_file_documents_source_license_and_totals():
    validate_censo_2024(CENSO)
    assert CENSO["source"].startswith("https://")
    assert "INE" in CENSO["license"] and "CC BY-SA" in CENSO["license"]
    assert CENSO["fetched_at"] and CENSO["notes"]
    assert set(CENSO["totals"]) == {"poblacion", "viviendas", "hogares"}


def test_codes_match_the_territory_index_without_duplicates():
    codes = [c["code"] for c in CENSO["comunas"]]
    assert len(codes) == len(set(codes))
    assert set(codes) <= set(INDEX)
    assert all(INDEX[c["code"]] == c["name"] for c in CENSO["comunas"])
    assert all(c["poblacion"] > 0 and c["viviendas"] > 0 and c["hogares"] > 0 for c in CENSO["comunas"])
    assert all(c["source"].startswith("https://") and c["fetched_at"] for c in CENSO["comunas"])
    # Comuna del índice sin dato: permitida solo si queda constancia en las notas.
    missing = set(INDEX) - set(codes)
    assert all(str(code) in " ".join(CENSO["notes"]) for code in missing)


def test_totals_match_the_sum_of_the_rows():
    assert sum(c["poblacion"] for c in CENSO["comunas"]) == CENSO["totals"]["poblacion"]
    assert sum(c["viviendas"] for c in CENSO["comunas"]) == CENSO["totals"]["viviendas"]
    assert sum(c["hogares"] for c in CENSO["comunas"]) == CENSO["totals"]["hogares"]


# --- contrato del archivo publicado (CALIDAD-03) ---


@pytest.mark.parametrize(
    ("campo", "valor", "mensaje"),
    [
        ("source", "", "'source'"),
        ("license", "  ", "'license'"),
        ("fetched_at", "ayer", "no ISO"),
        ("fetched_at", "2026-10-19T13:09:49", "sin zona"),
    ],
)
def test_contrato_rechaza_metadatos(campo, valor, mensaje):
    data = copy.deepcopy(CENSO)
    data[campo] = valor
    with pytest.raises(ValueError, match=mensaje):
        validate_censo_2024(data)


def test_contrato_rechaza_sin_comunas():
    data = copy.deepcopy(CENSO)
    del data["comunas"]
    with pytest.raises(ValueError, match="'comunas'"):
        validate_censo_2024(data)


def test_contrato_rechaza_pocas_comunas():
    data = copy.deepcopy(CENSO)
    data["comunas"] = data["comunas"][:10]
    with pytest.raises(ValueError, match="300"):
        validate_censo_2024(data)


@pytest.mark.parametrize(
    ("campo", "valor", "mensaje"),
    [
        ("code", "01101", "code no entero"),
        ("poblacion", -5, "'poblacion' negativo"),
        ("viviendas", True, "'viviendas' no numérico"),
    ],
)
def test_contrato_rechaza_fila(campo, valor, mensaje):
    data = copy.deepcopy(CENSO)
    data["comunas"][0][campo] = valor
    with pytest.raises(ValueError, match=mensaje):
        validate_censo_2024(data)


def test_contrato_rechaza_code_duplicado():
    data = copy.deepcopy(CENSO)
    data["comunas"][1]["code"] = data["comunas"][0]["code"]
    with pytest.raises(ValueError, match="duplicado"):
        validate_censo_2024(data)


# --- caché del archivo (CENSO-01) ---


def test_dos_consultas_seguidas_no_releen_el_archivo(tmp_path, monkeypatch):
    ruta = _escribe(tmp_path, monkeypatch, [_fila(TALCA)])
    lecturas = []
    original = Path.read_text

    def espia(self, *args, **kwargs):
        if self == ruta:
            lecturas.append(self)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", espia)

    assert censo.comuna(TALCA) is not None
    assert censo.comuna(TALCA) is not None
    assert len(censo.problemas()) == 0
    assert len(lecturas) == 1


def test_un_archivo_regenerado_se_relee(tmp_path, monkeypatch):
    ruta = _escribe(tmp_path, monkeypatch, [_fila(TALCA, poblacion=100)])
    assert censo.comuna(TALCA)["poblacion"] == 100

    ruta.write_text(json.dumps({"license": "CC BY-SA 4.0", "comunas": [_fila(TALCA, poblacion=200)]}), encoding="utf-8")
    os.utime(ruta, ns=(1_800_000_000_000_000_000, 1_800_000_000_000_000_000))  # mtime_ns distinto: la firma cambia
    assert censo.comuna(TALCA)["poblacion"] == 200


def test_archivo_ilegible_deja_exposicion_null_y_problema_con_el_error(tmp_path, monkeypatch):
    ruta = _escribe(tmp_path, monkeypatch, [_fila(TALCA)])
    ruta.write_text("{esto no es json", encoding="utf-8")

    assert censo.comuna(TALCA) is None
    assert censo.salud()["filas"] == 0
    assert any("no se pudo leer" in p for p in censo.problemas())


def test_una_fila_descartada_aparece_en_problemas_y_en_salud(tmp_path, monkeypatch):
    _escribe(tmp_path, monkeypatch, [_fila(TALCA), _fila(7202, poblacion=-1)])

    assert censo.comuna(7202) is None
    problema = next(p for p in censo.problemas() if "7202" in p)
    assert "poblacion" in problema
    salud = censo.salud()
    assert salud["filas"] == 1 and salud["descartadas"] == 1
    assert salud["problemas"] == censo.problemas()

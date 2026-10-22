"""`web/data/interfaz.json`: forma, códigos contra `comunas-index.json` y porcentajes en 0..100."""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import pytest

from tests.contrato_datos import validate_interfaz

ROOT = Path(__file__).resolve().parents[1]
INTERFAZ = json.loads((ROOT / "web" / "data" / "interfaz.json").read_text())
INDEX = {c["code"]: c["name"] for c in json.loads((ROOT / "web" / "data" / "comunas-index.json").read_text())}


def test_file_documents_source_license_and_date():
    validate_interfaz(INTERFAZ, INDEX)
    assert INTERFAZ["source"].startswith("https://")
    assert "CONAF" in INTERFAZ["license"]
    assert INTERFAZ["fetched_at"] and INTERFAZ["notes"]


def test_each_comuna_has_positive_area_and_pct_in_range():
    for code, c in INTERFAZ["comunas"].items():
        assert code.isdigit() and int(code) in INDEX
        assert isinstance(c["ha_interfaz"], (int, float)) and c["ha_interfaz"] > 0
        assert 0 < c["pct_comuna"] <= 100


def test_coverage_is_at_least_90_percent():
    assert len(INTERFAZ["comunas"]) / len(INDEX) >= 0.9


# --- contrato del archivo publicado (CALIDAD-03) ---


@pytest.mark.parametrize(
    ("campo", "valor", "mensaje"),
    [
        ("source", "", "'source'"),
        ("license", "  ", "'license'"),
        ("fetched_at", "ayer", "no ISO"),
        ("fetched_at", "2026-10-20T05:50:56", "sin zona"),
    ],
)
def test_contrato_rechaza_metadatos(campo, valor, mensaje):
    data = copy.deepcopy(INTERFAZ)
    data[campo] = valor
    with pytest.raises(ValueError, match=mensaje):
        validate_interfaz(data, INDEX)


def test_contrato_rechaza_sin_comunas():
    data = copy.deepcopy(INTERFAZ)
    del data["comunas"]
    with pytest.raises(ValueError, match="'comunas'"):
        validate_interfaz(data, INDEX)


def test_contrato_rechaza_pocas_comunas():
    data = copy.deepcopy(INTERFAZ)
    data["comunas"] = dict(list(data["comunas"].items())[:10])
    with pytest.raises(ValueError, match="300"):
        validate_interfaz(data, INDEX)


def test_contrato_rechaza_clave_no_numerica():
    data = copy.deepcopy(INTERFAZ)
    data["comunas"]["norte"] = {"ha_interfaz": 1.0, "pct_comuna": 0.5}
    with pytest.raises(ValueError, match="clave no numérica"):
        validate_interfaz(data, INDEX)


def test_contrato_rechaza_clave_sin_comuna_en_index():
    data = copy.deepcopy(INTERFAZ)
    data["comunas"]["99999"] = {"ha_interfaz": 1.0, "pct_comuna": 0.5}
    with pytest.raises(ValueError, match="sin comuna en comunas-index"):
        validate_interfaz(data, INDEX)


@pytest.mark.parametrize(
    ("campo", "valor", "mensaje"),
    [
        ("ha_interfaz", -0.1, "'ha_interfaz' negativo"),
        ("ha_interfaz", True, "'ha_interfaz' no numérico"),
        ("pct_comuna", 120.0, r"\[0, 100\]"),
        ("pct_comuna", -1.0, r"\[0, 100\]"),
        ("pct_comuna", "0.5", "'pct_comuna' no numérico"),
    ],
)
def test_contrato_rechaza_cifra(campo, valor, mensaje):
    data = copy.deepcopy(INTERFAZ)
    data["comunas"][next(iter(data["comunas"]))][campo] = valor
    with pytest.raises(ValueError, match=mensaje):
        validate_interfaz(data, INDEX)


def _assert_notes_document_missing(interfaz):
    """Exige que la nota de omitidas liste exactamente las comunas sin dato."""
    faltantes = set(INDEX) - {int(c) for c in interfaz["comunas"]}
    notas = [n for n in interfaz["notes"] if "omitida" in n]
    documentados = {int(m) for n in notas for m in re.findall(r"\b\d{4,5}\b", n)}
    assert documentados <= set(INDEX), f"códigos ajenos al índice: {sorted(documentados - set(INDEX))}"
    assert documentados == faltantes, (
        f"sin documentar: {sorted(faltantes - documentados)}; documentados de más: {sorted(documentados - faltantes)}"
    )


def test_notes_document_exactly_the_missing_comunas():
    _assert_notes_document_missing(INTERFAZ)


def test_note_check_fails_when_a_comuna_is_dropped():
    alterado = copy.deepcopy(INTERFAZ)
    alterado["comunas"].popitem()
    with pytest.raises(AssertionError):
        _assert_notes_document_missing(alterado)


def test_note_check_fails_when_note_lists_unknown_code():
    alterado = copy.deepcopy(INTERFAZ)
    i = next(k for k, n in enumerate(alterado["notes"]) if "omitida" in n)
    alterado["notes"][i] += ", 99999"
    with pytest.raises(AssertionError):
        _assert_notes_document_missing(alterado)

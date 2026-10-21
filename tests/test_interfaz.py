"""`web/data/interfaz.json`: forma, códigos contra `comunas-index.json` y porcentajes en 0..100."""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
INTERFAZ = json.loads((ROOT / "web" / "data" / "interfaz.json").read_text())
INDEX = {c["code"]: c["name"] for c in json.loads((ROOT / "web" / "data" / "comunas-index.json").read_text())}


def test_file_documents_source_license_and_date():
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

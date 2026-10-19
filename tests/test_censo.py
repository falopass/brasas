"""`web/data/censo_2024.json`: forma, códigos contra `comunas-index.json` y totales declarados."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CENSO = json.loads((ROOT / "web" / "data" / "censo_2024.json").read_text())
INDEX = {c["code"]: c["name"] for c in json.loads((ROOT / "web" / "data" / "comunas-index.json").read_text())}


def test_file_documents_source_license_and_totals():
    assert CENSO["source"].startswith("https://")
    assert "INE" in CENSO["license"] and "CC BY-SA" in CENSO["license"]
    assert CENSO["fetched_at"] and CENSO["notes"]
    assert set(CENSO["totals"]) == {"poblacion", "viviendas", "hogares"}


def test_each_comuna_has_the_fields_and_positive_numbers():
    for c in CENSO["comunas"]:
        assert isinstance(c["code"], int) and isinstance(c["name"], str) and c["name"]
        assert isinstance(c["poblacion"], int) and c["poblacion"] > 0
        assert isinstance(c["viviendas"], int) and c["viviendas"] > 0
        assert isinstance(c["hogares"], int) and c["hogares"] > 0
        assert c["source"].startswith("https://") and c["fetched_at"]


def test_codes_match_the_territory_index_without_duplicates():
    codes = [c["code"] for c in CENSO["comunas"]]
    assert len(codes) == len(set(codes))
    assert set(codes) <= set(INDEX)
    assert all(INDEX[c["code"]] == c["name"] for c in CENSO["comunas"])
    # Comuna del índice sin dato: permitida solo si queda constancia en las notas.
    missing = set(INDEX) - set(codes)
    assert all(str(code) in " ".join(CENSO["notes"]) for code in missing)


def test_totals_match_the_sum_of_the_rows():
    assert sum(c["poblacion"] for c in CENSO["comunas"]) == CENSO["totals"]["poblacion"]
    assert sum(c["viviendas"] for c in CENSO["comunas"]) == CENSO["totals"]["viviendas"]
    assert sum(c["hogares"] for c in CENSO["comunas"]) == CENSO["totals"]["hogares"]

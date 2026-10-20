"""`web/data/interfaz.json`: forma, códigos contra `comunas-index.json` y porcentajes en 0..100."""

from __future__ import annotations

import json
from pathlib import Path

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


def test_coverage_is_at_least_90_percent_or_documented():
    codes = {int(c) for c in INTERFAZ["comunas"]}
    missing = set(INDEX) - codes
    if len(codes) / len(INDEX) < 0.9:
        # Cobertura baja: permitida solo si cada comuna sin dato queda en las notas.
        assert all(str(code) in " ".join(INTERFAZ["notes"]) for code in missing)

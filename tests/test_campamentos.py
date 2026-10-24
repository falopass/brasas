"""OFI-25: el agregado de campamentos MINVU por comuna (`web/data/campamentos.json`).

Contrato mínimo: solo el agregado (code, name, region, conteos) — nunca nombres, folios ni
coordenadas de campamentos (SEC-01..SEC-05: un punto señala hogares vulnerables). Los códigos
son los del índice territorial y la fuente va citada con su salvedad de licencia.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "web" / "data"


def _load(nombre):
    return json.loads((DATA / nombre).read_text(encoding="utf-8"))


def test_campamentos_json_forma():
    data = _load("campamentos.json")
    assert data["source"].startswith("https://")
    assert "MINVU" in data["license"]
    comunas = data["comunas"]
    assert len(comunas) >= 100, "el catastro cubre buena parte del país"
    for c in comunas:
        assert set(c) == {"code", "name", "region", "n_campamentos", "n_hogares"}, \
            f"columna fuera del contrato (¿se coló un dato puntual?): {sorted(c)}"
        assert isinstance(c["code"], int) and isinstance(c["n_campamentos"], int)
        assert c["n_campamentos"] >= 1 and c["n_hogares"] >= 0


def test_campamentos_codes_son_comunas_reales():
    index = {c["code"] for c in _load("comunas-index.json")}
    for c in _load("campamentos.json")["comunas"]:
        assert c["code"] in index, f"{c['code']} no es una comuna del territorio"


def test_build_agrega_sin_datos_puntuales():
    """El agregador solo cuenta y suma: nombres/folios/coords de la fuente no propagan."""
    from scripts.local.build_campamentos import build

    raw = {"fetched_at": "2026-10-24T00:00:00+00:00", "features": [
        {"attributes": {"COM": "Iquique", "REG": "Tarapacá", "HOGARESCAT": 10.0,
                        "NOM": "No debe salir", "FOLIO": 1, "POINT_X": -70.0, "POINT_Y": -20.0}},
        {"attributes": {"COM": "Iquique", "REG": "Tarapacá", "HOGARESCAT": 5.0}},
        {"attributes": {"COM": "Iquique", "REG": "Tarapacá", "HOGARESCAT": None}},
        {"attributes": {"COM": "Inexistente", "REG": "X", "HOGARESCAT": 3.0}},
    ]}
    out = build(raw)
    assert len(out["comunas"]) == 1
    fila = out["comunas"][0]
    assert fila["name"] == "Iquique" and fila["n_campamentos"] == 3 and fila["n_hogares"] == 15
    assert "Inexistente" in out["notes"][-1]
    assert "No debe salir" not in json.dumps(out, ensure_ascii=False)

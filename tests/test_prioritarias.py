"""OFI-05: estructura de web/data/prioritarias.json (comunas prioritarias CONAF)."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = json.loads((ROOT / "web" / "data" / "prioritarias.json").read_text(encoding="utf-8"))
INDEX = json.loads((ROOT / "web" / "data" / "comunas-index.json").read_text(encoding="utf-8"))
CODIGOS = {c["code"] for c in INDEX}


def test_json_parseable_y_verified_booleano():
    assert isinstance(DATA, dict)
    assert isinstance(DATA["verified"], bool)
    assert isinstance(DATA["comunas"], list)


def test_sin_verificar_lista_vacia():
    if not DATA["verified"]:
        assert DATA["comunas"] == []


def test_comunas_verificadas_validas():
    if not DATA["verified"]:
        return
    vistos = set()
    for comuna in DATA["comunas"]:
        cod = comuna["cod_comuna"]
        assert re.fullmatch(r"\d{5}", cod), f"cod_comuna inválido: {cod!r}"
        assert cod not in vistos, f"cod_comuna duplicado: {cod}"
        vistos.add(cod)
        assert comuna["nombre"].strip(), f"nombre vacío para {cod}"
        assert int(cod) in CODIGOS, f"cod_comuna {cod} no existe en comunas-index.json"

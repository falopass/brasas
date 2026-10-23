"""VEC-02: guardas de la vista Mi zona sobre la temporada 2025-26 por comuna,
más el contrato del JSON versionado que la vista consume."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ZONA = (ROOT / "web" / "js" / "views" / "zona.js").read_text(encoding="utf-8")
TEMPORADA = json.loads((ROOT / "web" / "data" / "temporada-2526.json").read_text(encoding="utf-8"))


def test_la_vista_carga_el_json_de_la_temporada():
    assert "/web/data/temporada-2526.json" in ZONA


def test_el_bloque_usa_dual_e_imprime_la_fuente():
    assert "La temporada pasada en tu comuna" in ZONA
    assert "dual(" in ZONA
    assert "CONAF, reporte público de incendios (GEPRIF)" in ZONA
    assert "fetched_at" in ZONA  # «datos al …» visible


def test_sin_cifras_literales_en_el_bloque():
    bloque = ZONA.split("function seasonBlock", 1)[1]
    # los números salen de row.*; ninguna cifra de incendios o hectáreas escrita a mano
    assert "row.incendios" in bloque and "row.hectareas" in bloque
    assert not re_busca_cifra(bloque), "cifra literal de temporada en la vista"


def re_busca_cifra(bloque: str) -> bool:
    import re
    return bool(re.search(r"informó\s+\d+|quemaron\s+\d+", bloque))


def test_contrato_del_json():
    comunas = TEMPORADA["comunas"]
    assert comunas, "el JSON no trae comunas"
    for c in comunas[:20]:
        for campo in ("code", "name", "region", "incendios", "hectareas", "mes_peak", "max_ha"):
            assert campo in c, f"falta {campo} en {c.get('name', c)}"
        assert isinstance(c["incendios"], int) and c["incendios"] >= 0
        assert isinstance(c["hectareas"], (int, float)) and c["hectareas"] >= 0
    assert TEMPORADA["source"].startswith("https://")
    assert TEMPORADA["fetched_at"]

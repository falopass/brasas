"""`web/data/temporada-2526.json`: agregación del CSV de GEPRIF-CONAF (OFI-30).

El fixture es un CSV mínimo con el mismo encabezado real; nunca se toca la red.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "local"))
import build_temporada_2526 as temp  # noqa: E402

HEADERS = ("id,temporada,nombre,estado,num_reg,reg_id,f_inicio,sup_total,"
           "comuna,provincia,region,reg_order")
# Dos incendios en Molina (Maule), uno en Los Ángeles (Biobío) y uno sin comuna conocida.
FIXTURE = "\n".join([
    HEADERS,
    '1,2025,A,Extinguido,1,7,2025-12-08 13:20,"0,60",Molina,Curicó,Maule,9',
    '2,2025,B,Extinguido,2,7,2026-01-10 15:00,"1,40",Molina,Curicó,Maule,9',
    '3,2026,C,Activo,3,8,2026-02-01 10:00,"5,00",Los Angeles,Biobio,Biobío,11',
    '4,2026,D,Extinguido,4,7,2025-12-20 09:00,"2,50",Comuna Inventada,Curicó,Maule,9',
])


def build_fixture(tmp_path: Path) -> dict:
    csv_path = tmp_path / "incendios.csv"
    csv_path.write_text(FIXTURE, encoding="utf-8")
    return temp.build(temp.load_rows(csv_path), "2026-10-19T00:00:00+00:00")


def test_la_suma_regional_cuadra_con_el_total_nacional(tmp_path):
    data = build_fixture(tmp_path)
    suma = round(sum(r["hectareas"] for r in data["regiones"]), 2)
    assert suma == data["totales"]["hectareas"] == 9.5


def test_una_comuna_suma_sus_dos_incendios(tmp_path):
    data = build_fixture(tmp_path)
    molina = next(c for c in data["comunas"] if c["name"] == "Molina")
    assert molina["incendios"] == 2
    assert molina["hectareas"] == 2.0
    assert molina["mes_peak"] == "2026-01"
    assert molina["max_ha"] == 1.4


def test_comuna_desconocida_cae_en_sin_comuna(tmp_path):
    data = build_fixture(tmp_path)
    assert all(s["name"] == "Comuna Inventada" for s in data["sin_comuna"])
    assert data["sin_comuna"][0]["incendios"] == 1
    assert all(c["name"] != "Comuna Inventada" for c in data["comunas"])


def test_el_json_tiene_las_claves_obligatorias(tmp_path):
    data = build_fixture(tmp_path)
    assert data["source"].startswith("https://")
    assert "CONAF" in data["license"]
    assert data["temporada"] == "2025-2026"
    assert data["fetched_at"]
    for r in data["regiones"]:
        assert set(r) == {"name", "incendios", "hectareas", "mes_peak", "comuna_top"}
    for c in data["comunas"]:
        assert set(c) == {"code", "name", "region", "incendios", "hectareas",
                          "mes_peak", "max_ha"}


def test_el_json_versionado_existe_y_es_consistente():
    path = ROOT / "web" / "data" / "temporada-2526.json"
    if not path.exists():
        return  # se genera con scripts/local/build_temporada_2526.py
    data = json.loads(path.read_text())
    assert len(data["regiones"]) == 16
    suma = round(sum(r["hectareas"] for r in data["regiones"]), 2)
    assert suma == data["totales"]["hectareas"]

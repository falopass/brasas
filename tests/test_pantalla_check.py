"""Funciones puras de scripts/local/pantalla_check.py, sin navegador.

El modo municipal (?comunas=a,b&rotar=N) antes pasaba el chequeo sin mirar nada:
expected_comuna solo entendía ?comuna= y con name=None nunca verificaba el nombre
ni la rotación. Estas pruebas fijan el parseo y la resolución contra el índice
comunal, para que el chequeo falle cuando debe y verifique de verdad.
"""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "local"))

import pantalla_check  # noqa: E402

INDEX = json.loads((ROOT / "web" / "data" / "comunas-index.json").read_text(encoding="utf-8"))
URL = "http://127.0.0.1:8000/web/pantalla.html"


@pytest.mark.parametrize(
    ("consulta", "nombres"),
    [
        ("?comunas=7101,13101", ["Talca", "Santiago"]),
        ("?comunas=7101,Talca", ["Talca"]),  # código y nombre son la misma comuna
        ("?comunas=99999", ["99999"]),  # sin calce queda crudo: el chequeo lo marca
    ],
)
def test_expected_comunas_resuelve_dedup_y_desconocida(consulta, nombres):
    assert pantalla_check.expected_comunas(f"{URL}{consulta}", INDEX) == nombres


def test_expected_comuna_por_nombre_y_sin_parametro():
    comuna = pantalla_check.expected_comuna(f"{URL}?comuna=Talca", INDEX)
    assert comuna is not None and comuna["code"] == 7101 and comuna["name"] == "Talca"
    assert pantalla_check.expected_comuna(URL, INDEX) is None
    assert pantalla_check.expected_comuna(f"{URL}?comuna=", INDEX) is None


def test_comunas_pedidas_limpia_vacios_duplicados_y_ausencia():
    url = f"{URL}?comunas=7101,%2013101%20,talca,TALCA,,"
    assert pantalla_check.comunas_pedidas(url) == ["7101", "13101", "talca"]
    assert pantalla_check.comunas_pedidas(URL) == []
    assert pantalla_check.comunas_pedidas(f"{URL}?comuna=Talca") == []


@pytest.mark.parametrize(
    ("consulta", "segundos"),
    [("?rotar=1", 5), ("?rotar=60", 60), ("?rotar=999", 300), ("?rotar=abc", 45), ("?rotar=0", 45), ("", 45)],
)
def test_segundos_pedidos_acotado_al_rango(consulta, segundos):
    assert pantalla_check.segundos_pedidos(f"{URL}{consulta}") == segundos

"""Funciones puras de scripts/local/pantalla_check.py, sin navegador.

El modo municipal (?comunas=a,b&rotar=N) antes pasaba el chequeo sin mirar nada:
expected_comuna solo entendía ?comuna= y con name=None nunca verificaba el nombre
ni la rotación. Estas pruebas fijan el parseo y la resolución contra el índice
comunal, para que el chequeo falle cuando debe y verifique de verdad.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "local"))

import pantalla_check  # noqa: E402

INDEX = json.loads((ROOT / "web" / "data" / "comunas-index.json").read_text(encoding="utf-8"))
URL = "http://127.0.0.1:8000/web/pantalla.html"


def test_expected_comunas_dos_codigos_devuelve_sus_nombres():
    assert pantalla_check.expected_comunas(f"{URL}?comunas=7101,13101", INDEX) == ["Talca", "Santiago"]


def test_expected_comunas_valor_que_no_existe_queda_crudo():
    # El nombre crudo no es un nombre oficial: el chequeo lo detecta y debe fallar.
    assert pantalla_check.expected_comunas(f"{URL}?comunas=99999", INDEX) == ["99999"]
    assert pantalla_check.resolve_comuna(INDEX, "99999") is None


def test_expected_comunas_dedup_por_codigo():
    # «7101» y «Talca» son la misma comuna: la página rota una sola vez por código.
    assert pantalla_check.expected_comunas(f"{URL}?comunas=7101,Talca", INDEX) == ["Talca"]


def test_expected_comuna_nombre_sigue_funcionando():
    comuna = pantalla_check.expected_comuna(f"{URL}?comuna=Talca", INDEX)
    assert comuna is not None
    assert comuna["code"] == 7101 and comuna["name"] == "Talca"


def test_expected_comuna_sin_parametro():
    assert pantalla_check.expected_comuna(URL, INDEX) is None
    assert pantalla_check.expected_comuna(f"{URL}?comuna=", INDEX) is None


def test_comunas_pedidas_limpia_vacios_y_duplicados():
    url = f"{URL}?comunas=7101,%2013101%20,talca,TALCA,,"
    assert pantalla_check.comunas_pedidas(url) == ["7101", "13101", "talca"]


def test_comunas_pedidas_sin_parametro():
    assert pantalla_check.comunas_pedidas(URL) == []
    assert pantalla_check.comunas_pedidas(f"{URL}?comuna=Talca") == []


def test_segundos_pedidos_cae_al_minimo():
    assert pantalla_check.segundos_pedidos(f"{URL}?rotar=1") == 5


def test_segundos_pedidos_bordes_y_default():
    assert pantalla_check.segundos_pedidos(f"{URL}?rotar=60") == 60
    assert pantalla_check.segundos_pedidos(f"{URL}?rotar=999") == 300
    assert pantalla_check.segundos_pedidos(URL) == 45
    assert pantalla_check.segundos_pedidos(f"{URL}?rotar=abc") == 45
    assert pantalla_check.segundos_pedidos(f"{URL}?rotar=0") == 45

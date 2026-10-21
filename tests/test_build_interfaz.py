"""Guarda del generador de `web/data/interfaz.json` (QA-210).

Ejercita la lógica pura de `scripts/local/build_interfaz.py` —la asignación de
comuna de cada registro de la capa GEPRIF y la cobertura declarada— con una
fixture en memoria: sin red ni disco.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from shapely import STRtree
from shapely.geometry import Point, box

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "local"))
import build_interfaz as bi  # noqa: E402


@pytest.fixture
def indice():
    """Dos comunas de juguete: dos cuadrados disjuntos, como el índice real."""
    poligonos = [box(-70.7, -33.5, -70.6, -33.4), box(-70.6, -33.4, -70.5, -33.3)]
    codes = [13101, 13105]
    return {"tree": STRtree(poligonos), "codes": codes, "validos": set(codes)}


def test_dpa_valido_manda_sobre_el_poligono(indice):
    """Un dpa_cod válido gana aunque el punto caiga en otra comuna (borde/simplificación)."""
    code, via, espacial = bi.asignar_comuna(13101, Point(-70.55, -33.35), indice)
    assert (code, via) == (13101, "dpa")
    assert espacial == 13105, "el cruce espacial se reporta igual, para auditar la discrepancia"


def test_dpa_invalido_cae_al_poligono(indice):
    """Un dpa_cod que no está en el índice se asigna por el polígono que contiene el punto."""
    code, via, espacial = bi.asignar_comuna(99999, Point(-70.65, -33.45), indice)
    assert (code, via, espacial) == (13101, "poligono", 13101)


def test_sin_dpa_ni_poligono_devuelve_ninguna(indice):
    """Sin código válido y con el punto fuera de todo polígono: no se inventa la comuna."""
    code, via, espacial = bi.asignar_comuna(None, Point(0, 0), indice)
    assert (code, via, espacial) == (None, "ninguna", None)


def test_cobertura_declara_exactamente_las_comunas_sin_dato():
    res = bi.cobertura([13101, 13105, 5201], {"13101": {"ha_interfaz": 1.0, "pct_comuna": 0.1}})
    assert res == {"con_dato": 1, "total": 3, "sin_dato": [5201, 13105]}


def test_cobertura_completa_no_declara_huecos():
    res = bi.cobertura([13101, 5201], {"5201": {}, "13101": {}})
    assert res == {"con_dato": 2, "total": 2, "sin_dato": []}


def test_cobertura_solo_cuenta_comunas_del_indice():
    """Un código ajeno al índice en el resultado no infla la cobertura."""
    res = bi.cobertura([13101], {"13101": {}, "99999": {}})
    assert res == {"con_dato": 1, "total": 1, "sin_dato": []}

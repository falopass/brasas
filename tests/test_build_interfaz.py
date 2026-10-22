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


@pytest.mark.parametrize(
    ("dpa", "punto", "esperado"),
    [
        # Un dpa_cod válido gana aunque el punto caiga en otra comuna (borde/simplificación);
        # el cruce espacial se reporta igual, para auditar la discrepancia.
        (13101, Point(-70.55, -33.35), (13101, "dpa", 13105)),
        # Un dpa_cod que no está en el índice se asigna por el polígono que contiene el punto.
        (99999, Point(-70.65, -33.45), (13101, "poligono", 13101)),
        # Sin código válido y con el punto fuera de todo polígono: no se inventa la comuna.
        (None, Point(0, 0), (None, "ninguna", None)),
    ],
)
def test_asignar_comuna(indice, dpa, punto, esperado):
    assert bi.asignar_comuna(dpa, punto, indice) == esperado


@pytest.mark.parametrize(
    ("codigos", "datos", "esperado"),
    [
        ([13101, 13105, 5201], {"13101": {"ha_interfaz": 1.0, "pct_comuna": 0.1}}, {"con_dato": 1, "total": 3, "sin_dato": [5201, 13105]}),
        ([13101, 5201], {"5201": {}, "13101": {}}, {"con_dato": 2, "total": 2, "sin_dato": []}),
        # Un código ajeno al índice en el resultado no infla la cobertura.
        ([13101], {"13101": {}, "99999": {}}, {"con_dato": 1, "total": 1, "sin_dato": []}),
    ],
)
def test_cobertura(codigos, datos, esperado):
    assert bi.cobertura(codigos, datos) == esperado

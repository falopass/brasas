"""Variantes de nombre de comuna entre las fuentes oficiales y el territorio BCN.

Las fuentes no siempre usan la grafía del índice territorial (`web/data/comunas-index.json`):
el INE escribe «Marchihue» y «Trehuaco» en la capa del Censo 2024, y CONAF escribe
«Paiguano» y «Llay-Llay» en sus reportes. Este módulo es el único diccionario: los
informes que cruzan el nombre de la fuente con el territorio (`validar_deteccion`,
`calibrar_riesgo`, `build_censo`) llaman a `normalizar`, que aplica la variante y
después pliega con `_fold` de backend/geo.py. Sin ella, esos incendios caen en
«sin calce» y quedan fuera de las tasas por región y del lift por macrozona.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.geo import _fold  # noqa: E402

# Escritura de la fuente → nombre del índice territorial (mismo CUT).
VARIANTES = {
    "MARCHIHUE": "Marchigüe",  # INE, capa COMUNA_DPA_INDICADORES del Censo 2024
    "TREHUACO": "Treguaco",  # INE, capa COMUNA_DPA_INDICADORES del Censo 2024
    "PAIGUANO": "Paihuano",  # CONAF GEPRIF, CSV de la temporada
    "LLAY-LLAY": "Llaillay",  # CONAF GEPRIF, CSV de temporada y capa histórica
}

_VARIANTES = {_fold(origen): _fold(canonical) for origen, canonical in VARIANTES.items()}


def normalizar(nombre: str) -> str:
    """Nombre comparable: la variante conocida si aplica, y después `_fold` de backend/geo.py."""
    base = _fold(nombre or "")
    return _VARIANTES.get(base, base)

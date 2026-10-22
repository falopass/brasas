"""AGUA-06: la lista de consejos de calor se mantiene corta y completa.

El contenido de cada consejo (texto, fuente, URL https de dominio oficial y fecha de
consulta) lo cubre tests/js/calor.test.mjs, que importa el módulo real. Aquí solo se
vigila que la lista no crezca sin una decisión de contenido (QA-207) y que el parser
vea todos los objetos del arreglo.
"""

import re
from pathlib import Path

CALOR = Path(__file__).resolve().parents[1] / "web" / "js" / "calor.js"

_CONTENIDO = CALOR.read_text(encoding="utf-8")
_BLOQUE = re.search(r"CONSEJOS_CALOR\s*=\s*\[(.*?)\];", _CONTENIDO, re.S)
_CONSEJO = re.compile(r"\{\s*text:\s*'([^']+)',\s*source:\s*'([^']+)',\s*url:\s*'([^']+)'\s*\}")

assert _BLOQUE, "calor.js debe exportar CONSEJOS_CALOR como un arreglo"
CONSEJOS = [{"text": m.group(1), "source": m.group(2), "url": m.group(3)} for m in _CONSEJO.finditer(_BLOQUE.group(1))]


def test_hay_entre_dos_y_cinco_consejos():
    """La lista es corta a propósito; crecer es una decisión de contenido (QA-207)."""
    assert 2 <= len(CONSEJOS) <= 5


def test_todo_item_del_arreglo_es_un_consejo_completo():
    """Cada «{» del arreglo abre un consejo con sus tres campos: si falta
    uno, el objeto no calza con el formato y este conteo lo delata."""
    assert _BLOQUE.group(1).count("{") == len(CONSEJOS)

"""VIS-02: atributos de teclado del buscador de comunas.

Lee ``web/js/views/riesgo.js`` y exige que ``#r-search`` declare los atributos
que impiden que el teclado del teléfono ponga mayúscula ni autocorrija los
nombres de comuna, y que Enter se comporte como «buscar».
"""
from __future__ import annotations

import re
from pathlib import Path

RIESGO = Path(__file__).resolve().parents[1] / "web" / "js" / "views" / "riesgo.js"


def test_r_search_declara_los_atributos_del_teclado_movil() -> None:
    texto = RIESGO.read_text(encoding="utf-8")
    etiqueta = re.search(r"<input\b[^>]*id=\"r-search\"[^>]*>", texto)
    assert etiqueta, 'riesgo.js: no se encontró el <input id="r-search">'
    for atributo in (
        'enterkeyhint="search"',
        'autocapitalize="off"',
        'autocorrect="off"',
        'spellcheck="false"',
    ):
        assert atributo in etiqueta.group(0), f"#r-search sin {atributo}"


def test_r_search_abre_con_enter() -> None:
    """Enter corre la misma búsqueda que change: una coincidencia única abre."""
    texto = RIESGO.read_text(encoding="utf-8")
    assert "addEventListener('keydown'" in texto, "#r-search sin listener de Enter"
    assert "e.key === 'Enter'" in texto, "#r-search: el listener no mira Enter"

"""La portada sin JavaScript entrega lo esencial (UX-49): con los scripts
bloqueados no hay mapa, pero sí hay una emergencia. El <noscript> debe
ofrecer los teléfonos tocables, los pasos mínimos y salida a las páginas
que sí funcionan sin scripts (modo liviano y hoja para imprimir)."""

import re

from backend.settings import ROOT

INDEX = ROOT / "web" / "index.html"


def _noscript():
    html = INDEX.read_text(encoding="utf-8")
    bloque = re.search(r"<noscript>(.*?)</noscript>", html, re.S)
    assert bloque, "index.html sin bloque <noscript>"
    return bloque.group(1)


def test_noscript_telefonos_tocables():
    bloque = _noscript()
    for numero in ("130", "132", "131", "133"):
        assert f'href="tel:{numero}"' in bloque, f"noscript sin enlace tel:{numero}"


def test_noscript_salidas_sin_js():
    bloque = _noscript()
    assert 'href="/web/lite.html"' in bloque, "noscript sin enlace a la versión liviana"
    assert 'href="/web/lista.html"' in bloque, "noscript sin enlace a la hoja para imprimir"
    assert "https://senapred.cl/" in bloque, "noscript sin enlace a SENAPRED"


def test_noscript_avisa_que_no_es_oficial():
    assert "no es una alerta oficial" in _noscript()


def test_noscript_sin_scripts():
    """Un <script> dentro de <noscript> jamás se ejecuta: no debe haber ninguno."""
    assert "<script" not in _noscript()

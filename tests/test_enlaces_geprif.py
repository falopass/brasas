"""OFI-20: enlaces a las herramientas oficiales del DEI de CONAF (GEPRIF) en Prepárate.

Guarda mínima: los enlaces deben ser https y abrir en otra pestaña con rel="noopener".
BRASA solo enlaza; no copia ni redistribuye datos de CONAF.
"""

from __future__ import annotations

import re
from pathlib import Path

PREPARATE = Path(__file__).resolve().parents[1] / "web" / "js" / "views" / "preparate.js"


def _html() -> str:
    return PREPARATE.read_text(encoding="utf-8")


def test_dominios_geprif_con_https():
    html = _html()
    assert "https://deigeprif.com/" in html
    assert "https://meteograma.deigeprif.com/" in html


def test_sin_http_inseguro():
    html = _html()
    assert "http://deigeprif" not in html
    assert "http://meteograma.deigeprif" not in html


def test_enlaces_con_noopener():
    html = _html()
    enlaces = re.findall(r'<a href="https://[^"]*deigeprif\.com/"[^>]*>', html)
    assert len(enlaces) == 2
    for tag in enlaces:
        assert 'target="_blank"' in tag
        assert 'rel="noopener"' in tag

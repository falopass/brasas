"""OFI-20: enlaces a las herramientas oficiales del DEI de CONAF (GEPRIF) en Prepárate.

Guarda mínima: los enlaces deben ser https y abrir en otra pestaña con rel="noopener".
BRASA solo enlaza; no copia ni redistribuye datos de CONAF.
"""

from __future__ import annotations

import re
from pathlib import Path

PREPARATE = Path(__file__).resolve().parents[1] / "web" / "js" / "views" / "preparate.js"


def test_enlaces_geprif_https_en_otra_pestana():
    enlaces = re.findall(r'<a href="([^"]*deigeprif\.com/)"([^>]*)>', PREPARATE.read_text(encoding="utf-8"))
    assert [url for url, _ in enlaces] == ["https://deigeprif.com/", "https://meteograma.deigeprif.com/"]
    for url, attrs in enlaces:
        assert url.startswith("https://"), f"enlace inseguro: {url}"
        assert 'target="_blank"' in attrs and 'rel="noopener"' in attrs, f"falta target/rel en {url}"

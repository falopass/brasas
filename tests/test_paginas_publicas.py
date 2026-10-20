"""La tabla de `docs/PAGINAS.md` manda sobre indexación: cada página listada
existe en disco, su `<meta name="robots">` coincide con lo documentado y su
`<title>` no está vacío. Una página nueva no se valida hasta que se
documente; cambiar el robots de una documentada rompe este test."""

import re

import pytest

from backend.settings import ROOT

DOC = ROOT / "docs" / "PAGINAS.md"
FILA = re.compile(r"^\|\s*`(/[^`\s]*)`[^|]*\|[^|]*\|\s*(indexable|noindex)\b", re.M)
NOINDEX_META = re.compile(r'<meta\s+name="robots"\s+content="noindex"')


def _archivo(ruta):
    if ruta == "/":
        return ROOT / "web" / "index.html"
    rel = ruta.lstrip("/")
    return ROOT / rel if (ROOT / rel).is_file() else ROOT / "web" / rel


def _paginas_documentadas():
    return [(ruta, estado) for ruta, estado in FILA.findall(DOC.read_text(encoding="utf-8"))]


def test_inventario_no_vacio():
    """La tabla tiene que listar páginas; si el regex no captura ninguna,
    el documento cambió de formato y este test dejó de proteger nada."""
    assert _paginas_documentadas(), "docs/PAGINAS.md: tabla sin rutas reconocibles"


@pytest.mark.parametrize(
    ("ruta", "estado"),
    _paginas_documentadas(),
    ids=[r for r, _ in _paginas_documentadas()],
)
def test_pagina_documentada(ruta, estado):
    pagina = _archivo(ruta)
    assert pagina.is_file(), f"{ruta}: documentada pero sin archivo en disco"
    html = pagina.read_text(encoding="utf-8")
    title = re.search(r"<title>(.*?)</title>", html)
    assert title and title.group(1).strip(), f"{ruta}: sin <title>"
    if estado == "noindex":
        assert NOINDEX_META.search(html), f"{ruta}: documentada noindex sin meta robots"
    else:
        assert not NOINDEX_META.search(html), f"{ruta}: documentada indexable con meta noindex"

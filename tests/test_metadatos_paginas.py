"""Metadatos sociales de las páginas de utilidad (SEO-06): canonical, Open Graph
y `twitter:card` para que WhatsApp muestre título y descripción al compartirlas.
Solo HTML estático, con `html.parser` de la biblioteca estándar."""

from html.parser import HTMLParser

import pytest

from backend.settings import ROOT

# Página -> og:type que le corresponde.
PAGINAS = {
    "lista.html": "article",
    "plan.html": "article",
    "respuesta.html": "website",
}


class _Head(HTMLParser):
    """Recolecta el canonical y las <meta> con nombre o propiedad."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.metas = {}  # property/name -> content
        self.canonical = ""

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "meta":
            clave = a.get("property") or a.get("name")
            if clave:
                self.metas[clave] = (a.get("content") or "").strip()
        elif tag == "link" and "canonical" in (a.get("rel") or "").split():
            self.canonical = (a.get("href") or "").strip()


def _doc(nombre):
    doc = _Head()
    doc.feed((ROOT / "web" / nombre).read_text(encoding="utf-8"))
    doc.close()
    return doc


@pytest.mark.parametrize("nombre,tipo", PAGINAS.items())
def test_metadatos_sociales(nombre, tipo):
    doc = _doc(nombre)
    assert doc.canonical == f"/web/{nombre}", f"{nombre}: canonical {doc.canonical!r} no apunta a la propia página"
    esperado = {
        "og:type": tipo,
        "og:site_name": "BRASA Chile",
        "og:locale": "es_CL",
        "og:url": doc.canonical,
        "twitter:card": "summary",
    }
    for clave, valor in esperado.items():
        assert doc.metas.get(clave) == valor, f"{nombre}: {clave} = {doc.metas.get(clave)!r} (se espera {valor!r})"
    for clave in ("og:title", "og:description"):
        assert doc.metas.get(clave), f"{nombre}: falta {clave}"
    assert len(doc.metas["og:description"]) <= 160, f"{nombre}: og:description pasa de 160 caracteres"

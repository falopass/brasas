"""Metadatos sociales de las páginas públicas (SEO-06, ICON-E-01): canonical y
`og:url` absolutas del host público, Open Graph/Twitter con imagen absoluta
1200×630 PNG, alt de la imagen y `summary_large_image`, para que WhatsApp y las
redes muestren la tarjeta correcta al compartirlas. `focos.html` lleva su propia
portada (`og-focos.png`); el resto usa la portada de marca (`og.png`).

`admin.html` queda fuera a propósito: es una página privada y no debe declarar
etiquetas sociales (lo vigila tests/test_iconos_enlaces.py).

Solo HTML estático, con `html.parser` de la biblioteca estándar."""

from html.parser import HTMLParser

import pytest

from backend.settings import ROOT

# Host público: el mismo PUBLIC_BASE_URL que usa backend/routes/paginas_comuna.py.
PUBLIC_BASE = "https://brasa-chile.ddiegosebastianbb.workers.dev"
OG_PORTADA = f"{PUBLIC_BASE}/web/icons/og.png"
OG_FOCOS = f"{PUBLIC_BASE}/web/icons/og-focos.png"

# Página -> (og:type que le corresponde, su imagen OG).
PAGINAS = {
    "index.html": ("website", OG_PORTADA),
    "focos.html": ("website", OG_FOCOS),
    "lista.html": ("article", OG_PORTADA),
    "plan.html": ("article", OG_PORTADA),
    "respuesta.html": ("website", OG_PORTADA),
    "colegios.html": ("article", OG_PORTADA),
    "preguntas.html": ("website", OG_PORTADA),
    "datos.html": ("website", OG_PORTADA),
    "lite.html": ("website", OG_PORTADA),
    "estado.html": ("website", OG_PORTADA),
    "pantalla.html": ("website", OG_PORTADA),
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


def _canon_esperado(nombre):
    return f"{PUBLIC_BASE}/" if nombre == "index.html" else f"{PUBLIC_BASE}/web/{nombre}"


@pytest.mark.parametrize("nombre,tipo,imagen", [(n, t, i) for n, (t, i) in PAGINAS.items()])
def test_metadatos_sociales(nombre, tipo, imagen):
    doc = _doc(nombre)
    canon = _canon_esperado(nombre)
    assert doc.canonical == canon, f"{nombre}: canonical {doc.canonical!r} no es la URL absoluta {canon!r}"
    esperado = {
        "og:type": tipo,
        "og:site_name": "BRASA Chile",
        "og:locale": "es_CL",
        "og:url": canon,
        "og:image": imagen,
        "og:image:width": "1200",
        "og:image:height": "630",
        "og:image:type": "image/png",
        "twitter:card": "summary_large_image",
    }
    for clave, valor in esperado.items():
        assert doc.metas.get(clave) == valor, f"{nombre}: {clave} = {doc.metas.get(clave)!r} (se espera {valor!r})"
    for clave in ("og:title", "og:description", "og:image:alt"):
        assert doc.metas.get(clave), f"{nombre}: falta {clave}"
    assert len(doc.metas["og:description"]) <= 160, f"{nombre}: og:description pasa de 160 caracteres"

"""Guarda de los enlaces a fuentes oficiales citadas en el contenido (QA-57).

La regla de producto es «siempre mostrar la fuente»: estos enlaces se le
muestran a la gente en Prepárate y en docs/FUENTES.md. Esta guarda es
estática (sin red): falla si una URL deja de ser https, si su dominio no
está en la lista blanca de instituciones conocidas, o si la misma URL
aparece citada con dos textos distintos. Si aparece un dominio nuevo,
agregarlo a DOMINIOS_OFICIALES con un comentario de por qué es oficial.
"""

import re
from urllib.parse import urlparse

from backend.settings import ROOT

PREPARATE = ROOT / "web" / "js" / "views" / "preparate.js"
FUENTES = ROOT / "docs" / "FUENTES.md"

# Dominios de instituciones oficiales (o infraestructura pública acordada).
# El host debe ser el dominio o un subdominio de él.
DOMINIOS_OFICIALES = (
    "conaf.cl",  # Corporación Nacional Forestal (Chile)
    "conafprevencionincendios.cl",  # sitio de prevención de CONAF
    "senapred.cl",  # Servicio Nacional de Prevención y Respuesta ante Desastres
    "senapred.gob.cl",  # biblioteca digital de SENAPRED
    "minsal.cl",  # Ministerio de Salud (sitio degreyd.minsal.cl)
    "dmc.gob.cl",  # Dirección Meteorológica de Chile
    "meteo.cl",  # MeteoChile / DMC
    "gob.cl",  # plataforma única del Estado de Chile
    "noaa.gov",  # NOAA (EE. UU.): GOES, FIRMS referenciadas
    "nasa.gov",  # NASA FIRMS
    "openstreetmap.org",  # capa base y puntos de encuentro
)

_PAR_RE = re.compile(r"\[\s*'([^']*)'\s*,\s*'([^']*)'\s*\]")


def _pares_src():
    """Extrae (texto, url) del objeto SRC de preparate.js."""
    js = PREPARATE.read_text(encoding="utf-8")
    m = re.search(r"const SRC = \{(.*?)\};", js, re.S)
    assert m, "no se encontró el objeto SRC en preparate.js"
    return _PAR_RE.findall(m.group(1))


def test_src_tiene_enlaces():
    pares = _pares_src()
    assert len(pares) >= 8, f"se esperaban las fuentes de SRC, se extrajeron {len(pares)}"


def test_urls_https_y_dominio_oficial():
    pares = _pares_src()
    for texto, url in pares:
        assert url.strip(), f"URL vacía en «{texto}»"
        parsed = urlparse(url)
        assert parsed.scheme == "https", f"«{texto}» no es https: {url}"
        host = parsed.hostname or ""
        assert host, f"«{texto}» sin host: {url}"
        assert any(host == d or host.endswith("." + d) for d in DOMINIOS_OFICIALES), (
            f"«{texto}» apunta a un dominio no registrado: {host}. "
            "Si es una institución oficial, agrégala a DOMINIOS_OFICIALES con un comentario."
        )


def test_sin_duplicados_contradictorios():
    vistos = {}
    for texto, url in _pares_src():
        if url in vistos:
            assert vistos[url] == texto, f"misma URL con dos textos: «{vistos[url]}» y «{texto}» ({url})"
        vistos[url] = texto


def test_fuentes_md_sin_enlaces_http():
    malas = [(n, linea.strip()) for n, linea in enumerate(FUENTES.read_text(encoding="utf-8").splitlines(), 1) if "http://" in linea]
    assert not malas, "docs/FUENTES.md tiene enlaces http:// en: " + "; ".join(f"línea {n}: {l}" for n, l in malas)

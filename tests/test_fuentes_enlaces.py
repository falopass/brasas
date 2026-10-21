"""Guarda de los enlaces a fuentes oficiales citadas en el contenido (QA-57).

La regla de producto es «siempre mostrar la fuente»: estos enlaces se le
muestran a la gente en Prepárate, en «¿Qué hago si…?», en los consejos de
calor y en docs/FUENTES.md. Esta guarda es estática (sin red): falla si una
URL deja de ser https, si su dominio no está en la lista blanca de
instituciones conocidas, o si la misma URL aparece citada con dos textos
distintos. Si aparece un dominio nuevo, agregarlo a DOMINIOS_OFICIALES con
un comentario de por qué es oficial.
"""

import re
from urllib.parse import urlparse

import pytest

from backend.settings import ROOT

PREPARATE = ROOT / "web" / "js" / "views" / "preparate.js"
QUEHAGO = ROOT / "web" / "js" / "views" / "quehago.js"
CALOR = ROOT / "web" / "js" / "calor.js"
FUENTES = ROOT / "docs" / "FUENTES.md"

# Dominios de instituciones oficiales (o infraestructura pública acordada).
# El host debe ser el dominio o un subdominio de él.
DOMINIOS_OFICIALES = (
    "conaf.cl",  # Corporación Nacional Forestal (Chile)
    "conafprevencionincendios.cl",  # sitio de prevención de CONAF
    "senapred.cl",  # Servicio Nacional de Prevención y Respuesta ante Desastres
    "senapred.gob.cl",  # biblioteca digital de SENAPRED
    "minsal.cl",  # Ministerio de Salud (sitio degreyd.minsal.cl)
    "senadis.gob.cl",  # Servicio Nacional de la Discapacidad (guía de emergencia)
    "dmc.gob.cl",  # Dirección Meteorológica de Chile
    "meteo.cl",  # MeteoChile / DMC
    "gob.cl",  # plataforma única del Estado de Chile
    "noaa.gov",  # NOAA (EE. UU.): GOES, FIRMS referenciadas
    "nasa.gov",  # NASA FIRMS
    "openstreetmap.org",  # capa base y puntos de encuentro
)

_PAR_RE = re.compile(r"\[\s*'([^']*)'\s*,\s*'([^']*)'\s*\]")
_SRC_RE = re.compile(r"const SRC = \{(.*?)\};", re.S)
_SOURCES_RE = re.compile(r"sources:\s*\[((?:[^\[\]]|\[[^\]]*\])*)\]")
_CALOR_RE = re.compile(r"CONSEJOS_CALOR\s*=\s*\[(.*?)\];", re.S)
_CALOR_PAR_RE = re.compile(r"source:\s*'([^']*)'\s*,\s*url:\s*'([^']*)'")


def pares_de(archivo, patron, par=_PAR_RE):
    """Extrae (texto, url) de cada bloque de fuentes del archivo que calce con `patron`."""
    bloques = patron.findall(archivo.read_text(encoding="utf-8"))
    assert bloques, f"no se encontraron fuentes en {archivo.name}"
    return [encontrado for bloque in bloques for encontrado in par.findall(bloque)]


def _pares_src():
    """Extrae (texto, url) del objeto SRC de preparate.js."""
    return pares_de(PREPARATE, _SRC_RE)


def _pares_quehago():
    """Extrae (texto, url) de cada `sources: [...]` de quehago.js."""
    return pares_de(QUEHAGO, _SOURCES_RE)


def _pares_calor():
    """Extrae (fuente, url) de CONSEJOS_CALOR; el `text` del consejo no es un enlace."""
    return pares_de(CALOR, _CALOR_RE, _CALOR_PAR_RE)


def _url_oficial(texto, url, archivo):
    assert url.strip(), f"URL vacía en «{texto}» ({archivo.name})"
    parsed = urlparse(url)
    assert parsed.scheme == "https", f"«{texto}» no es https en {archivo.name}: {url}"
    host = parsed.hostname or ""
    assert host, f"«{texto}» sin host en {archivo.name}: {url}"
    assert any(host == d or host.endswith("." + d) for d in DOMINIOS_OFICIALES), (
        f"«{texto}» apunta a un dominio no registrado en {archivo.name}: {host}. "
        "Si es una institución oficial, agrégala a DOMINIOS_OFICIALES con un comentario."
    )


def _sin_duplicados(pares, archivo):
    vistos = {}
    for texto, url in pares:
        if url in vistos:
            assert vistos[url] == texto, f"misma URL con dos textos en {archivo.name}: «{vistos[url]}» y «{texto}» ({url})"
        vistos[url] = texto


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


def test_quehago_tiene_enlaces():
    pares = _pares_quehago()
    assert len(pares) >= 8, f"se esperaban las fuentes de quehago.js, se extrajeron {len(pares)}"


def test_calor_tiene_enlaces():
    pares = _pares_calor()
    assert len(pares) >= 3, f"se esperaban los consejos de calor.js, se extrajeron {len(pares)}"


def test_quehago_urls_https_y_dominio_oficial():
    for texto, url in _pares_quehago():
        _url_oficial(texto, url, QUEHAGO)


def test_calor_urls_https_y_dominio_oficial():
    for texto, url in _pares_calor():
        _url_oficial(texto, url, CALOR)


def test_quehago_sin_duplicados_contradictorios():
    _sin_duplicados(_pares_quehago(), QUEHAGO)


def test_calor_sin_duplicados_contradictorios():
    _sin_duplicados(_pares_calor(), CALOR)


def test_fuentes_md_sin_enlaces_http():
    malas = [(n, linea.strip()) for n, linea in enumerate(FUENTES.read_text(encoding="utf-8").splitlines(), 1) if "http://" in linea]
    assert not malas, "docs/FUENTES.md tiene enlaces http:// en: " + "; ".join(f"línea {n}: {l}" for n, l in malas)


@pytest.mark.parametrize(
    "url",
    ["http://senapred.cl/alertas/", "https://senapred-inventado.cl/alertas/", ""],
    ids=["http", "dominio-inventado", "vacia"],
)
def test_la_guarda_rechaza_un_enlace_invalido(url):
    """El propio guard tiene que fallar con http://, con un dominio fuera de la lista y con una URL vacía."""
    with pytest.raises(AssertionError):
        _url_oficial("Prueba", url, QUEHAGO)

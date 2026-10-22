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

# Los archivos JS usan comillas simples; la guarda tolera también dobles.
_PAR_RE = re.compile(r"""\[\s*['"]([^'"]*)['"]\s*,\s*['"]([^'"]*)['"]\s*\]""")
_SRC_RE = re.compile(r"const SRC = \{(.*?)\};", re.S)
_SOURCES_RE = re.compile(r"sources:\s*\[((?:[^\[\]]|\[[^\]]*\])*)\]")
_CALOR_RE = re.compile(r"CONSEJOS_CALOR\s*=\s*\[(.*?)\];", re.S)
_CALOR_PAR_RE = re.compile(r"""source:\s*['"]([^'"]*)['"]\s*,\s*url:\s*['"]([^'"]*)['"]""")


def pares_de(archivo, patron, par=_PAR_RE):
    """Extrae (texto, url, linea) de cada bloque de fuentes del archivo que calce con `patron`."""
    texto = archivo.read_text(encoding="utf-8")
    bloques = list(patron.finditer(texto))
    assert bloques, f"no se encontraron fuentes en {archivo.name}"
    pares = []
    for bloque in bloques:
        base = bloque.start(1)
        for par_m in par.finditer(bloque.group(1)):
            linea = texto.count("\n", 0, base + par_m.start()) + 1
            pares.append((par_m.group(1), par_m.group(2), linea))
    return pares


def _pares_src():
    """Extrae (texto, url, linea) del objeto SRC de preparate.js."""
    return pares_de(PREPARATE, _SRC_RE)


def _pares_quehago():
    """Extrae (texto, url, linea) de cada `sources: [...]` de quehago.js."""
    return pares_de(QUEHAGO, _SOURCES_RE)


def _pares_calor():
    """Extrae (fuente, url, linea) de CONSEJOS_CALOR; el `text` del consejo no es un enlace."""
    return pares_de(CALOR, _CALOR_RE, _CALOR_PAR_RE)


def _url_oficial(texto, url, archivo, linea=0):
    donde = f"{archivo.name}:{linea}" if linea else archivo.name
    assert url.strip(), f"URL vacía en «{texto}» ({donde})"
    parsed = urlparse(url)
    assert parsed.scheme == "https", f"«{texto}» no es https en {donde}: {url}"
    host = parsed.hostname or ""
    assert host, f"«{texto}» sin host en {donde}: {url}"
    assert any(host == d or host.endswith("." + d) for d in DOMINIOS_OFICIALES), (
        f"«{texto}» apunta a un dominio no registrado en {donde}: {host}. "
        "Si es una institución oficial, agrégala a DOMINIOS_OFICIALES con un comentario."
    )


def _sin_duplicados(pares, archivo):
    vistos = {}
    for texto, url, linea in pares:
        if url in vistos:
            assert vistos[url] == texto, f"misma URL con dos textos en {archivo.name}:{linea}: «{vistos[url]}» y «{texto}» ({url})"
        vistos[url] = texto


@pytest.mark.parametrize(
    ("archivo", "pares", "minimo"),
    [(PREPARATE, _pares_src, 8), (QUEHAGO, _pares_quehago, 10), (CALOR, _pares_calor, 3)],
    ids=["preparate", "quehago", "calor"],
)
def test_fuentes_https_dominio_oficial_y_sin_duplicados(archivo, pares, minimo):
    extraidos = pares()
    assert len(extraidos) >= minimo, f"se esperaban al menos {minimo} fuentes en {archivo.name}, se extrajeron {len(extraidos)}"
    for texto, url, linea in extraidos:
        _url_oficial(texto, url, archivo, linea)
    _sin_duplicados(extraidos, archivo)


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

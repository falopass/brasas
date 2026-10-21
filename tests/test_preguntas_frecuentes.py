"""La página de preguntas frecuentes (CONT-18) explica el producto en palabras
de vecino: qué es un punto de calor, qué significan los estados y colores, qué
capas tiene el mapa y de dónde salen los datos. Es pública, estática, sin
JavaScript, y cada respuesta cita el archivo del que sale la regla."""

import json
import re

from backend.main import app
from backend.settings import ROOT

PAGINA = ROOT / "web" / "preguntas.html"
VISTAS = ROOT / "web" / "js" / "views"
MAPA = ROOT / "web" / "js" / "views" / "mapa.js"
SECCION = re.compile(r"<section\b[^>]*>(.*?)</section>", re.S)
H2 = re.compile(r"<h2\b[^>]*>(.*?)</h2>", re.S)
LDJSON = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
HREF = re.compile(r'<a\b[^>]*\bhref\s*=\s*["\']([^"\']+)["\']', re.I)
COMENTARIO = re.compile(r"<!--(.*?)-->\s*<section\b", re.S)
FUENTE = re.compile(r"[\w./-]+\.(?:py|js|md|html):\d+(?:-\d+)?")
LAYERS = re.compile(r"const\s+layers\s*=\s*\{(.*?)\}", re.S)
CLAVE = re.compile(r"(\w+)\s*:")

# La FAQ habla en palabras de vecino, no con las claves del código: cada clave
# del objeto `layers` de mapa.js tiene su nombre visible en la sección #capas.
NOMBRE_VISIBLE = {
    "focos": "focos",
    "incendios": "incendios",
    "risk": "peligro",
    "rain": "lluvia",
    "reports": "avisos",
    "places": "lugares",
    "hulls": "huella",
    "lightning": "rayos",
    "aire": "humo",
    "scars": "cicatrices",
}


def _html() -> str:
    return PAGINA.read_text(encoding="utf-8")


def _texto(fragmento: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", fragmento)).strip()


def _texto_plano(fragmento: str) -> str:
    # Como queda en el ld+json: el espacio que deja la etiqueta borrada no separa la puntuación.
    return re.sub(r" ([,.;:!?])", r"\1", _texto(fragmento))


def _secciones() -> list[str]:
    return SECCION.findall(_html())


def _rutas_api() -> set[str]:
    return set(app.openapi()["paths"])


def test_metadatos_y_sin_scripts():
    html = _html()
    assert '<html lang="es"' in html
    assert re.search(r'<meta\s+name="viewport"', html)
    assert re.search(r'<meta\s+name="description"\s+content="\S', html)
    assert '<link rel="canonical" href="/web/preguntas.html">' in html
    assert "/web/css/app.css" in html
    assert "<script" not in LDJSON.sub("", html).lower()


def test_entre_diez_y_doce_preguntas():
    preguntas = H2.findall(_html())
    assert 10 <= len(preguntas) <= 12, f"se esperaban entre 10 y 12 preguntas, hay {len(preguntas)}"
    for pregunta in preguntas:
        assert "?" in _texto(pregunta), f"el encabezado no es una pregunta: {pregunta!r}"


def test_cada_respuesta_tiene_frase_y_enlace():
    for i, seccion in enumerate(_secciones(), 1):
        partes = H2.split(seccion, maxsplit=1)
        assert len(partes) == 3, f"la sección {i} no tiene exactamente un <h2>"
        respuesta = _texto(partes[2])
        assert len(respuesta.split()) >= 5 and re.search(r"[.!?]", respuesta), f"la sección {i} no responde con una frase"
        assert HREF.search(partes[2]), f"la sección {i} no tiene ningún enlace"


def test_enlaces_internos_existen():
    rutas_api = _rutas_api()
    vistas = "\n".join(p.read_text(encoding="utf-8") for p in VISTAS.glob("*.js"))
    for href in HREF.findall(_html()):
        if href.startswith("/web/"):
            assert (ROOT / href.lstrip("/")).is_file(), f"archivo inexistente: {href}"
        elif href.startswith("/api/"):
            assert href.split("?")[0].rstrip("/") in rutas_api, f"ruta inexistente: {href}"
        elif "#/" in href:
            vista = href.split("#/", 1)[1].split("?")[0].split("/")[0]
            assert re.search(rf"\bid:\s*['\"]{re.escape(vista)}['\"]", vistas), f"vista inexistente: {href}"


def test_indice_de_anclas_al_principio():
    html = _html()
    indice = html.split("<h1", 1)[1].split("</nav>", 1)[0]
    anclas = re.findall(r'href="#([^"]+)"', indice)
    ids = re.findall(r"<section\b[^>]*\bid=([^\s>]+)", html)
    assert anclas == ids, f"el índice no lista cada pregunta una sola vez y en orden: anclas={anclas}, secciones={ids}"


def test_primera_respuesta_nombra_a_senapred():
    primera = _secciones()[0]
    respuesta = _texto(H2.split(primera, maxsplit=1)[2])
    assert "SENAPRED" in respuesta


def test_cada_pregunta_cita_su_fuente():
    bloques = COMENTARIO.findall(_html())
    assert len(bloques) == len(_secciones()), "cada sección necesita su comentario con el archivo de origen"
    for i, bloque in enumerate(bloques, 1):
        assert FUENTE.search(bloque), f"la sección {i} no cita un archivo con línea"


def test_datos_estructurados_faqpage():
    """SEO-01: un FAQPage con una Question por cada <h2> de la página; el
    name es el texto visible del encabezado y el Answer el de la sección."""
    bloques = LDJSON.findall(_html())
    assert len(bloques) == 1, "la página necesita exactamente un bloque ld+json"
    datos = json.loads(bloques[0])
    assert datos["@context"] == "https://schema.org"
    assert datos["@type"] == "FAQPage"
    entidades = datos["mainEntity"]
    assert len(entidades) == len(_secciones()), "una Question por sección, ni una más ni una menos"
    for i, (entidad, seccion) in enumerate(zip(entidades, _secciones()), 1):
        assert entidad["@type"] == "Question", f"mainEntity {i} no es Question"
        partes = H2.split(seccion, maxsplit=1)
        assert entidad["name"] == _texto_plano(partes[1]), f"el name de la Question {i} no es el texto visible de su <h2>"
        respuesta = entidad["acceptedAnswer"]
        assert respuesta["@type"] == "Answer", f"la Question {i} no tiene acceptedAnswer Answer"
        assert respuesta["text"] == _texto_plano(partes[2]), f"el Answer {i} no reproduce el texto visible de la sección"
        assert "<" not in respuesta["text"] and "&" not in respuesta["text"], f"el Answer {i} lleva HTML"


def test_telefonos_y_descargo():
    html = _html()
    for telefono in ("tel:130", "tel:132"):
        assert telefono in html
    assert "no reemplaza a la autoridad" in html


def _claves_layers(fuente_mapa: str) -> list[str]:
    """Claves del objeto `layers` de web/js/views/mapa.js (texto, sin ejecutar JS)."""
    match = LAYERS.search(fuente_mapa)
    assert match, "no se encontró el objeto layers en web/js/views/mapa.js"
    return CLAVE.findall(match.group(1))


def _texto_capas() -> str:
    for seccion in SECCION.finditer(_html()):
        if "id=capas" in seccion.group(0):
            return _texto(seccion.group(1)).lower()
    raise AssertionError("no se encontró la sección #capas")


def capas_sin_explicar(fuente_mapa: str, texto_capas: str) -> list[str]:
    """Claves de `layers` que la sección #capas no menciona. Una clave nueva
    sin entrada en NOMBRE_VISIBLE también falta: hay que explicarla en la FAQ."""
    faltantes = []
    for clave in _claves_layers(fuente_mapa):
        nombre = NOMBRE_VISIBLE.get(clave)
        if nombre is None or nombre not in texto_capas:
            faltantes.append(clave)
    return faltantes


def test_cada_capa_del_mapa_esta_explicada():
    faltantes = capas_sin_explicar(MAPA.read_text(encoding="utf-8"), _texto_capas())
    assert not faltantes, f"capas de mapa.js sin explicar en preguntas.html: {faltantes}"


def test_guarda_detecta_capa_sin_explicar():
    """Caso mutado en memoria: si la sección pierde una capa, la guarda nombra cuál falta."""
    texto = _texto_capas().replace("rayos", "")
    assert "lightning" in capas_sin_explicar(MAPA.read_text(encoding="utf-8"), texto)

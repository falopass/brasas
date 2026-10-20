"""La página de preguntas frecuentes (CONT-16) explica las reglas reales de los
avisos: es pública, estática, sin JavaScript (la CSP prohíbe scripts en línea y
la página no los necesita), y cada respuesta cita el archivo del que sale la
regla para que el próximo cambio de código avise qué revisar."""

import re

from backend.settings import ROOT

PAGINA = ROOT / "web" / "preguntas.html"
FUENTES = ("alerts.py", "freshness.py", "incidents.py")


def _html() -> str:
    return PAGINA.read_text(encoding="utf-8")


def _secciones() -> list[str]:
    return re.findall(r"<section>(.*?)</section>", _html(), re.S)


def test_preguntas_metadatos_y_sin_scripts():
    html = _html()
    assert '<html lang="es"' in html
    assert re.search(r'<meta\s+name="viewport"', html)
    assert re.search(r'<meta\s+name="description"\s+content="\S', html)
    assert "<script" not in html.lower()


def test_preguntas_son_cinco_y_citan_su_fuente():
    secciones = _secciones()
    assert len(secciones) == 5, f"se esperaban 5 preguntas, hay {len(secciones)}"
    for i, seccion in enumerate(secciones, 1):
        assert re.search(r"<h2>.*\?", seccion), f"la sección {i} no lleva una pregunta"
    # Cada respuesta va precedida de un comentario con el archivo que la funda.
    bloques = re.findall(r"<!--(.*?)-->\s*<section>", _html(), re.S)
    assert len(bloques) == 5
    for i, bloque in enumerate(bloques, 1):
        assert any(f in bloque for f in FUENTES), f"la sección {i} no cita su archivo de origen ({', '.join(FUENTES)})"


def test_preguntas_telefonos_y_descargo():
    html = _html()
    for telefono in ("tel:130", "tel:132"):
        assert telefono in html
    assert "no reemplaza a la autoridad" in html

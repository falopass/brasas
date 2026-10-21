"""La portada avisa cuando la app no alcanza a arrancar (PORTADA-02).

El <noscript> de UX-49 solo cubre a quien tiene JavaScript desactivado. Si el
JavaScript está activo pero falla —el módulo app.js no llega por un 2G rural,
el navegador viejo no lo entiende o un error temprano corta el arranque— la
persona veía una pantalla muda justo cuando quizá busca qué hacer. El bloque
#arranque-fallido queda oculto en el HTML y un guion en línea (clásico, no
módulo, para correr aunque los módulos no carguen) lo muestra si a los 15 s
la app no pintó; repite el chequeo a los 30 s por si el primero llegó antes
de tiempo.
"""

import re

from backend.settings import ROOT

INDEX = ROOT / "web" / "index.html"


def _html() -> str:
    return INDEX.read_text(encoding="utf-8")


def _bloque() -> str:
    match = re.search(
        r'<div\b[^>]*\bid="arranque-fallido"[^>]*>(.*?)</div>\s*(?=<script)',
        _html(),
        re.S,
    )
    assert match, 'index.html sin <div id="arranque-fallido">'
    return match.group(0)


def _script_vigia() -> str:
    """El guion que vigila el arranque: el <script> en línea que menciona el bloque."""
    html_sin_noscript = re.sub(r"<noscript>.*?</noscript>", "", _html(), flags=re.S)
    guiones = re.findall(r"<script\b[^>]*>(.*?)</script>", html_sin_noscript, re.S | re.I)
    vigias = [g for g in guiones if "arranque-fallido" in g]
    assert vigias, "index.html sin guion en línea que vigile #arranque-fallido"
    return vigias[0]


def test_bloque_existe_y_nace_oculto():
    tag = re.search(r'<div\b[^>]*\bid="arranque-fallido"[^>]*>', _html())
    assert tag, 'index.html sin <div id="arranque-fallido">'
    assert "hidden" in tag.group(0), "el bloque debe nacer oculto (hidden)"


def test_bloque_telefonos_tocables():
    bloque = _bloque()
    for numero in ("130", "132", "131", "133"):
        assert f'href="tel:{numero}"' in bloque, f"bloque sin enlace tel:{numero}"


def test_bloque_salidas_sin_app():
    bloque = _bloque()
    assert 'href="/web/lite.html"' in bloque, "bloque sin enlace a la versión liviana"
    assert 'href="/web/lista.html"' in bloque, "bloque sin enlace a la hoja para imprimir"
    assert "https://senapred.cl/" in bloque, "bloque sin enlace a SENAPRED"


def test_bloque_avisa_que_no_es_oficial():
    assert "no es una alerta oficial" in _bloque()


def test_bloque_ofrece_reintentar():
    assert "Reintentar" in _bloque(), "bloque sin botón Reintentar"
    assert "location.reload" in _script_vigia(), "el guion no recarga al reintentar"


def test_vigia_es_script_clasico_fuera_de_noscript():
    """El guion debe correr aunque los módulos no carguen: nada de type="module"
    ni de import, y fuera del <noscript> (que jamás ejecuta scripts)."""
    html = _html()
    noscript = re.search(r"<noscript>(.*?)</noscript>", html, re.S)
    assert noscript and "arranque-fallido" not in noscript.group(1), "el vigía no puede vivir dentro de <noscript>"
    vigias = [
        (tag, cuerpo) for tag, cuerpo in re.findall(r"(<script\b[^>]*>)(.*?)</script>", html, re.S | re.I) if "arranque-fallido" in cuerpo
    ]
    assert vigias, "index.html sin guion en línea que vigile #arranque-fallido"
    for tag, cuerpo in vigias:
        assert 'type="module"' not in tag and "type='module'" not in tag, (
            'el vigía no puede ser type="module": si el módulo no carga, nadie vigila'
        )
        assert not re.search(r"(?<![-\w])src\s*=", tag), "el vigía debe ser en línea, sin src"
        assert not re.search(r"\bimport\b", cuerpo), "el vigía no puede usar import"


def test_vigia_chequea_a_los_15_y_30_segundos():
    cuerpo = _script_vigia()
    assert "15000" in cuerpo, "falta el chequeo a los 15 s"
    assert "30000" in cuerpo, "falta el segundo chequeo a los 30 s"
    assert "view" in cuerpo and "nav" in cuerpo, "el vigía debe comprobar si la app pintó: #view o #nav con hijos"

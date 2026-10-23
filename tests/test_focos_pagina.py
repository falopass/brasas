"""FOCOS-01: la lista en texto de focos e incendios activos (/focos.html).

La página existe para quien no puede abrir el mapa (2G, datos lentos, lector de
pantalla): consulta solo GET públicos, marca «confirmado» solo vía CONAF y nunca
dice «no hay fuego» cuando una fuente no pudo consultarse. Solo biblioteca
estándar y el cliente de pruebas, como tests/test_paginas_estaticas.py.
"""

import re

from backend.settings import ROOT

FOCOS = ROOT / "web" / "focos.html"
FOCOS_JS = ROOT / "web" / "js" / "focos.js"


def test_focos_se_sirve_en_raiz_y_bajo_web(make_client):
    """El backend la sirve en la raíz como /lista.html; el estático bajo /web/ ya la cubre."""
    with make_client() as client:
        for ruta in ("/focos.html", "/web/focos.html"):
            r = client.get(ruta)
            assert r.status_code == 200, f"{ruta} respondió {r.status_code}"
            assert "Focos e incendios activos en Chile" in r.text


def test_focos_estructura_minima():
    html = FOCOS.read_text(encoding="utf-8")
    assert re.search(r'<html[^>]*lang="es"', html), "focos.html: <html> sin lang"
    assert len(re.findall(r"<h1\b", html)) == 1, "focos.html: debe tener un solo <h1>"
    assert "<main" in html, "focos.html: falta <main>"
    assert re.search(r'<meta\s+name="robots"\s+content="noindex"', html), "focos.html: falta robots noindex"


def test_focos_cita_emergencias_y_no_es_oficial():
    """El descargo de responsabilidad y los teléfonos son estáticos: llegan aunque
    el módulo no cargue o la API esté caída."""
    html = FOCOS.read_text(encoding="utf-8")
    assert "no es una alerta oficial" in html and "SENAPRED" in html
    assert 'href="tel:130"' in html and 'href="tel:132"' in html


def test_focos_sin_scripts_en_linea_ni_hosts_externos():
    """Misma regla que lista.html (AUTOCONTENIDAS en test_estaticas_guardas.py):
    ningún <script> con cuerpo y ningún src/href/action a otro host; los <a>
    externos no se cuentan porque el navegador no los descarga."""
    html = FOCOS.read_text(encoding="utf-8")
    for cuerpo in re.findall(r"<script[^>]*>(.*?)</script>", html, re.S):
        assert not cuerpo.strip(), "focos.html: script en línea (la CSP del repo no los permite)"
    for tag, _attr, ref in re.findall(r"<(\w+)[^>]*?\b(src|href|action)\s*=\s*[\"']([^\"']+)", html):
        if tag.lower() == "a":
            continue
        assert not re.match(r"(?:https?:)?//", ref), f"focos.html: host externo {ref}"
    assert 'src="/web/js/focos.js"' in html, "focos.html: no carga su módulo"


def test_focos_js_consulta_solo_los_get_publicos_con_tope():
    js = FOCOS_JS.read_text(encoding="utf-8")
    assert "/api/incidents?hours=24" in js, "focos.js: no consulta /api/incidents?hours=24"
    assert "/api/official-fires" in js, "focos.js: no consulta /api/official-fires"
    assert "AbortController" in js and re.search(r"8_?000", js), "focos.js: falta el AbortController con tope de 8 s"


def test_focos_js_formatea_en_hora_de_chile():
    js = FOCOS_JS.read_text(encoding="utf-8")
    assert "America/Santiago" in js, "focos.js: la hora debe formatearse en America/Santiago"


def test_focos_js_escapa_lo_interpolado_como_texto():
    """«Talca <b>» de CONAF se muestra tal cual: la tabla interpola solo por
    textContent, que nunca interpreta marcado. La guarda es estructural: en
    focos.js no existe ningún sink de HTML donde el <b> pudiera volverse etiqueta."""
    js = FOCOS_JS.read_text(encoding="utf-8")
    assert "textContent" in js, "focos.js: debe insertar los datos con textContent"
    for sink in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write"):
        assert sink not in js, f"focos.js usa {sink}: «Talca <b>» se interpretaría como HTML"


def test_focos_tabla_accesible_en_el_html():
    """La tabla nace con <caption> y <th scope="col"> para que un lector de
    pantalla la recorra; las filas las arma focos.js."""
    html = FOCOS.read_text(encoding="utf-8")
    assert re.search(r'<table[^>]*class="[^"]*tabla-focos', html), "focos.html: falta la tabla .tabla-focos"
    assert "<caption" in html, "focos.html: la tabla no tiene <caption>"
    for th in re.findall(r"<th\b[^>]*>", html):
        assert 'scope="col"' in th, f"focos.html: <th> sin scope: {th}"

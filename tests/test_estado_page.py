"""ESTADO-01: la página pública /web/estado.html se sirve, es noindex y no carga recursos
externos (solo su módulo propio). El contenido lo pinta web/js/estado.js a partir de
/api/status; aquí se guarda el contrato del documento y la línea de SENAPRED."""

import re

from backend.settings import ROOT

PAGINA = ROOT / "web" / "estado.html"


def test_la_pagina_responde_y_es_noindex_con_canonical_propio(make_client):
    with make_client() as client:
        response = client.get("/web/estado.html")
    assert response.status_code == 200
    assert re.search(r'<meta name="robots" content="noindex"', response.text)
    assert re.search(r'<link rel="canonical" href="/web/estado.html"', response.text)


def test_carga_su_modulo_y_no_recursos_externos():
    html = PAGINA.read_text(encoding="utf-8")
    assert re.search(r'<script type="module" src="/web/js/estado\.js"></script>', html)
    for tag in re.findall(r"<(?:script|link|img)\b[^>]*>", html):
        for ref in re.findall(r'(?:src|href)="([^"]+)"', tag):
            assert not re.match(r"(?:https?:)?//", ref), f"recurso externo en la página: {ref}"


def test_dice_que_no_es_una_alerta_oficial_y_enlaza_senapred():
    html = PAGINA.read_text(encoding="utf-8")
    assert "BRASA no es una alerta oficial: sigue a SENAPRED" in html
    assert 'href="https://www.senapred.cl"' in html


def test_el_modulo_de_estado_existe_y_expone_la_funcion_pura():
    js = (ROOT / "web" / "js" / "estado.js").read_text(encoding="utf-8")
    assert "export function summarizeStatus" in js
    assert "no pudimos consultar el estado" in js.lower()


def test_ajustes_enlaza_al_estado_del_servicio():
    ui = (ROOT / "web" / "js" / "ui.js").read_text(encoding="utf-8")
    assert 'href="/web/estado.html"' in ui
    assert "Estado del servicio" in ui

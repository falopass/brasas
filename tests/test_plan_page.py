"""Hoja imprimible del plan familiar (UX-41): /web/plan.html es una página propia,
con su módulo /web/js/plan.js, que se imprime sin depender de una ventana emergente.
Sin scripts ni estilos en línea: la CSP del proyecto no los permite."""
import re

from backend.settings import ROOT

PAGINA = ROOT / "web" / "plan.html"


def test_plan_html_estructura():
    html = PAGINA.read_text(encoding="utf-8")
    assert "<meta charset" in html
    assert '<html lang="es"' in html
    assert "@media print" in html
    assert '<script type="module" src="/web/js/plan.js"' in html
    assert "Volver a BRASA" in html


def test_plan_html_sin_scripts_ni_estilos_en_linea():
    html = PAGINA.read_text(encoding="utf-8")
    head = html.split("</head>", 1)[0]
    assert 'style="' not in head
    for tag in re.findall(r"<script\b[^>]*>", html):
        assert 'src="' in tag, f"script en línea: {tag}"


def test_plan_page_y_modulo_se_sirven(make_client):
    with make_client() as client:
        r = client.get("/web/plan.html")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/html")
        r = client.get("/web/js/plan.js")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/javascript")

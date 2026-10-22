"""Páginas estáticas de BRASA: la hoja imprimible de emergencia (UX-07/UX-18),
la página de datos abiertos (IDEA-09), la hoja del plan familiar (UX-41) y el sitemap.

La lista y datos se sirven en la raíz; su ausencia de hosts externos, teléfonos y
módulo único ya la cubren `test_estaticas_guardas.py` y `test_paginas_livianas.py`.
"""

import re

import pytest

from backend.settings import ROOT

LISTA = ROOT / "web" / "lista.html"
DATOS = ROOT / "web" / "datos.html"
PLAN = ROOT / "web" / "plan.html"
SITEMAP = ROOT / "web" / "sitemap.xml"
BASE = "https://brasa-chile.ddiegosebastianbb.workers.dev"


def test_lista_tiene_toggle_letra_grande_sin_js():
    html = LISTA.read_text(encoding="utf-8")
    assert re.search(r'<input[^>]+id="grande"', html)
    assert re.search(r'<label[^>]+for="grande"', html)
    css = (ROOT / "web" / "css" / "lista.css").read_text(encoding="utf-8")
    assert "#grande:checked" in css
    assert re.search(r"@media print[^}]*\.size-toggle", css, re.S)


@pytest.mark.parametrize("ruta", ["/lista.html", "/datos.html", "/web/datos.html"])
def test_paginas_se_sirven_en_raiz_y_bajo_web(make_client, ruta):
    with make_client() as client:
        r = client.get(ruta)
        assert r.status_code == 200
        assert "no es un sistema oficial" in r.text


def test_datos_es_autocontenida_y_declara_la_regla_de_oro():
    html = DATOS.read_text(encoding="utf-8")
    for ref in re.findall(r'(?:src|href|action)\s*=\s*["\']([^"\']+)', html):
        assert not re.match(r"(?:https?:)?//", ref), f"referencia a un host externo: {ref}"
    for cuerpo in re.findall(r"<script[^>]*>(.*?)</script>", html, re.S):
        assert not cuerpo.strip(), "script en línea"
    assert "no es un sistema oficial" in html
    assert "SENAPRED" in html and "no es un incendio" in html
    assert "Reintentar" not in html  # el botón lo crea web/js/datos.js solo si falla el índice


def test_plan_es_una_hoja_imprimible_sin_estilos_en_linea(make_client):
    html = PLAN.read_text(encoding="utf-8")
    assert "@media print" in html
    head = html.split("</head>", 1)[0]
    assert 'style="' not in head
    with make_client() as client:
        r = client.get("/web/plan.html")
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
        r = client.get("/web/js/plan.js")
        assert r.status_code == 200 and r.headers["content-type"].startswith("text/javascript")


def test_sitemap_cubre_las_paginas_publicas_indexables():
    """Cada .html público e indexable de web/ está en el sitemap; las que declaran
    noindex quedan fuera (test_sitemap.py verifica que el sitemap no liste noindex)."""
    sitemap = SITEMAP.read_text(encoding="utf-8")
    for page in sorted((ROOT / "web").glob("*.html")):
        if page.name == "admin.html":
            continue
        html = page.read_text(encoding="utf-8").lower()
        robots = re.search(r'<meta\s+name=["\']robots["\'][^>]*>', html)
        if robots and "noindex" in robots.group(0):
            continue
        ruta = "/" if page.name == "index.html" else f"/web/{page.name}"
        assert f"<loc>{BASE}{ruta}</loc>" in sitemap, f"falta {ruta} en sitemap.xml"

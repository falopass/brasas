"""Páginas estáticas de BRASA: la hoja imprimible de emergencia (UX-07) es autocontenida,
sin scripts ni hosts externos, y se sirve en /lista.html. La página de datos abiertos
(IDEA-09) solo carga su propio script y aparece en el sitemap como toda página pública."""

import re

from backend.settings import ROOT

LISTA = ROOT / "web" / "lista.html"
DATOS = ROOT / "web" / "datos.html"
SITEMAP = ROOT / "web" / "sitemap.xml"
BASE = "https://brasa-chile.ddiegosebastianbb.workers.dev"


def test_lista_existe_sin_scripts_ni_hosts_externos():
    html = LISTA.read_text(encoding="utf-8")
    assert "<script" not in html.lower()
    for ref in re.findall(r'(?:src|href|action)\s*=\s*["\']([^"\']+)', html):
        assert not re.match(r"(?:https?:)?//", ref), f"referencia a un host externo: {ref}"


def test_lista_tiene_telefonos_y_descargo():
    html = LISTA.read_text(encoding="utf-8")
    for telefono in ("130", "131", "132", "133"):
        assert telefono in html
    assert "no es un sistema oficial" in html


def test_lista_se_sirve_en_raiz(make_client):
    with make_client() as client:
        r = client.get("/lista.html")
        assert r.status_code == 200
        assert "no es un sistema oficial" in r.text


def test_lista_tiene_toggle_letra_grande_sin_js():
    html = LISTA.read_text(encoding="utf-8")
    assert re.search(r'<input[^>]+id="grande"', html)
    assert re.search(r'<label[^>]+for="grande"', html)
    css = (ROOT / "web" / "css" / "lista.css").read_text(encoding="utf-8")
    assert "#grande:checked" in css
    assert re.search(r"@media print[^}]*\.size-toggle", css, re.S)


def test_datos_sin_scripts_inline_ni_hosts_externos():
    html = DATOS.read_text(encoding="utf-8")
    for ref in re.findall(r'(?:src|href|action)\s*=\s*["\']([^"\']+)', html):
        assert not re.match(r"(?:https?:)?//", ref), f"referencia a un host externo: {ref}"
    for cuerpo in re.findall(r"<script[^>]*>(.*?)</script>", html, re.S):
        assert not cuerpo.strip(), "script en línea"


def test_datos_tiene_descargo_y_regla_de_oro():
    html = DATOS.read_text(encoding="utf-8")
    assert "no es un sistema oficial" in html
    assert "SENAPRED" in html
    assert "no es un incendio" in html
    assert "Reintentar" not in html  # el botón lo crea web/js/datos.js solo si falla el índice


def test_datos_se_sirve_en_raiz(make_client):
    with make_client() as client:
        r = client.get("/datos.html")
        assert r.status_code == 200
        assert "no es un sistema oficial" in r.text
        assert client.get("/web/datos.html").status_code == 200


def test_sitemap_cubre_las_paginas_publicas_indexables():
    """Cada .html público e indexable de web/ está en el sitemap; las que declaran
    noindex quedan fuera (test_sitemap.py verifica que el sitemap no liste noindex)."""
    sitemap = SITEMAP.read_text(encoding="utf-8")
    assert "admin.html" not in sitemap
    for page in sorted((ROOT / "web").glob("*.html")):
        if page.name == "admin.html":
            continue
        html = page.read_text(encoding="utf-8").lower()
        robots = re.search(r'<meta\s+name=["\']robots["\'][^>]*>', html)
        if robots and "noindex" in robots.group(0):
            continue
        ruta = "/" if page.name == "index.html" else f"/web/{page.name}"
        assert f"<loc>{BASE}{ruta}</loc>" in sitemap, f"falta {ruta} en sitemap.xml"

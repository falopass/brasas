"""Páginas estáticas de BRASA: la hoja imprimible de emergencia (UX-07) es autocontenida,
sin scripts ni hosts externos, y se sirve en /lista.html. La página de datos abiertos
(IDEA-09) solo carga recursos del propio sitio, se sirve en /datos.html y, como toda
página pública de web/, aparece en sitemap.xml."""
import re

from backend.settings import ROOT

WEB = ROOT / "web"
LISTA = WEB / "lista.html"
DATOS = WEB / "datos.html"
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


def test_datos_sin_scripts_ni_hosts_externos():
    html = DATOS.read_text(encoding="utf-8")
    for ref in re.findall(r'(?:src|href|action)\s*=\s*["\']([^"\']+)', html):
        assert not re.match(r"(?:https?:)?//", ref), f"referencia a un host externo: {ref}"
    for src in re.findall(r'<script[^>]*src\s*=\s*["\']([^"\']+)', html, re.IGNORECASE):
        assert src.startswith("/"), f"script fuera del propio sitio: {src}"


def test_cada_pagina_publica_esta_en_el_sitemap():
    sitemap = (WEB / "sitemap.xml").read_text(encoding="utf-8")
    urls = set(re.findall(r"<loc>([^<]+)</loc>", sitemap))
    for pagina in WEB.glob("*.html"):
        if pagina.name == "admin.html":
            continue
        loc = f"{BASE}/" if pagina.name == "index.html" else f"{BASE}/web/{pagina.name}"
        assert loc in urls, f"{pagina.name} no aparece en sitemap.xml"


def test_datos_se_sirve_en_raiz(make_client):
    with make_client() as client:
        r = client.get("/datos.html")
        assert r.status_code == 200
        assert "no es un sistema oficial" in r.text

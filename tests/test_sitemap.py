"""Guardas del sitemap: solo anuncia páginas indexables que existen.

Una URL listada con `robots: noindex` (o inexistente) contradice el
sitemap y hace que los buscadores lo ignoren."""

import re
import xml.etree.ElementTree as ET
from urllib.parse import urlparse

from backend.settings import ROOT

WEB = ROOT / "web"
SITEMAP = WEB / "sitemap.xml"
ROBOTS = WEB / "robots.txt"
WRANGLER = ROOT / "deploy" / "cloudflare" / "wrangler.jsonc"


def _base_publica():
    """La misma fuente que la aplicación: PUBLIC_BASE_URL declarado en
    deploy/cloudflare/wrangler.jsonc (el Worker lo recibe como variable).

    No se lee del entorno ni del .env local: ahí vale 127.0.0.1 y esta
    guarda es sobre la dirección pública del sitio."""
    m = re.search(r'"PUBLIC_BASE_URL"\s*:\s*"([^"]+)"', WRANGLER.read_text(encoding="utf-8"))
    assert m and m.group(1).strip(), "wrangler.jsonc no declara PUBLIC_BASE_URL"
    return m.group(1).strip().rstrip("/")


BASE = _base_publica()


def _locs():
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    tree = ET.parse(SITEMAP)
    return [el.text.strip() for el in tree.findall(".//sm:loc", ns)]


def _archivo_de(loc):
    path = loc.removeprefix(BASE).lstrip("/")
    if path == "":
        return WEB / "index.html"
    return WEB / path.removeprefix("web/")


def test_cada_loc_apunta_a_un_archivo_existente():
    locs = _locs()
    assert locs, "el sitemap no lista ninguna URL"
    for loc in locs:
        assert loc.startswith(BASE), f"URL fuera del dominio: {loc}"
        assert _archivo_de(loc).is_file(), f"no existe archivo para {loc}"


def test_ninguna_pagina_listada_declara_noindex():
    for loc in _locs():
        html = _archivo_de(loc).read_text(encoding="utf-8").lower()
        robots = re.search(r'<meta\s+name=["\']robots["\'][^>]*>', html)
        assert not (robots and "noindex" in robots.group(0)), f"{loc} declara noindex"


def test_admin_no_es_indexable_ni_esta_en_el_sitemap():
    assert not any("admin" in loc for loc in _locs())
    assert "noindex" in (WEB / "admin.html").read_text(encoding="utf-8").lower()


def _sitemap_de_robots():
    for linea in ROBOTS.read_text(encoding="utf-8").splitlines():
        if linea.strip().lower().startswith("sitemap:"):
            return linea.split(":", 1)[1].strip()
    return ""


def test_sitemap_de_robots_es_https_y_en_el_mismo_host():
    """El `Sitemap:` de robots.txt debe vivir en el mismo host que PUBLIC_BASE_URL.

    Si el dominio cambia (OPS-11) se actualiza wrangler.jsonc y esta guarda
    exige el mismo cambio en robots.txt. Verificado a mano: poniendo otro
    host en el `Sitemap:` la prueba falla."""
    url = urlparse(_sitemap_de_robots())
    assert url.scheme == "https" and url.hostname, "el Sitemap de robots.txt debe ser una URL absoluta https://"
    esperado = urlparse(BASE).hostname
    assert url.hostname == esperado, f"robots.txt anuncia el sitemap en {url.hostname} y PUBLIC_BASE_URL es {esperado}"


def test_sitemap_de_robots_apunta_a_web_sitemap_xml():
    url = urlparse(_sitemap_de_robots())
    assert url.path == "/web/sitemap.xml", f"path inesperado en robots.txt: {url.path}"
    assert SITEMAP.is_file(), "no existe web/sitemap.xml en el repo"

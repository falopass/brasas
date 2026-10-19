"""Guardas del sitemap: solo anuncia páginas indexables que existen.

Una URL listada con `robots: noindex` (o inexistente) contradice el
sitemap y hace que los buscadores lo ignoren."""

import re
import xml.etree.ElementTree as ET

from backend.settings import ROOT

WEB = ROOT / "web"
SITEMAP = WEB / "sitemap.xml"
BASE = "https://brasa-chile.ddiegosebastianbb.workers.dev"


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

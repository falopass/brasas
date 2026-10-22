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


def _base_publica(texto=None):
    """La misma fuente que la aplicación: PUBLIC_BASE_URL declarado en
    deploy/cloudflare/wrangler.jsonc (el Worker lo recibe como variable).

    No se lee del entorno ni del .env local: ahí vale 127.0.0.1 y esta
    guarda es sobre la dirección pública del sitio. Se ignoran las líneas
    comentadas: un valor viejo comentado no puede hacer pasar la guarda."""
    texto = WRANGLER.read_text(encoding="utf-8") if texto is None else texto
    texto = re.sub(r"^\s*//.*$", "", texto, flags=re.M)
    m = re.search(r'"PUBLIC_BASE_URL"\s*:\s*"([^"]+)"', texto)
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


def test_cada_loc_existe_y_es_indexable():
    locs = _locs()
    assert locs, "el sitemap no lista ninguna URL"
    for loc in locs:
        assert loc.startswith(BASE), f"URL fuera del dominio: {loc}"
        archivo = _archivo_de(loc)
        assert archivo.is_file(), f"no existe archivo para {loc}"
        robots = re.search(r'<meta\s+name=["\']robots["\'][^>]*>', archivo.read_text(encoding="utf-8").lower())
        assert not (robots and "noindex" in robots.group(0)), f"{loc} declara noindex"


def test_admin_no_es_indexable_ni_esta_en_el_sitemap():
    assert not any("admin" in loc for loc in _locs())
    assert "noindex" in (WEB / "admin.html").read_text(encoding="utf-8").lower()


def _sitemap_de_robots():
    for linea in ROBOTS.read_text(encoding="utf-8").splitlines():
        if linea.strip().lower().startswith("sitemap:"):
            return linea.split(":", 1)[1].strip()
    return ""


def test_sitemap_de_robots_es_https_del_mismo_host_y_apunta_al_archivo():
    """El `Sitemap:` de robots.txt debe vivir en el mismo host que PUBLIC_BASE_URL.

    Si el dominio cambia (OPS-11) se actualiza wrangler.jsonc y esta guarda
    exige el mismo cambio en robots.txt. Verificado a mano: poniendo otro
    host en el `Sitemap:` la prueba falla."""
    url = urlparse(_sitemap_de_robots())
    assert url.scheme == "https" and url.hostname, "el Sitemap de robots.txt debe ser una URL absoluta https://"
    esperado = urlparse(BASE).hostname
    assert url.hostname == esperado, f"robots.txt anuncia el sitemap en {url.hostname} y PUBLIC_BASE_URL es {esperado}"
    assert url.path == "/web/sitemap.xml", f"path inesperado en robots.txt: {url.path}"


def test_la_base_publica_ignora_un_valor_comentado():
    """Un PUBLIC_BASE_URL viejo comentado no puede fijar el host esperado:
    si lo hiciera, la guarda pasaría contra el dominio que ya no se sirve."""
    jsonc = """
    {
      // "PUBLIC_BASE_URL": "https://viejo.example",
      "PUBLIC_BASE_URL": "https://nuevo.example",
    }
    """
    assert _base_publica(jsonc) == "https://nuevo.example"

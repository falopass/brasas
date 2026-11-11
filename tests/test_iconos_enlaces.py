"""ICON-E-01 · integración: los consumidores del set de marca E.

- Todas las páginas enlazan el favicon de respaldo ICO (16/32/48) más el SVG y,
  las públicas, el `apple-touch-icon` de 180.
- Los archivos referenciados existen en `web/icons/`.
- La marca de la app y de admin consume `/web/icons/icon.svg`: no quedan los
  anillos inline (`mk-iso`/`mk-core`) del set anterior.
- `/comuna/<slug>` enlaza su tarjeta propia `/og/comuna/<code>.png` con las
  dimensiones, tipo y alt del contrato, y `admin.html` no declara metas sociales.
"""

import re
from html.parser import HTMLParser

import pytest

from backend.routes import paginas_comuna
from backend.settings import ROOT
from tests.test_pagina_comuna import seed_riesgo

WEB = ROOT / "web"
PAGINAS_TODAS = sorted(p.name for p in WEB.glob("*.html"))
PAGINAS_PRIVADAS = {"admin.html"}
PAGINAS_PUBLICAS = [n for n in PAGINAS_TODAS if n not in PAGINAS_PRIVADAS]
PAGINAS_FAVICON_NUEVO = PAGINAS_TODAS


class _Links(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.metas = {}

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "link":
            self.links.append(a)
        elif tag == "meta":
            clave = a.get("property") or a.get("name")
            if clave:
                self.metas[clave] = (a.get("content") or "").strip()


def _doc(nombre):
    doc = _Links()
    doc.feed((WEB / nombre).read_text(encoding="utf-8"))
    doc.close()
    return doc


def _rel(doc, rel):
    return [l for l in doc.links if rel in (l.get("rel") or "").split()]


@pytest.mark.parametrize("nombre", PAGINAS_FAVICON_NUEVO)
def test_favicon_ico_y_svg(nombre):
    doc = _doc(nombre)
    ico = _rel(doc, "icon")
    assert any(l.get("href") == "/web/icons/favicon.ico" for l in ico), f"{nombre}: falta el favicon.ico de respaldo"
    for l in ico:
        if l.get("href") == "/web/icons/favicon.ico":
            for tam in ("16x16", "32x32", "48x48"):
                assert tam in (l.get("sizes") or ""), f"{nombre}: favicon.ico sin size {tam}"
    assert any(
        l.get("href") == "/web/icons/favicon.svg" and l.get("type") == "image/svg+xml" for l in ico
    ), f"{nombre}: falta el favicon.svg con type image/svg+xml"


@pytest.mark.parametrize("nombre", PAGINAS_PUBLICAS)
def test_apple_touch_icon_180(nombre):
    doc = _doc(nombre)
    apple = _rel(doc, "apple-touch-icon")
    assert apple and apple[0].get("href") == "/web/icons/apple-touch-icon.png", (
        f"{nombre}: falta el apple-touch-icon de 180"
    )
    assert (apple[0].get("sizes") or "") == "180x180", f"{nombre}: apple-touch-icon sin sizes=180x180"


def test_archivos_de_marca_referenciados_existen():
    """Cada /web/icons/... que enlaza una página (favicon, apple-touch-icon,
    og:image) existe en el repo."""
    faltantes = []
    for nombre in PAGINAS_TODAS:
        doc = _doc(nombre)
        refs = [l.get("href") or "" for l in doc.links]
        og = doc.metas.get("og:image") or ""
        if og.startswith("https://brasa-chile.ddiegosebastianbb.workers.dev/"):
            refs.append(og.split("workers.dev", 1)[1])
        for src in refs:
            if src.startswith("/web/icons/") and not (WEB / src.removeprefix("/web/")).is_file():
                faltantes.append(f"{nombre}: {src}")
    assert not faltantes, "iconos enlazados sin archivo:\n" + "\n".join(faltantes)


@pytest.mark.parametrize("nombre", ["index.html", "admin.html"])
def test_la_marca_consume_icon_svg_sin_anillos(nombre):
    """El motivo de anillos quedó atrás: la marca es el icon.svg del set E, con el
    mismo tamaño (.mark/.mark-sm) y semántica decorativa (alt vacío)."""
    html = (WEB / nombre).read_text(encoding="utf-8")
    assert "mk-iso" not in html and "mk-core" not in html, f"{nombre}: aún lleva los anillos inline"
    assert 'class="mark" src="/web/icons/icon.svg"' in html, f"{nombre}: la marca no consume /web/icons/icon.svg"
    marcas = re.findall(r'<img class="mark[^"]*" src="/web/icons/icon\.svg"[^>]*>', html)
    assert marcas, f"{nombre}: falta la marca <img> con icon.svg"
    for tag in marcas:
        assert 'alt=""' in tag, f"{nombre}: la marca decorativa debe llevar alt vacío: {tag}"


def test_admin_sin_metas_sociales():
    """La moderación es privada: no debe declarar Open Graph ni twitter:card."""
    doc = _doc("admin.html")
    assert not any(clave.startswith(("og:", "twitter:")) for clave in doc.metas), (
        "admin.html declara metas sociales"
    )


def test_comuna_enlaza_su_tarjeta_og(make_client):
    """La ficha de comuna comparte `/og/comuna/<codigo>.png` con el contrato
    completo: imagen absoluta 1200×630 PNG, alt con el nombre real y card grande."""
    with make_client() as client:
        db = client.app.state.services.db
        c = paginas_comuna.territory().comunas[0]
        seed_riesgo(db, c.code)
        body = client.get(f"/comuna/{paginas_comuna.slug(c.name)}").text
    imagen = f"/og/comuna/{c.code}.png"
    assert f'property="og:image" content="{paginas_comuna.PUBLIC_BASE}{imagen}"' in body
    assert 'property="og:image:width" content="1200"' in body
    assert 'property="og:image:height" content="630"' in body
    assert 'property="og:image:type" content="image/png"' in body
    assert paginas_comuna._esc(c.name) in re.search(r'property="og:image:alt" content="([^"]+)"', body).group(1)
    assert 'name="twitter:card" content="summary_large_image"' in body
    assert 'rel="apple-touch-icon" href="/web/icons/apple-touch-icon.png"' in body

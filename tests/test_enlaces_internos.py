"""Enlaces y recursos internos de BRASA, sin red (AUTO-04).

Cada `href`/`src` que empieza con `/` debe apuntar a un archivo de `web/` o a una
ruta GET declarada en `backend/`. Cada `#/nombre` debe existir en `LABELS` de
`web/js/app.js`, y cada `<loc>` del sitemap debe tener su archivo.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

from backend.settings import ROOT

WEB = ROOT / "web"
BACKEND = ROOT / "backend"
APP_JS = WEB / "js" / "app.js"
SITEMAP = WEB / "sitemap.xml"
BASE = "https://brasa-chile.ddiegosebastianbb.workers.dev"

# Excepciones documentadas: rutas que sirve otro componente (por ejemplo el
# Worker de Cloudflare) y que por eso no aparecen en backend/. Vacía: hoy toda
# ruta interna la sirve FastAPI o es un archivo de web/.
EXCEPCIONES: dict[str, str] = {}

_ATRIBUTO = re.compile(r"""(?:href|src)\s*=\s*["']([^"']+)["']""")
_FRAGMENTO = re.compile(r"#/([A-Za-z0-9_-]+)")
_DECORADOR = re.compile(r"""@(\w+)\.get\(\s*["']([^"']*)["']""")
_ROUTER = re.compile(r"(\w+)\s*=\s*APIRouter\(([^)]*)\)")
_PREFIJO = re.compile(r"""prefix\s*=\s*["']([^"']+)["']""")


class _EnlacesHtml(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.enlaces: list[tuple[int, str]] = []

    def handle_starttag(self, tag, attrs):
        for nombre, valor in attrs:
            if nombre in ("href", "src") and valor and valor.startswith("/"):
                self.enlaces.append((self.getpos()[0], valor))


def _fuentes() -> list[Path]:
    return sorted(WEB.glob("*.html")) + sorted((WEB / "js").rglob("*.js"))


def _rel(archivo: Path) -> str:
    return archivo.relative_to(ROOT).as_posix()


def _enlaces_de(archivo: Path) -> list[tuple[int, str]]:
    texto = archivo.read_text(encoding="utf-8")
    if archivo.suffix == ".html":
        parser = _EnlacesHtml()
        parser.feed(texto)
        return parser.enlaces
    return [
        (numero, enlace)
        for numero, linea in enumerate(texto.splitlines(), 1)
        for enlace in _ATRIBUTO.findall(linea)
        if enlace.startswith("/")
    ]


def _rutas_backend() -> list[re.Pattern[str]]:
    rutas = []
    for archivo in BACKEND.rglob("*.py"):
        texto = archivo.read_text(encoding="utf-8")
        prefijos = {}
        for m in _ROUTER.finditer(texto):
            prefijo = _PREFIJO.search(m.group(2))
            prefijos[m.group(1)] = prefijo.group(1) if prefijo else ""
        for m in _DECORADOR.finditer(texto):
            nombre, ruta = m.group(1), m.group(2)
            if nombre in prefijos:
                ruta = prefijos[nombre] + ruta
            elif nombre != "app":
                continue
            partes = re.split(r"\{[^}]+\}", ruta or "/")
            rutas.append(re.compile("^" + "[^/]+".join(re.escape(p) for p in partes) + "$"))
    return rutas


def _valido(enlace: str, rutas: list[re.Pattern[str]]) -> bool:
    ruta = enlace.split("#", 1)[0].split("?", 1)[0]
    if ruta.startswith("/web/"):
        return (WEB / ruta.removeprefix("/web/")).is_file()
    return ruta in EXCEPCIONES or any(p.match(ruta) for p in rutas)


def _labels() -> set[str]:
    texto = APP_JS.read_text(encoding="utf-8")
    bloque = re.search(r"const LABELS = \{(.*?)\};", texto, re.S)
    return set(re.findall(r"""["']?([\w-]+)["']?\s*:""", bloque.group(1))) if bloque else set()


def test_recursos_y_paginas_internas_existen():
    rutas = _rutas_backend()
    fallas = [
        f"{_rel(archivo)}:{numero}: {enlace} (no existe en web/ ni es una ruta de backend/)"
        for archivo in _fuentes()
        for numero, enlace in _enlaces_de(archivo)
        if "${" not in enlace and not enlace.startswith("//") and not _valido(enlace, rutas)
    ]
    assert not fallas, "Enlaces internos sin destino:\n" + "\n".join(fallas)


def test_rutas_por_fragmento_existen_en_labels():
    labels = _labels()
    assert labels, "no se pudo leer const LABELS de web/js/app.js"
    fallas = [
        f"{_rel(archivo)}:{numero}: #/{nombre} (no está en LABELS)"
        for archivo in _fuentes()
        for numero, linea in enumerate(archivo.read_text(encoding="utf-8").splitlines(), 1)
        for nombre in _FRAGMENTO.findall(linea)
        if nombre not in labels
    ]
    assert not fallas, "Rutas por fragmento sin vista:\n" + "\n".join(fallas)


def test_sitemap_apunta_a_archivos_de_web():
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    locs = [el.text.strip() for el in ET.parse(SITEMAP).findall(".//sm:loc", ns)]
    assert locs, "el sitemap no lista ninguna URL"
    fallas = []
    for loc in locs:
        ruta = loc.removeprefix(BASE).lstrip("/")
        ruta = "index.html" if not ruta else ruta.removeprefix("web/")
        if not (WEB / ruta).is_file():
            fallas.append(f"web/sitemap.xml: {loc} (no existe web/{ruta})")
    assert not fallas, "URLs del sitemap sin archivo:\n" + "\n".join(fallas)


def test_la_guarda_detecta_un_enlace_roto():
    """La guarda tiene que fallar con un enlace roto, no solo pasar en verde."""
    rutas = _rutas_backend()
    for enlace in ("/web/css/no-existe.css", "/js/no-existe.js", "/api/no-existe"):
        assert not _valido(enlace, rutas), f"{enlace} debería verse como roto"
    assert _valido("/api/status", rutas), "una ruta GET de backend/ debe resolver"
    assert "vista-fantasma" not in _labels(), "una vista inventada no puede estar en LABELS"

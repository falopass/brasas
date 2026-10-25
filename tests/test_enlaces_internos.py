"""Enlaces y recursos internos de BRASA, sin red (AUTO-04, ENLACES-04).

Cada `href`/`src` que empieza con `/` debe apuntar a un archivo de `web/` o a una
ruta GET declarada en `backend/`. Cada `#/nombre` debe existir en `LABELS` de
`web/js/app.js`, y las vistas registradas deben ser exactamente las esperadas:
un `#/ruta` que no existe queda muerto sin que nadie lo note.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

from backend.settings import ROOT

WEB = ROOT / "web"
BACKEND = ROOT / "backend"
APP_JS = WEB / "js" / "app.js"
VIEWS = WEB / "js" / "views"

# Excepciones documentadas: rutas que sirve otro componente (por ejemplo el
# Worker de Cloudflare) y que por eso no aparecen en backend/. Vacía: hoy toda
# ruta interna la sirve FastAPI o es un archivo de web/.
EXCEPCIONES: dict[str, str] = {}

# Vistas registradas hoy (los `id:` de web/js/views/*.js). La raíz «#/» nunca
# produce hallazgo: el router la resuelve a «mi-zona». «#/v/<token>» es la
# ficha que comparte un vecino y cuenta como la vista «v».
VISTAS_ESPERADAS = {
    "alertas",
    "calidad",
    "casos",
    "incendio",
    "mapa",
    "mas",
    "mi-zona",
    "preparate",
    "privacidad",
    "quehago",
    "riesgo",
    "temporada",
    "v",
}

_ATRIBUTO = re.compile(r"""(?:href|src)\s*=\s*["']([^"']+)["']""")
_FRAGMENTO = re.compile(r"#/([A-Za-z0-9_-]+)")
_ID_VISTA = re.compile(r"""^\s*id:\s*["']([\w-]+)["']""", re.MULTILINE)
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


def _vistas_registradas() -> set[str]:
    return {vista for archivo in VIEWS.glob("*.js") for vista in _ID_VISTA.findall(archivo.read_text(encoding="utf-8"))}


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


def test_las_vistas_registradas_son_las_esperadas():
    registradas = _vistas_registradas()
    assert registradas == VISTAS_ESPERADAS, (
        f"las vistas cambiaron: faltan {sorted(VISTAS_ESPERADAS - registradas)}, "
        f"sobran {sorted(registradas - VISTAS_ESPERADAS)}; actualiza VISTAS_ESPERADAS"
    )


def test_la_guarda_detecta_enlaces_y_vistas_rotas(tmp_path):
    """La cadena completa —extraer y validar— acusa el archivo que falta y la vista fantasma."""
    rutas = _rutas_backend()
    for enlace in ("/web/css/no-existe.css", "/js/no-existe.js", "/api/no-existe"):
        assert not _valido(enlace, rutas), f"{enlace} debería verse como roto"
    assert _valido("/api/status", rutas), "una ruta GET de backend/ debe resolver"
    pagina = tmp_path / "rota.html"
    pagina.write_text('<a href="/web/css/no-existe.css">x</a>\n<a href="#/vista-fantasma">y</a>', encoding="utf-8")
    assert [enlace for _, enlace in _enlaces_de(pagina) if not _valido(enlace, rutas)] == ["/web/css/no-existe.css"]
    labels = _labels()
    fantasmas = [
        (numero, nombre)
        for numero, linea in enumerate(pagina.read_text(encoding="utf-8").splitlines(), 1)
        for nombre in _FRAGMENTO.findall(linea)
        if nombre not in labels
    ]
    assert fantasmas == [(2, "vista-fantasma")]

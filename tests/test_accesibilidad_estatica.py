"""Guardas de accesibilidad básica de las páginas estáticas (QA-36, QA-76):
estructura mínima de todas las páginas sueltas y guardas estrictas
(landmarks y controles con nombre accesible) en PAGINAS. Solo HTML
estático, con `html.parser` de la biblioteca estándar.

PAGINAS cubre index, lite, lista, admin, respuesta, datos, plan y preguntas.
plan.html es la única excepción de <h1>: la hoja real la pinta web/js/plan.js:77
en tiempo de ejecución, así que el título definitivo no existe en el HTML; la
guarda acepta 0 o 1 <h1> ahí y axe-core lo revisa ya renderizado en
scripts/local/browser_checks.py. El <h1> de respaldo del HTML se reemplaza al
pintar la hoja, no se duplica.

pantalla.html sigue fuera de PAGINAS porque la está tocando UX-45; se suma
cuando ese PR esté en main.

Comprobado a mano: sin el aria-label del <main> de datos.html, test_estructura
falla; se restaura y vuelve a verde."""

from html.parser import HTMLParser

import pytest

from backend.settings import ROOT

PAGINAS = [
    "index.html",
    "lite.html",
    "lista.html",
    "admin.html",
    "respuesta.html",
    "datos.html",
    "plan.html",
    "preguntas.html",
]
PAGINAS_SUELTAS = sorted(ruta.name for ruta in (ROOT / "web").glob("*.html"))
# plan.html no puede exigir un <h1> estático: plan.js:77 escribe el título al pintar
# la hoja. La revisión en navegador (axe) lo cubre ya renderizado.
SIN_H1_ESTATICO = {"plan.html": "lo escribe plan.js:77; lo cubre la revisión en navegador"}


class _Doc(HTMLParser):
    """Recolecta en una pasada lo que miran las guardas."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lang = ""
        self._en_title = False
        self.title = ""
        self.ids = set()
        self.skip_links = []  # href de cada .skip-link
        self.h1 = 0
        self.landmarks = []  # (tag, aria-label) de cada <main> y <nav>
        self.imgs = []  # atributos de cada <img>
        self.controles = []  # (tag, atributos) de input/select/textarea
        self.labels_for = set()  # ids referenciados por <label for>
        self.botones = []  # {"aria_label": str, "texto": str}
        self.tabindices = []
        self.tablas = []  # {"caption": str, "ths": [atributos]} de cada <table>
        self._boton = None  # <button> abierto, para juntar su texto
        self._tabla = None  # <table> abierta, para juntar su caption y sus <th>
        self._en_caption = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "html":
            self.lang = (a.get("lang") or "").strip()
        elif tag == "title":
            self._en_title = True
        elif tag == "h1":
            self.h1 += 1
        elif tag in ("main", "nav"):
            self.landmarks.append((tag, (a.get("aria-label") or "").strip()))
        elif tag == "img":
            self.imgs.append(a)
        elif tag in ("input", "select", "textarea"):
            if (a.get("type") or "") != "hidden":
                self.controles.append((tag, a))
        elif tag == "label" and a.get("for"):
            self.labels_for.add(a["for"])
        elif tag == "button":
            self._boton = {"aria_label": (a.get("aria-label") or "").strip(), "texto": ""}
            self.botones.append(self._boton)
        elif tag == "table":
            self._tabla = {"caption": "", "ths": []}
            self.tablas.append(self._tabla)
        elif tag == "caption" and self._tabla is not None:
            self._en_caption = True
        elif tag == "th" and self._tabla is not None:
            self._tabla["ths"].append(a)
        if a.get("id"):
            self.ids.add(a["id"])
        if "skip-link" in (a.get("class") or "").split():
            self.skip_links.append(a.get("href") or "")
        if a.get("tabindex") is not None:
            try:
                self.tabindices.append(int(a["tabindex"]))
            except ValueError:
                self.tabindices.append(1)

    def handle_endtag(self, tag):
        if tag == "title":
            self._en_title = False
        elif tag == "button":
            self._boton = None
        elif tag == "caption":
            self._en_caption = False
        elif tag == "table":
            self._tabla = None

    def handle_data(self, data):
        if self._en_title:
            self.title += data
        if self._boton is not None:
            self._boton["texto"] += data
        if self._en_caption and self._tabla is not None:
            self._tabla["caption"] += data


def _doc(nombre):
    doc = _Doc()
    doc.feed((ROOT / "web" / nombre).read_text(encoding="utf-8"))
    doc.close()
    return doc


def _assert_h1(nombre, doc):
    if nombre in SIN_H1_ESTATICO:
        assert doc.h1 <= 1, f"{nombre}: {doc.h1} encabezados <h1> (se espera a lo sumo 1)"
    else:
        assert doc.h1 == 1, f"{nombre}: {doc.h1} encabezados <h1> (se espera exactamente 1)"


def test_paginas_sueltas_cubiertas():
    assert len(PAGINAS_SUELTAS) >= 9, f"solo {len(PAGINAS_SUELTAS)} páginas en web/; la guarda debe cubrir al menos nueve"


@pytest.mark.parametrize("nombre", PAGINAS_SUELTAS)
def test_estructura_minima(nombre):
    doc = _doc(nombre)
    assert doc.lang, f"{nombre}: <html> sin lang"
    assert doc.title.strip(), f"{nombre}: <title> vacío o ausente"
    _assert_h1(nombre, doc)
    assert any(tag == "main" for tag, _ in doc.landmarks), f"{nombre}: falta <main>"


@pytest.mark.parametrize("nombre", PAGINAS)
def test_lang_y_title(nombre):
    doc = _doc(nombre)
    assert doc.lang, f"{nombre}: <html> sin lang"
    assert doc.title.strip(), f"{nombre}: <title> vacío o ausente"


@pytest.mark.parametrize("nombre", PAGINAS)
def test_estructura(nombre):
    doc = _doc(nombre)
    for href in doc.skip_links:
        destino = href[1:] if href.startswith("#") else ""
        assert destino and destino in doc.ids, f"{nombre}: skip-link {href!r} sin destino"
    _assert_h1(nombre, doc)
    assert any(tag == "main" for tag, _ in doc.landmarks), f"{nombre}: falta <main>"
    for tag, label in doc.landmarks:
        assert label, f"{nombre}: <{tag}> sin aria-label"


@pytest.mark.parametrize("nombre", PAGINAS)
def test_nombres_accesibles(nombre):
    doc = _doc(nombre)
    for img in doc.imgs:
        assert "alt" in img or img.get("aria-hidden") == "true", f"{nombre}: <img src={img.get('src', '?')!r}> sin alt ni aria-hidden"
    for tag, a in doc.controles:
        assert (a.get("aria-label") or "").strip() or a.get("id") in doc.labels_for, (
            f"{nombre}: <{tag} id={a.get('id', '?')!r}> sin <label for> ni aria-label"
        )
    for b in doc.botones:
        assert b["aria_label"] or b["texto"].strip(), f"{nombre}: <button> sin texto ni aria-label"
    for ti in doc.tabindices:
        assert ti <= 0, f"{nombre}: tabindex positivo ({ti})"


def test_tablas_de_respuesta_con_caption_y_scope():
    """respuesta.html: cada tabla dice qué mide y cada <th> declara su alcance (QA-36)."""
    doc = _doc("respuesta.html")
    assert doc.tablas, "respuesta.html: no se encontraron tablas"
    for i, tabla in enumerate(doc.tablas, 1):
        assert tabla["caption"].strip(), f"respuesta.html: la tabla {i} no tiene <caption>"
        for th in tabla["ths"]:
            assert (th.get("scope") or "").strip(), f"respuesta.html: la tabla {i} tiene un <th> sin scope"

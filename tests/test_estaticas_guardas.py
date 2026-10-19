"""Guardas de las páginas estáticas y del precache del service worker:
un typo en `SHELL` o una página sin `lang`, `title` o `description`
debe romper el CI en vez de llegar a producción."""
import re

from backend.settings import ROOT

SW = ROOT / "web" / "sw.js"
MAIN = ROOT / "backend" / "main.py"

# Páginas que no se indexan: les basta `robots: noindex` en vez de description.
NOINDEX = {"admin.html", "lista.html", "pantalla.html"}
# Páginas autocontenidas: ninguna referencia a hosts externos.
AUTOCONTENIDAS = {"lista.html", "lite.html", "pantalla.html"}


def _rutas_precache():
    sw = SW.read_text(encoding="utf-8")
    bloque = sw.split("SHELL = [", 1)[1].split("]", 1)[0]
    return re.findall(r"'([^']+)'", bloque)


def _rutas_backend():
    main = MAIN.read_text(encoding="utf-8")
    return set(re.findall(r'@app\.get\("([^"]+)"', main))


def test_precache_sin_rutas_rotas():
    """Cada ruta de `SHELL` existe como archivo bajo `web/` (o en la raíz del
    repo para `/web/...`) o está declarada como ruta en `backend/main.py`."""
    rutas_backend = _rutas_backend()
    faltantes = []
    for ruta in _rutas_precache():
        rel = ruta.lstrip("/")
        if (
            ruta not in rutas_backend
            and not (ROOT / "web" / rel).is_file()
            and not (ROOT / rel).is_file()
        ):
            faltantes.append(ruta)
    assert not faltantes, f"rutas del precache sin archivo ni ruta declarada: {faltantes}"


def test_paginas_tienen_metadatos():
    for pagina in sorted((ROOT / "web").glob("*.html")):
        html = pagina.read_text(encoding="utf-8")
        assert '<html lang="es"' in html, f"{pagina.name} sin lang=es"
        title = re.search(r"<title>(.*?)</title>", html)
        assert title and title.group(1).strip(), f"{pagina.name} sin <title>"
        assert re.search(r'<meta\s+name="viewport"', html), f"{pagina.name} sin viewport"
        if pagina.name in NOINDEX:
            assert re.search(
                r'<meta\s+name="robots"\s+content="noindex"', html
            ), f"{pagina.name} noindex sin meta robots"
        else:
            assert re.search(
                r'<meta\s+name="description"\s+content="\S', html
            ), f"{pagina.name} sin description"


def test_autocontenidas_sin_terceros():
    """Ningún recurso cargado por la página viene de otro host.
    Los <a href> externos (p. ej. el enlace a senapred.cl) no se cuentan:
    el navegador no los descarga, solo los sigue el usuario."""
    for nombre in sorted(AUTOCONTENIDAS):
        html = (ROOT / "web" / nombre).read_text(encoding="utf-8")
        for tag, attr, ref in re.findall(
            r"<(\w+)[^>]*?\b(src|href|action)\s*=\s*[\"']([^\"']+)", html
        ):
            if tag.lower() == "a":
                continue
            assert not re.match(
                r"(?:https?:)?//", ref
            ), f"{nombre}: host externo {ref}"

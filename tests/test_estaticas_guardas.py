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
# Rutas del SHELL que aún no existen en disco porque las crea otro encargo en
# paralelo (el install usa allSettled y las tolera). Quitar cada entrada
# apenas el archivo exista. Hoy: RISK-18 crea /web/js/enso.js.
PENDIENTES = {"/web/js/enso.js"}


def _rutas_precache():
    sw = SW.read_text(encoding="utf-8")
    bloque = sw.split("SHELL = [", 1)[1].split("]", 1)[0]
    return re.findall(r"'([^']+)'", bloque)


# Imports que carga el navegador: `import ... from '…'`, `export ... from '…'`,
# `import '…'` y `import('…')`. Solo se siguen las rutas relativas.
_IMPORT_ESTATICO = re.compile(r"\bfrom\s+['\"]([^'\"]+)['\"]")
_IMPORT_DIRECTO = re.compile(r"\bimport\s*(?:\(\s*)?['\"]([^'\"]+)['\"]")


def _import_relativos(archivo):
    src = archivo.read_text(encoding="utf-8")
    for ref in _IMPORT_ESTATICO.findall(src) + _IMPORT_DIRECTO.findall(src):
        if ref.startswith(("./", "../")):
            yield (archivo.parent / ref).resolve()


def modulos_del_arranque():
    """Módulos JS bajo web/ que el navegador descarga para abrir la app:
    el `src` de cada <script type="module"> de las páginas precargadas en
    `SHELL`, más sus imports relativos de forma transitiva. Lo externo
    (https://…) no es relativo y web/vendor se ignora: va aparte."""
    shell = set(_rutas_precache())
    semillas = []
    for pagina in (ROOT / "web").glob("*.html"):
        if f"/web/{pagina.name}" not in shell and pagina.name != "index.html":
            continue  # solo las páginas precargadas deben abrir sin conexión
        for tag in re.findall(r"<script\b[^>]*>", pagina.read_text(encoding="utf-8")):
            if 'type="module"' not in tag:
                continue
            src = re.search(r'src=["\']([^"\']+)["\']', tag)
            if src and src.group(1).startswith("/web/"):
                semillas.append(ROOT / src.group(1).lstrip("/"))
    modulos = set()
    pendientes = list(semillas)
    while pendientes:
        modulo = pendientes.pop()
        if not modulo.is_file() or not modulo.is_relative_to(ROOT):
            continue
        rel = "/" + modulo.relative_to(ROOT).as_posix()
        if "vendor" in modulo.parts or rel in modulos:
            continue
        modulos.add(rel)
        pendientes.extend(_import_relativos(modulo))
    return modulos


def _faltantes_precache(modulos, shell):
    return sorted(m for m in modulos if m not in shell)


def test_modulos_del_arranque_en_precache():
    """Todo módulo que el arranque necesita está en `SHELL`: sin él, la vista
    correspondiente se rompe sin conexión aunque nadie note nada en línea."""
    faltantes = _faltantes_precache(modulos_del_arranque(), set(_rutas_precache()))
    assert not faltantes, "; ".join(
        f"agrega {ruta} a SHELL en web/sw.js" for ruta in faltantes
    )


def test_guarda_precache_detecta_faltantes():
    """La comparación devuelve justo los módulos ausentes del SHELL."""
    modulos = {"/web/js/app.js", "/web/js/views/fantasma.js"}
    assert _faltantes_precache(modulos, {"/web/js/app.js"}) == ["/web/js/views/fantasma.js"]


def _rutas_backend():
    main = MAIN.read_text(encoding="utf-8")
    return set(re.findall(r'@app\.get\("([^"]+)"', main))


def test_precache_sin_rutas_rotas():
    """Cada ruta de `SHELL` existe como archivo bajo `web/` (o en la raíz del
    repo para `/web/...`) o está declarada como ruta en `backend/main.py`."""
    rutas_backend = _rutas_backend()
    faltantes = []
    for ruta in _rutas_precache():
        if ruta in PENDIENTES:
            continue
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

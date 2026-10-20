"""Guardas de las páginas estáticas y del precache del service worker:
un typo en `SHELL` o una página sin `lang`, `title` o `description`
debe romper el CI en vez de llegar a producción."""

import re

from backend.settings import ROOT

SW = ROOT / "web" / "sw.js"
MAIN = ROOT / "backend" / "main.py"
LISTA = ROOT / "web" / "lista.html"
CSS_LISTA = ROOT / "web" / "css" / "lista.css"

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
    assert not faltantes, "; ".join(f"agrega {ruta} a SHELL en web/sw.js" for ruta in faltantes)


def test_guarda_precache_detecta_faltantes():
    """La comparación devuelve justo los módulos ausentes del SHELL."""
    modulos = {"/web/js/app.js", "/web/js/views/fantasma.js"}
    assert _faltantes_precache(modulos, {"/web/js/app.js"}) == ["/web/js/views/fantasma.js"]


def _rutas_backend():
    main = MAIN.read_text(encoding="utf-8")
    return set(re.findall(r'@app\.get\("([^"]+)"', main))


def _ruta_existe(root, ruta, rutas_backend):
    """Una ruta del SHELL existe si el backend la sirve, o si hay un archivo
    bajo `web/` o bajo la raíz del repo (`/` vive en main.py)."""
    rel = ruta.lstrip("/")
    return ruta in rutas_backend or (root / "web" / rel).is_file() or (root / rel).is_file()


def _rutas_inexistentes(root, rutas, pendientes, rutas_backend=()):
    return sorted(r for r in rutas if r not in pendientes and not _ruta_existe(root, r, rutas_backend))


def _pendientes_creadas(root, pendientes):
    return sorted(r for r in pendientes if (root / r.lstrip("/")).is_file() or (root / "web" / r.lstrip("/")).is_file())


def test_precache_sin_rutas_rotas():
    """Cada ruta de `SHELL` existe como archivo bajo `web/` (o en la raíz del
    repo para `/web/...`) o está declarada como ruta en `backend/main.py`."""
    faltantes = _rutas_inexistentes(ROOT, _rutas_precache(), PENDIENTES, _rutas_backend())
    assert not faltantes, f"rutas del precache sin archivo ni ruta declarada: {faltantes}"


def test_precache_solo_apunta_a_archivos_existentes():
    """Guarda bidireccional del precache: toda ruta de `SHELL` apunta a algo
    que existe en disco o en el backend. `cache.add` corre con `allSettled`,
    así que una ruta rota no rompe el install: pasa en silencio."""
    rotas = _rutas_inexistentes(ROOT, _rutas_precache(), PENDIENTES, _rutas_backend())
    assert not rotas, "; ".join(f"{ruta} sobra en SHELL de web/sw.js o falta crear el archivo" for ruta in rotas)


def test_pendientes_no_conserva_rutas_creadas():
    """Una entrada de `PENDIENTES` cuyo archivo ya existe taparía un error
    futuro: hay que quitarla de la lista apenas el archivo aparece."""
    creadas = _pendientes_creadas(ROOT, PENDIENTES)
    assert not creadas, "; ".join(f"{ruta} ya existe en disco: quítala de PENDIENTES" for ruta in creadas)


def test_guarda_existencia_detecta_rutas_rotas(tmp_path):
    """La comparación devuelve solo las rutas sin archivo: las pendientes se
    toleran y las rutas del backend cuentan como existentes."""
    (tmp_path / "web" / "js").mkdir(parents=True)
    (tmp_path / "web" / "js" / "app.js").write_text("", encoding="utf-8")
    rutas = ["/web/js/app.js", "/web/js/fantasma.js", "/web/js/enso.js", "/ping"]
    assert _rutas_inexistentes(tmp_path, rutas, {"/web/js/enso.js"}, {"/ping"}) == ["/web/js/fantasma.js"]


def test_guarda_pendientes_detecta_creadas(tmp_path):
    """`PENDIENTES` se limpia sola: si el archivo aparece, la guarda lo pide."""
    (tmp_path / "web" / "js").mkdir(parents=True)
    (tmp_path / "web" / "js" / "enso.js").write_text("", encoding="utf-8")
    assert _pendientes_creadas(tmp_path, {"/web/js/enso.js", "/web/js/todavia-no.js"}) == ["/web/js/enso.js"]


def test_paginas_tienen_metadatos():
    for pagina in sorted((ROOT / "web").glob("*.html")):
        html = pagina.read_text(encoding="utf-8")
        assert '<html lang="es"' in html, f"{pagina.name} sin lang=es"
        title = re.search(r"<title>(.*?)</title>", html)
        assert title and title.group(1).strip(), f"{pagina.name} sin <title>"
        assert re.search(r'<meta\s+name="viewport"', html), f"{pagina.name} sin viewport"
        if pagina.name in NOINDEX:
            assert re.search(r'<meta\s+name="robots"\s+content="noindex"', html), f"{pagina.name} noindex sin meta robots"
        else:
            assert re.search(r'<meta\s+name="description"\s+content="\S', html), f"{pagina.name} sin description"


def test_autocontenidas_sin_terceros():
    """Ningún recurso cargado por la página viene de otro host.
    Los <a href> externos (p. ej. el enlace a senapred.cl) no se cuentan:
    el navegador no los descarga, solo los sigue el usuario."""
    for nombre in sorted(AUTOCONTENIDAS):
        html = (ROOT / "web" / nombre).read_text(encoding="utf-8")
        for tag, attr, ref in re.findall(r"<(\w+)[^>]*?\b(src|href|action)\s*=\s*[\"']([^\"']+)", html):
            if tag.lower() == "a":
                continue
            assert not re.match(r"(?:https?:)?//", ref), f"{nombre}: host externo {ref}"


def test_hoja_imprimible_con_casillas_tel_y_espacios_rotulados():
    """La hoja del refrigerador (UX-07/UX-18) se usa con lápiz y con lector de
    pantalla: cada ítem de las dos listas lleva una casilla real con su
    <label for>, los teléfonos se pueden llamar desde el celular y cada línea
    en blanco dice qué se escribe en ella. El bloque de impresión no puede
    desaparecer."""
    html = LISTA.read_text(encoding="utf-8")
    listas = re.findall(r'<ul class="kit[^"]*">(.*?)</ul>', html, re.S)
    assert len(listas) == 2, f"lista.html: se esperan las 2 listas con casillas, hay {len(listas)}"
    for lista in listas:
        for item in re.findall(r"<li>(.*?)</li>", lista, re.S):
            casilla = re.search(r'<input[^>]*type="checkbox"[^>]*id="([^"]+)"', item)
            assert casilla, f"lista.html: ítem sin casilla: {item.strip()[:60]}"
            assert re.search(rf'<label[^>]*for="{re.escape(casilla.group(1))}"', item), (
                f"lista.html: la casilla {casilla.group(1)} no tiene <label for>"
            )

    telefonos = re.search(r'<ul class="phones">(.*?)</ul>', html, re.S)
    assert telefonos, "lista.html: falta la lista de teléfonos de emergencia"
    numeros = set()
    for item in re.findall(r"<li>(.*?)</li>", telefonos.group(1), re.S):
        enlace = re.search(r'href="tel:(\d+)"', item)
        assert enlace, f"lista.html: teléfono sin enlace tel:: {item.strip()[:60]}"
        numeros.add(enlace.group(1))
        assert re.search(rf'href="tel:{enlace.group(1)}"[^>]*>{enlace.group(1)}</a>', item), (
            f"lista.html: el enlace tel:{enlace.group(1)} no muestra el número"
        )
    assert numeros >= {"130", "131", "132", "133"}, f"lista.html: faltan teléfonos: {sorted({'130', '131', '132', '133'} - numeros)}"

    espacios = re.findall(r'<[^>]*class="[^"]*\bblank\b[^"]*"[^>]*>', html)
    assert espacios, "lista.html: no hay líneas en blanco (.blank)"
    for etiqueta in espacios:
        assert re.search(r'aria-label="[^"]+"', etiqueta), f"lista.html: .blank sin aria-label: {etiqueta}"
        assert 'aria-hidden="true"' not in etiqueta, f"lista.html: .blank con aria-hidden: {etiqueta}"

    css = CSS_LISTA.read_text(encoding="utf-8")
    impresion = re.search(r"@media print\s*\{(.*?)\n\}", css, re.S)
    assert impresion, "lista.css: falta el bloque @media print"
    assert "break-inside: avoid" in impresion.group(1), "lista.css: @media print sin break-inside: avoid"

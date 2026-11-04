"""Guardas de las páginas estáticas y del precache del service worker:
un typo en `SHELL` o una página sin `viewport` o `description`
debe romper el CI en vez de llegar a producción.

La ruta pública de `SHELL` la vigila `tests/test_service_worker.py` y
`lang`/`title` los vigila `tests/test_accesibilidad_estatica.py`; la
existencia de los archivos se comprueba aquí.
"""

import re

from backend.settings import ROOT

SW = ROOT / "web" / "sw.js"
LISTA = ROOT / "web" / "lista.html"
CSS_LISTA = ROOT / "web" / "css" / "lista.css"
PANTALLA = ROOT / "web" / "pantalla.html"
PANTALLA_JS = ROOT / "web" / "js" / "pantalla.js"
MAP_JS = ROOT / "web" / "js" / "map.js"

# Páginas que no se indexan: les basta `robots: noindex` en vez de description.
NOINDEX = {"admin.html", "colegios.html", "lista.html", "pantalla.html"}
# Páginas autocontenidas: ninguna referencia a hosts externos.
AUTOCONTENIDAS = {"colegios.html", "lista.html", "lite.html", "pantalla.html"}
# Páginas que no se precachean a propósito, con su motivo a la vista.
SIN_PRECACHE = {
    "admin.html": "exige sesión; sin conexión no sirve",
    "colegios.html": "material de clase para imprimir; el docente la abre con conexión",
    "datos.html": "catálogo para descargar datos; no es una herramienta de emergencia",
    "pantalla.html": "se abre en un equipo con red",
    "estado.html": "diagnóstico en vivo; sin conexión no hay estado que consultar",
}


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


def _paginas_sin_precache():
    shell = set(_rutas_precache())
    faltantes = []
    for pagina in sorted((ROOT / "web").glob("*.html")):
        ruta = "/" if pagina.name == "index.html" else f"/web/{pagina.name}"
        if ruta not in shell and pagina.name not in SIN_PRECACHE:
            faltantes.append(f"/web/{pagina.name}")
    return faltantes


def test_paginas_en_precache_o_justificadas():
    """Toda página de `web/` se abre sin conexión o está justificada en
    `SIN_PRECACHE`: una página nueva sin declarar debe romper el CI, no dar
    404 en el campo cuando no hay señal."""
    assert all(motivo.strip() for motivo in SIN_PRECACHE.values()), "SIN_PRECACHE: cada página excluida necesita su motivo"
    faltantes = _paginas_sin_precache()
    assert not faltantes, "; ".join(f"agrega {ruta} a SHELL en web/sw.js o justifícalo en SIN_PRECACHE" for ruta in faltantes)


def test_precache_solo_apunta_a_archivos_existentes():
    """`cache.add` corre con `allSettled`: una ruta rota se descarta en silencio
    y esa pantalla no abre sin señal. `/` la sirve el backend; el resto debe
    existir en el repo (bajo la raíz o bajo `web/`)."""
    rotas = []
    for ruta in _rutas_precache():
        if ruta == "/":
            continue
        rel = ruta.lstrip("/")
        if not (ROOT / rel).is_file() and not (ROOT / "web" / rel).is_file():
            rotas.append(ruta)
    assert not rotas, f"rutas de SHELL sin archivo en el repo: {rotas}"


def test_paginas_tienen_metadatos():
    for pagina in sorted((ROOT / "web").glob("*.html")):
        html = pagina.read_text(encoding="utf-8")
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


def _css_sin_comentarios(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def _trozos_media_899(css: str) -> tuple[str, str]:
    """Separa el interior de `@media (max-width: 899px)` del resto.

    Las llaves se cuentan balanceadas: un `}` interior no cierra el bloque.
    """
    limpio = _css_sin_comentarios(css)
    marca = "@media (max-width: 899px)"
    dentro: list[str] = []
    fuera: list[str] = []
    i = 0
    n = len(limpio)
    while i < n:
        j = limpio.find(marca, i)
        if j < 0:
            fuera.append(limpio[i:])
            break
        fuera.append(limpio[i:j])
        k = limpio.find("{", j)
        assert k != -1, "app.css: @media (max-width: 899px) sin llave de apertura"
        depth = 0
        p = k
        while p < n:
            if limpio[p] == "{":
                depth += 1
            elif limpio[p] == "}":
                depth -= 1
                if depth == 0:
                    dentro.append(limpio[k + 1:p])
                    i = p + 1
                    break
            p += 1
        else:
            raise AssertionError("app.css: bloque @media (max-width: 899px) sin cerrar")
    return "".join(dentro), "".join(fuera)


def _attrib_oculta(css: str) -> str | None:
    """Selector que nombra `.maplibregl-ctrl-attrib` y declara `display: none`."""
    i = 0
    n = len(css)
    while True:
        j = css.find("{", i)
        if j < 0:
            return None
        depth = 1
        p = j + 1
        while p < n and depth:
            if css[p] == "{":
                depth += 1
            elif css[p] == "}":
                depth -= 1
            p += 1
        prev = max(css.rfind("}", 0, j), css.rfind(";", 0, j))
        selector = css[prev + 1:j]
        propias = css[j + 1:p - 1].split("{", 1)[0]
        if re.search(r"\.maplibregl-ctrl-attrib(?![\w-])", selector) and re.search(r"display\s*:\s*none", propias):
            return " ".join(selector.split())
        i = j + 1


def test_mapa_mantiene_credito_visible():
    """MAPA-105: en escritorio el crédito de las capas base no se esconde tras el
    botón «i»: el control de atribución de MapLibre queda expandido (`compact: false`)
    y lleva su texto extra (límites y detecciones). En celular (≤899 px) la barra
    sobre el mapa se oculta solo dentro de ese `@media`; el crédito del fondo activo,
    con enlace, está en «Capas», en el panel y en «Calidad de los datos»."""
    js = MAP_JS.read_text(encoding="utf-8")
    assert "attributionControl:" in js, "map.js: sin control de atribución de MapLibre"
    assert "compact: false" in js, "map.js: la atribución no debe quedar colapsada"
    assert "customAttribution" in js, "map.js: falta el crédito de límites y detecciones"
    css = (ROOT / "web" / "css" / "app.css").read_text(encoding="utf-8")
    regla = ".maplibregl-ctrl-scale, .maplibregl-ctrl-attrib { display: none !important; }"
    dentro, fuera = _trozos_media_899(css)
    assert regla in dentro, (
        "app.css: la barra de atribución solo puede ocultarse dentro de @media (max-width: 899px)"
    )
    oculta = _attrib_oculta(fuera)
    assert oculta is None, f"app.css: `.maplibregl-ctrl-attrib` se oculta fuera del móvil: {oculta}"

    licencias = (ROOT / "web" / "data" / "licencias.json").read_text(encoding="utf-8")
    for url in (
        "https://openfreemap.org",
        "https://cloudless.eox.at",
        "https://opentopomap.org",
        "https://mapterhorn.com/attribution",
    ):
        assert url in licencias, f"licencias.json: falta el enlace del fondo {url}"
    calidad = (ROOT / "web" / "js" / "views" / "calidad.js").read_text(encoding="utf-8")
    assert "split(/(https:\\/\\/" in calidad, "calidad.js: las URL de la nota no se parten para enlazarlas"
    assert 'href="${part}"' in calidad, "calidad.js: la URL de la nota no queda en un enlace"
    vista = (ROOT / "web" / "js" / "views" / "mapa.js").read_text(encoding="utf-8")
    assert "function creditoFondoHtml" in vista, "mapa.js: falta el crédito del fondo activo"
    assert 'href="#/calidad"' in vista, "mapa.js: el crédito del fondo no enlaza a #/calidad"
    assert 'id="layers-basemap-credit"' in vista, "mapa.js: «Capas» no muestra el crédito del fondo"
    assert 'id="panel-basemap-credit"' in vista, "mapa.js: el panel no muestra el crédito del fondo"
    assert vista.find('data-capa="${c.key}"') < vista.find('id="layers-basemap-credit"'), (
        "mapa.js: el crédito del fondo debe ir después de las casillas de capa"
    )


def test_pantalla_publica_avisa_la_edad_del_dato():
    """PAN-21: la pantalla que un municipio deja encendida no puede aparentar datos
    frescos cuando no lo son: aviso visible con su `id` en el HTML y edad calculada
    con `freshness`/`stale` de /api/status, no con el reloj del navegador."""
    html = PANTALLA.read_text(encoding="utf-8")
    assert 'id="stale-banner"' in html, "pantalla.html: falta el nodo del aviso de datos viejos"
    js = PANTALLA_JS.read_text(encoding="utf-8")
    for marca in ("/api/status", "freshness", "stale", "Los datos no se actualizan"):
        assert marca in js, f"pantalla.js: falta {marca!r} (la edad del dato sale de /api/status)"


def test_admin_pestana_salud():
    """AUTO-09 (unificado en OPS-29): el panel de administración muestra la salud
    del servicio en su propia pestaña: el botón sigue el patrón `data-tab` +
    `aria-pressed` de las demás, la sección tiene encabezado propio y no trae
    scripts en línea (la CSP del repo no los permite). El detalle de la vista y
    de la consulta a /api/status lo vigila tests/test_admin_salud.py."""
    html = (ROOT / "web" / "admin.html").read_text(encoding="utf-8")
    assert 'data-tab="salud"' in html, "admin.html: falta la pestaña «Salud»"
    assert 'id="salud"' in html, 'admin.html: falta <section id="salud">'
    salud = html.split('id="salud"', 1)[1].split("</section>", 1)[0]
    assert "<h2" in salud, "la sección «salud» no tiene encabezado propio"
    assert "<script" not in salud, "la sección «salud» trae un <script> en línea"

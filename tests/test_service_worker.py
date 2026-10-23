"""FIX-35: el service worker debe cachear la cáscara completa, incluido el modo
liviano (/web/lite.html) y la hoja A4 (/web/lista.html), que son las vistas
pensadas para usarse con señal mala o sin conexión.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"

# MAPA-143: los polígonos del territorio son 2,28 MB sin comprimir. No se precargan: el mapa
# pide las comunas cuando las usa (límites, coropleta o comuna elegida) y la caché de la
# interfaz las guarda en esa primera visita. Precachearlas las bajaba dos veces en la primera.
POLIGONOS_FUERA_DEL_PRECACHE = ["/web/data/comunas.geojson", "/web/data/regiones.geojson"]

# Rutas GET de solo lectura que las vistas consumen y deben responder con el
# último dato guardado cuando no hay conexión (FIX-59).
RUTAS_API_CACHEABLES = [
    "/api/config",
    "/api/observations",
    "/api/risk",
    "/api/status",
    "/api/cases",
    "/api/places",
    "/api/alerts",
    "/api/reports",
    "/api/shared",
    "/api/incidents",
    "/api/official-fires",
    "/api/panorama",
    "/api/climate/enso",
]


def _array(nombre: str) -> set[str]:
    """Extrae un arreglo de rutas de web/sw.js."""
    fuente = (WEB / "sw.js").read_text(encoding="utf-8")
    match = re.search(rf"const\s+{nombre}\s*=\s*\[(.*?)\]", fuente, re.DOTALL)
    assert match, f"no se encontró el arreglo {nombre} en web/sw.js"
    return set(re.findall(r"'([^']+)'", match.group(1)))


def _shell() -> set[str]:
    return _array("SHELL")


def _cacheable_api() -> set[str]:
    return _array("CACHEABLE_API")


def _recursos_locales(html: str) -> set[str]:
    """Rutas locales (src/href absolutas al propio sitio) referenciadas en el HTML."""
    return {valor for valor in re.findall(r"""(?:src|href)=["']([^"']+)["']""", html) if valor.startswith("/")}


def test_api_cacheable_cubre_rutas_de_lectura():
    cacheable = _cacheable_api()
    faltantes = [ruta for ruta in RUTAS_API_CACHEABLES if ruta not in cacheable]
    assert not faltantes, f"faltan en CACHEABLE_API de web/sw.js: {faltantes}"


def test_poligonos_del_territorio_no_se_precargan():
    """MAPA-143: los 2,28 MB de polígonos salen del precache; la caché de /web/ los guarda
    la primera vez que el mapa los pide, así que sin conexión siguen estando tras esa visita."""
    shell = _shell()
    dentro = [ruta for ruta in POLIGONOS_FUERA_DEL_PRECACHE if ruta in shell]
    assert not dentro, f"vuelven al precache de web/sw.js: {dentro}"
    fuente = (WEB / "sw.js").read_text(encoding="utf-8")
    assert "url.pathname.startsWith('/web/')" in fuente, "la caché de interfaz ya no guarda lo que pide el mapa"


def test_recursos_de_lite_y_lista_cacheables():
    shell = _shell()
    for pagina in ("lite.html", "lista.html"):
        html = (WEB / pagina).read_text(encoding="utf-8")
        for recurso in _recursos_locales(html):
            if recurso.startswith("/api/"):
                continue  # rutas de API: las cubre la caché dinámica CACHEABLE_API
            assert recurso in shell, f"{pagina} referencia {recurso}, que no está en SHELL de web/sw.js (quedaría sin respuesta offline)"


# Número de entradas de SHELL fijado hoy: un borrado accidental salta aunque
# las rutas que queden sigan existiendo. Bajó de 61 a 59 con MAPA-143 (los dos
# polígonos del territorio salieron del precache) y subió a 60 con PRIV-03
# (/web/js/recibo.js: el recibo de lo guardado se arma en el cliente, así que
# también tiene que estar sin conexión). 2026-10-21: +1 — /web/js/escenario.js
# (FUEGO-26: el escenario en palabras se arma en el cliente y viaja sin conexión).
# 2026-10-22: +1 — /web/js/buscador.js (MAPA-21: el buscador de comunas del panel
# de capas viaja con el SHELL para que el mapa siga armándose sin señal)
# y +1 — /web/js/pildora.js (PILDORA-01: la píldora de la cabecera evalúa los
# cinco estados en el cliente).
# 2026-10-23: +1 — /web/js/spreadtext.js (FUEGO-14: el escenario en palabras de
# vecino se arma en el cliente y la ficha tiene que seguir abriendo sin señal).
SHELL_ENTRADAS_HOY = 73


def test_shell_solo_apunta_a_rutas_publicas():
    """FIX-98: cada entrada de SHELL apunta a /web/ (salvo la raíz y el manifiesto).
    Que el archivo exista lo cubre test_estaticas_guardas.py; aquí queda la ruta pública."""
    for ruta in _shell():
        assert ruta in ("/", "/manifest.webmanifest") or ruta.startswith("/web/"), f"ruta fuera de /web/ en SHELL de web/sw.js: {ruta}"


def test_shell_numero_de_entradas():
    """Un borrado accidental de una entrada rompe la prueba aunque las que
    queden sigan existiendo; agregar una exige actualizar SHELL_ENTRADAS_HOY."""
    assert len(_shell()) == SHELL_ENTRADAS_HOY


# OPS-26: /web/lite.html, /web/lista.html y /web/respuesta.html figuran en
# SHELL pero hoy no se guardan en producción, porque esas URL redirigen y el
# cache.add termina en 404. La guarda no las marca porque los archivos sí
# existen en el repo; hay que volver a medirlas cuando OPS-26 se resuelva.

"""FIX-35: el service worker debe cachear la cáscara completa, incluido el modo
liviano (/web/lite.html) y la hoja A4 (/web/lista.html), que son las vistas
pensadas para usarse con señal mala o sin conexión.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"

RUTAS_LIGERAS = [
    "/web/lite.html",
    "/web/js/lite.js",
    "/web/lista.html",
    "/web/css/lista.css",
]

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


def _shell() -> set[str]:
    """Extrae el arreglo SHELL de web/sw.js."""
    fuente = (WEB / "sw.js").read_text(encoding="utf-8")
    match = re.search(r"const\s+SHELL\s*=\s*\[(.*?)\]", fuente, re.DOTALL)
    assert match, "no se encontró el arreglo SHELL en web/sw.js"
    return set(re.findall(r"'([^']+)'", match.group(1)))


def _cacheable_api() -> set[str]:
    """Extrae el arreglo CACHEABLE_API de web/sw.js."""
    fuente = (WEB / "sw.js").read_text(encoding="utf-8")
    match = re.search(r"const\s+CACHEABLE_API\s*=\s*\[(.*?)\]", fuente, re.DOTALL)
    assert match, "no se encontró el arreglo CACHEABLE_API en web/sw.js"
    return set(re.findall(r"'([^']+)'", match.group(1)))


def _recursos_locales(html: str) -> set[str]:
    """Rutas locales (src/href absolutas al propio sitio) referenciadas en el HTML."""
    return {valor for valor in re.findall(r"""(?:src|href)=["']([^"']+)["']""", html) if valor.startswith("/")}


def test_shell_incluye_modo_liviano_y_lista():
    shell = _shell()
    faltantes = [ruta for ruta in RUTAS_LIGERAS if ruta not in shell]
    assert not faltantes, f"faltan en SHELL de web/sw.js: {faltantes}"


def test_api_cacheable_cubre_rutas_de_lectura():
    cacheable = _cacheable_api()
    faltantes = [ruta for ruta in RUTAS_API_CACHEABLES if ruta not in cacheable]
    assert not faltantes, f"faltan en CACHEABLE_API de web/sw.js: {faltantes}"


def test_recursos_de_lite_y_lista_cacheables():
    shell = _shell()
    for pagina in ("lite.html", "lista.html"):
        html = (WEB / pagina).read_text(encoding="utf-8")
        for recurso in _recursos_locales(html):
            if recurso.startswith("/api/"):
                continue  # rutas de API: las cubre la caché dinámica CACHEABLE_API
            assert recurso in shell, f"{pagina} referencia {recurso}, que no está en SHELL de web/sw.js (quedaría sin respuesta offline)"


# Número de entradas de SHELL fijado hoy: un borrado accidental salta aunque
# las rutas que queden sigan existiendo.
SHELL_ENTRADAS_HOY = 61


def _sin_archivo(rutas: set[str]) -> list[str]:
    """Entradas que no existen como archivo en el repo. `/` la sirve el
    backend; `/manifest.webmanifest` vive bajo web/ como el resto."""
    return sorted(
        ruta for ruta in rutas if ruta != "/" and not (ROOT / ruta.lstrip("/")).is_file() and not (WEB / ruta.lstrip("/")).is_file()
    )


def test_shell_solo_apunta_a_archivos_que_existen():
    """FIX-98: cada entrada de SHELL apunta a /web/ (salvo la raíz y el
    manifiesto) y existe en el árbol del repo. `cache.add` corre con
    `allSettled`, así que una ruta fantasma no rompe el install: se descarta
    en silencio y esa pantalla no abre sin señal."""
    shell = _shell()
    for ruta in shell:
        assert ruta == "/" or ruta == "/manifest.webmanifest" or ruta.startswith("/web/"), (
            f"ruta fuera de /web/ en SHELL de web/sw.js: {ruta}"
        )
    faltantes = _sin_archivo(shell)
    assert not faltantes, f"rutas de SHELL sin archivo en el repo: {faltantes}"


def test_shell_numero_de_entradas():
    """Un borrado accidental de una entrada rompe la prueba aunque las que
    queden sigan existiendo; agregar una exige actualizar SHELL_ENTRADAS_HOY."""
    assert len(_shell()) == SHELL_ENTRADAS_HOY


def test_guarda_detecta_rutas_fantasma():
    """Caso mutado en memoria: una entrada inexistente en SHELL debe romper
    la guarda nombrando esa ruta."""
    mutado = _shell() | {"/web/js/no-existe.js"}
    assert "/web/js/no-existe.js" in _sin_archivo(mutado)


# OPS-26: /web/lite.html, /web/lista.html y /web/respuesta.html figuran en
# SHELL pero hoy no se guardan en producción, porque esas URL redirigen y el
# cache.add termina en 404. La guarda no las marca porque los archivos sí
# existen en el repo; hay que volver a medirlas cuando OPS-26 se resuelva.

"""MOV-01: la portada precarga el grafo estático de módulos y el vigilante
del arranque distingue conexión lenta de falla real.

En Slow 3G la cascada de imports de app.js (4-5 niveles × ~2 s de latencia)
dejaba a la app pintando recién a los ~16 s y el vigilante PORTADA-02 mostraba
«BRASA no pudo cargar» aunque la app sí estaba cargando. Dos guardas:

- Los `<link rel="modulepreload">` de index.html deben coincidir exactamente
  con los imports estáticos transitivos de web/js/app.js (sin app.js, que ya
  la pide el `<script type="module">`), para que la lista no se pudra cuando
  cambie el grafo.
- El aviso #arranque-lento existe y la pantalla «no pudo cargar» no puede
  aparecer por tiempo antes de los 45 s.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "local"))
import peso_arranque  # noqa: E402

from backend.settings import ROOT  # noqa: E402

INDEX = ROOT / "web" / "index.html"
APP = ROOT / "web" / "js" / "app.js"


def _html() -> str:
    return INDEX.read_text(encoding="utf-8")


def _precargas() -> list[str]:
    """Los href de cada <link rel="modulepreload"> del <head>."""
    return [
        m.group(1)
        for tag in re.findall(r"<link\b[^>]*>", _html(), re.I)
        if re.search(r'rel=["\']modulepreload["\']', tag, re.I)
        for m in [re.search(r'href=["\']([^"\']+)["\']', tag)]
        if m
    ]


def test_modulepreload_cubre_el_grafo_estatico():
    """La lista de modulepreload de index.html debe ser exactamente el grafo de
    imports estáticos de app.js: ni un módulo de más (precarga al vicio) ni uno
    de menos (sigue pagando la cascada en red lenta)."""
    grafo = peso_arranque.modulos_arranque([APP], ROOT)
    esperados = {"/" + m.relative_to(ROOT).as_posix() for m in grafo} - {"/web/js/app.js"}
    assert esperados, "el grafo estático de app.js quedó vacío: revisar peso_arranque.modulos_arranque"
    assert set(_precargas()) == esperados, (
        "modulepreload de index.html desactualizado: "
        f"faltan {sorted(esperados - set(_precargas()))}, "
        f"sobran {sorted(set(_precargas()) - esperados)}"
    )


def test_modulepreload_sin_duplicados():
    precargas = _precargas()
    assert len(precargas) == len(set(precargas)), f"modulepreload duplicados: {precargas}"


def test_vigia_presente_y_fallo_por_tiempo_a_los_45s():
    """El «no pudo cargar» no puede aparecer por tiempo antes de los 45 s:
    a los 15 s lo que corre es el aviso de conexión lenta."""
    html_sin_noscript = re.sub(r"<noscript>.*?</noscript>", "", _html(), flags=re.S)
    guiones = re.findall(r"<script\b[^>]*>(.*?)</script>", html_sin_noscript, re.S | re.I)
    vigias = [g for g in guiones if "arranque-fallido" in g]
    assert vigias, "index.html sin guion en línea que vigile #arranque-fallido"
    cuerpo = vigias[0]
    assert "45000" in cuerpo, "la pantalla de fallo debe esperar a los 45 s"
    assert "15000" in cuerpo, "a los 15 s corre el aviso de conexión lenta, no la falla"
    assert "30000" not in cuerpo, "ya no hay un segundo chequeo de falla a los 30 s"


def test_aviso_conexion_lenta_existe_y_nace_oculto():
    tag = re.search(r'<div\b[^>]*\bid="arranque-lento"[^>]*>', _html())
    assert tag, 'index.html sin <div id="arranque-lento">'
    assert "hidden" in tag.group(0), "el aviso de conexión lenta debe nacer oculto"
    bloque = re.search(r'<div\b[^>]*\bid="arranque-lento"[^>]*>(.*?)</div>\s*(?=<script)', _html(), re.S)
    assert bloque, "bloque #arranque-lento vacío"
    contenido = bloque.group(1)
    assert "conexión está lenta" in contenido
    assert "no pudo cargar" not in contenido, "el aviso de conexión lenta no puede sonar a falla"
    for tel in ("130", "132"):
        assert f'href="tel:{tel}"' in contenido, f"aviso sin enlace tel:{tel}"
    assert 'href="/web/lite.html"' in contenido, "aviso sin enlace a la versión liviana"
    assert 'href="/focos.html"' in contenido, "aviso sin enlace a la lista de focos"


def test_maplibre_css_viaja_con_el_motor_no_en_el_head():
    """El CSS de MapLibre bloqueaba el primer pintado aunque la portada no lo
    necesita: se fue del <head> y lo inyecta ensureMap() junto al motor."""
    head = _html().split("</head>", 1)[0]
    assert "maplibre-gl.css" not in head, "maplibre-gl.css sigue bloqueando el <head>"
    app = APP.read_text(encoding="utf-8")
    assert "maplibre-gl.css" in app, "app.js debe inyectar maplibre-gl.css al pedir el motor del mapa"
    # Antes de app.css: si va después, sus reglas le ganan a los ajustes de app.css (MOV-02).
    assert "insertBefore(css, document.querySelector(" in app and 'link[href="/web/css/app.css"]' in app

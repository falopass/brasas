"""VIS-01: guardas de la legibilidad y el uso del mapa en teléfono y escritorio.

La medición en producción (Playwright, 360/390 px táctil y 1280 px,
11-nov-2026) encontró:

- los aria-label/title de los controles de MapLibre en inglés («Find my
  location», «Zoom in»…): ``web/js/map.js`` debe pasar ``locale`` al ``Map``
  con los textos en español, con las claves del defaultLocale del
  ``web/vendor/maplibre/maplibre-gl.js`` que sirve el repo;
- la edad del dato junto a «Actualizar» (``.refresh-age``) a 9,4 px
  (.625 rem) y los títulos de grupo de «Capas»/«Filtros» a 11,25 px
  (.75 rem): ningún texto del mapa puede bajar de 0,8 rem (12 px con la
  raíz en 15 px);
- el ícono de «Actualizar» casi invisible: tinta #333 sobre el fondo oscuro
  ``--ov-bg``: el botón usa ``--ov-ink``;
- el buscador del mapa sin atributos que apaguen la autocorrección del
  teclado del teléfono ni navegación por flechas: ``#map-search`` exige
  ``autocorrect``, ``spellcheck``, ``autocapitalize`` en off e
  ``inputmode="search"``, y la lista se recorre con el teclado.
"""
from __future__ import annotations

import re

from backend.settings import ROOT

JS_MAPA = (ROOT / "web" / "js" / "map.js").read_text(encoding="utf-8")
JS_VISTA = (ROOT / "web" / "js" / "views" / "mapa.js").read_text(encoding="utf-8")
CSS = re.sub(r"/\*.*?\*/", "", (ROOT / "web" / "css" / "app.css").read_text(encoding="utf-8"), flags=re.S)

# Claves del defaultLocale de web/vendor/maplibre/maplibre-gl.js (buscar el
# objeto con «GeolocateControl.FindMyLocation»); los valores por defecto que
# no deben volver a aparecer en el locale del mapa.
CLAVES_LOCALE = {
    "AttributionControl.MapFeedback",
    "AttributionControl.ToggleAttribution",
    "FullscreenControl.Enter",
    "FullscreenControl.Exit",
    "GeolocateControl.FindMyLocation",
    "GeolocateControl.LocationNotAvailable",
    "LogoControl.Title",
    "Map.Title",
    "Marker.Title",
    "NavigationControl.ResetBearing",
    "NavigationControl.ZoomIn",
    "NavigationControl.ZoomOut",
    "Popup.Close",
    "ScaleControl.Feet",
    "ScaleControl.Kilometers",
    "ScaleControl.Meters",
    "ScaleControl.Miles",
    "ScaleControl.NauticalMiles",
    "TerrainControl.Disable",
    "TerrainControl.Enable",
}
EN_INGLES = {
    "GeolocateControl.FindMyLocation": "Find my location",
    "NavigationControl.ZoomIn": "Zoom in",
    "NavigationControl.ZoomOut": "Zoom out",
}


def _locale_del_mapa() -> dict[str, str]:
    """Pares clave→texto del objeto `locale` pasado al Map."""
    return dict(
        re.findall(
            r"'((?:AttributionControl|FullscreenControl|GeolocateControl|LogoControl|Map|Marker|NavigationControl|Popup|ScaleControl|TerrainControl)\.[A-Za-z]+)'\s*:\s*'([^']+)'",
            JS_MAPA,
        )
    )


def test_map_recibe_locale() -> None:
    i = JS_MAPA.index("new maplibregl.Map({")
    assert "locale:" in JS_MAPA[i : i + 800], "map.js: el Map no recibe `locale`"


def test_locale_cubre_los_controles_en_espanol() -> None:
    pares = _locale_del_mapa()
    assert pares, "map.js: no se encontró un objeto locale con claves de control"
    faltan = CLAVES_LOCALE - pares.keys()
    assert not faltan, f"map.js: claves de locale sin texto en español: {sorted(faltan)}"
    for clave, ingles in EN_INGLES.items():
        assert pares[clave] != ingles, f"map.js: {clave} sigue en inglés"


def test_buscador_sin_autocorreccion() -> None:
    m = re.search(r"<input[^>]*id=\"map-search\"[^>]*>", JS_VISTA)
    assert m, "mapa.js: no se encontró el input #map-search"
    etiqueta = m.group(0)
    for atributo, valor in {
        "autocapitalize": "off",
        "autocorrect": "off",
        "spellcheck": "false",
        "inputmode": "search",
        "autocomplete": "off",
    }.items():
        assert f'{atributo}="{valor}"' in etiqueta, f"mapa.js: #map-search sin {atributo}=\"{valor}\""


def test_buscador_navegable_con_teclado() -> None:
    """Enter elige el primer resultado y las flechas recorren la lista."""
    bloque = JS_VISTA[JS_VISTA.index("function bindBuscarComuna"):]
    assert re.search(r"key === 'ArrowDown'[\s\S]{0,200}\.focus\(\)", bloque)
    assert re.search(r"key === 'Enter' && hits\.length[\s\S]{0,120}elegir\(0\)", bloque)
    assert re.search(r"key === 'ArrowUp'[\s\S]{0,320}search\)?\.focus\(\)", bloque)
    assert "key === 'Escape'" in bloque


def test_refresh_age_no_baja_de_12px() -> None:
    """Ninguna regla `.refresh-age` declara un font-size menor a 0,8 rem."""
    tamanos = [
        (float(v), u)
        for _, cuerpo in re.findall(r"([^{}]*\.refresh-age[^{}]*)\{([^{}]*)\}", CSS)
        for v, u in re.findall(r"font-size\s*:\s*([0-9.]+)\s*(rem|px)", cuerpo)
    ]
    assert tamanos, "app.css: `.refresh-age` sin font-size"
    for valor, unidad in tamanos:
        px = valor * 15 if unidad == "rem" else valor
        assert px >= 12, f"app.css: `.refresh-age` baja de 12 px ({valor}{unidad})"


def test_icono_actualizar_sobre_tinta_clara() -> None:
    """El ícono de «Actualizar» usa la tinta del overlay, no un gris oscuro."""
    m = re.search(r"\.map-refresh button\s*\{([^}]*)\}", CSS)
    assert m and "color: var(--ov-ink)" in m.group(1)


def test_titulos_de_grupo_no_bajan_de_12px() -> None:
    """«Fondo»/«Fuego»/«Contexto»/«Desde cuándo» ≥12 px dentro de los controles."""
    m = re.search(
        r"\.map-layers \.layers-group-title,\s*\.map-filters \.layers-group-title\s*\{([^}]*)\}",
        CSS,
    )
    assert m, "app.css: falta la regla acotada de .layers-group-title"
    assert "font-size: 0.8rem" in m.group(1)

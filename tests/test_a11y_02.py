"""A11Y-02: guardas de la auditoría de accesibilidad del 11-nov-2026.

La medición en navegador real (390×844 con letra al 200 %, tema claro y oscuro,
nivel sencillo y técnico) encontró dos desbordes y un título compartido:

- ``web/lite.html``: la fila de marca (``.brand-row``) no envolvía y el título
  más el botón «Actualizar» empujaban el ancho de la página (scrollW 423 en
  390 px). Ahora la fila envuelve y el ``h1`` puede encogerse.
- ``web/datos.html``: la lista de definición de «Límites»
  (``grid-template-columns: max-content 1fr``) dejaba la descripción fuera del
  viewport (scrollW 436 en 390 px). En pantalla angosta la lista se apila.
- ``web/js/views/riesgo.js``: la ficha de comuna compartía el <title> «Riesgo»
  con la vista general. La ficha nombra la comuna.

Cada prueba lee el archivo como texto, como hacen test_vista_mapa.py y
test_vis02_fichas.py.
"""
from __future__ import annotations

import re

from backend.settings import ROOT

LITE = (ROOT / "web" / "lite.html").read_text(encoding="utf-8")
DATOS = (ROOT / "web" / "datos.html").read_text(encoding="utf-8")
RIESGO = (ROOT / "web" / "js" / "views" / "riesgo.js").read_text(encoding="utf-8")


def test_lite_brand_row_envuelve_a_200_porciento() -> None:
    fila = re.search(r"\.brand-row\s*\{([^}]*)\}", LITE)
    assert fila, "lite.html: no se encontró la regla .brand-row"
    assert "flex-wrap" in fila.group(1), ".brand-row no envuelve: a 200 % desborda el ancho"
    sel = re.search(r"\.brand-row\s+\.brand\s*\{([^}]*)\}", LITE)
    assert sel and "min-width" in sel.group(1), ".brand-row .brand sin min-width: el h1 no puede encogerse en flex"


def test_datos_dl_se_apila_en_pantalla_angosta() -> None:
    media = re.search(r"@media\s*\([^)]*max-width[^)]*\)\s*\{[^}]*dl\s*\{([^}]*)\}", DATOS)
    assert media, "datos.html: falta el @media que apila la dl de «Límites»"
    assert "grid-template-columns" in media.group(1) and "1fr" in media.group(1), \
        "la dl de datos.html sigue en dos columnas en pantalla angosta"


def test_riesgo_ficha_nombra_la_comuna_en_el_titulo() -> None:
    assert "document.title" in RIESGO, "riesgo.js no ajusta document.title"
    assert re.search(r"document\.title\s*=\s*`\$\{data\.comuna\.name\}", RIESGO), \
        "la ficha de riesgo no nombra la comuna en el <title>"

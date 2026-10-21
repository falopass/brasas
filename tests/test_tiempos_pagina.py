"""Medidor de tiempos de carga del e2e (REND-01): la lógica pura vive en
`scripts/local/tiempos_pagina.py` y `browser_checks.py` solo recolecta las marcas
(marca de navegación + LCP vía PerformanceObserver). Estas pruebas cubren el resumen
que la revisión imprime: mediana por página, la marca «lenta» sobre LCP 2,5 s y la
tabla — sin navegador ni servidor.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "local"))
import tiempos_pagina  # noqa: E402


def m(pagina, **marcas):
    return {"pagina": pagina, **marcas}


def test_resumen_groups_measurements_by_page_and_takes_the_median():
    mediciones = [
        m("riesgo", ttfb=40, dcl=300, carga=900, lcp=1200),
        m("riesgo", ttfb=50, dcl=320, carga=1000, lcp=1400),
        m("riesgo", ttfb=45, dcl=310, carga=950, lcp=1300),
        m("mapa", ttfb=30, dcl=200, carga=600, lcp=800),
    ]
    filas = {f["pagina"]: f for f in tiempos_pagina.resumen(mediciones)}
    assert filas["riesgo"]["lcp"] == 1300 and filas["riesgo"]["carga"] == 950 and filas["riesgo"]["n"] == 3
    assert filas["mapa"]["lcp"] == 800 and filas["mapa"]["n"] == 1


def test_resumen_orders_pages_slowest_first():
    filas = tiempos_pagina.resumen([m("rapida", lcp=900), m("lenta", lcp=3000), m("media", lcp=1800)])
    assert [f["pagina"] for f in filas] == ["lenta", "media", "rapida"]


def test_a_page_over_the_lcp_reference_is_flagged_lenta_without_failing():
    lenta = tiempos_pagina.resumen([m("lenta", lcp=tiempos_pagina.LCP_LENTO_MS + 1)])
    assert lenta[0]["lenta"] is True
    justa = tiempos_pagina.resumen([m("justa", lcp=tiempos_pagina.LCP_LENTO_MS)])
    assert justa[0]["lenta"] is False


def test_pages_without_lcp_do_not_break_the_summary():
    filas = tiempos_pagina.resumen([m("sin-lcp", ttfb=10, dcl=100, carga=200, lcp=None)])
    assert filas[0]["lcp"] is None and filas[0]["lenta"] is False
    assert "sin-lcp" in tiempos_pagina.tabla(filas)


def test_tabla_marks_the_slow_page_and_keeps_every_page():
    filas = tiempos_pagina.resumen([m("rapida", lcp=900), m("morosa", lcp=3000)])
    lineas = {linea.split()[0]: linea for linea in tiempos_pagina.tabla(filas).splitlines() if linea.strip()}
    assert "morosa" in lineas and "rapida" in lineas
    assert lineas["morosa"].endswith("← lenta")
    assert not lineas["rapida"].endswith("← lenta")

"""Tiempos de carga por página, medidos en el navegador del e2e (REND-01).

El presupuesto de peso (presupuesto_peso.py, peso_arranque.py) mide bytes, no tiempo:
este módulo resume lo que browser_checks.py recolecta en cada pasada —la marca de
navegación y el LCP leído con un PerformanceObserver instalado antes de cargar— y lo
imprime como tabla informativa.

Nunca hace fallar la revisión: la referencia publicada es LCP ≤ 2,5 s en la emulación
local y las páginas sobre esa marca se rotulan «lenta» para notar regresiones gruesas
entre PRs sin bloquear el merge por el ruido de un runner compartido.
"""

from __future__ import annotations

import statistics
from typing import Any

LCP_LENTO_MS = 2500

# Marcas recolectadas por el navegador, en ms desde el inicio de la navegación.
CAMPOS = ("ttfb", "dcl", "carga", "lcp")


def _mediana(valores: list[float | None]) -> int | None:
    vals = [v for v in valores if v is not None]
    return round(statistics.median(vals)) if vals else None


def resumen(mediciones: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Mediana por página de cada marca (TTFB, DOMContentLoaded, load y LCP).

    `mediciones` son dicts con `pagina` y las marcas en ms (pueden venir en None cuando
    el navegador no las produjo). Devuelve una fila por página, ordenadas de la más
    lenta a la más rápida según el LCP mediano; `lenta` marca LCP > LCP_LENTO_MS.
    """
    por_pagina: dict[str, list[dict[str, Any]]] = {}
    for m in mediciones:
        por_pagina.setdefault(m["pagina"], []).append(m)
    filas = []
    for pagina, grupo in por_pagina.items():
        fila = {"pagina": pagina, "n": len(grupo)}
        for campo in CAMPOS:
            fila[campo] = _mediana([g.get(campo) for g in grupo])
        fila["lenta"] = fila["lcp"] is not None and fila["lcp"] > LCP_LENTO_MS
        filas.append(fila)
    filas.sort(key=lambda f: -(f["lcp"] if f["lcp"] is not None else -1))
    return filas


def _ms(v: int | None) -> str:
    return "—" if v is None else str(v)


def tabla(filas: list[dict[str, Any]]) -> str:
    """Tabla de texto para la salida del e2e; las páginas lentas llevan marca."""
    lineas = [f"  {'página':28s} {'ttfb':>6s} {'dcl':>6s} {'carga':>6s} {'lcp':>6s}"]
    for f in filas:
        marca = "  ← lenta" if f["lenta"] else ""
        lineas.append(f"  {f['pagina']:28s} {_ms(f['ttfb']):>6s} {_ms(f['dcl']):>6s} {_ms(f['carga']):>6s} {_ms(f['lcp']):>6s}{marca}")
    return "\n".join(lineas)

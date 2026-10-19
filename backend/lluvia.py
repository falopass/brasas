"""Lluvia horaria e isoterma 0 °C: el insumo del aviso de aluvión (AGUA-03A).

Tras un incendio el suelo quemado absorbe menos agua, así que lo que importa no es el
acumulado del día sino cuánta lluvia cae en pocas horas y a qué altura está la isoterma
0 °C: si está muy alta, en la cordillera cae lluvia en vez de nieve y el agua escurre de
inmediato hacia las quebradas.

La serie horaria viene del pronóstico de Open-Meteo (`forecast_hourly` con
`extra_vars=["precipitation", "freezing_level_height"]`), con `time` en UTC.

Los umbrales son iniciales y están pendientes de calibración con datos chilenos
(intensidades de DMC/DGA y la isoterma de los aluviones documentados). Por ahora la
señal solo marca la peor ventana de lluvia: no gatilla ningún aviso todavía.
"""
from __future__ import annotations

from typing import Any

VENTANA_HORAS = 3
MM_3H_INTENSA = 10.0      # mm en 3 horas: umbral inicial de «lluvia intensa», por calibrar
ISOTERMA_ALTA_M = 2500.0  # sobre esta altura la isoterma se informa como alta; no decide la señal


def _hora(valor: Any) -> float | None:
    """Una lectura horaria válida (número real, no booleano) o None."""
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return None
    return float(valor)


def ventana(hourly: dict[str, Any]) -> dict[str, Any] | None:
    """La peor ventana de VENTANA_HORAS horas: {mm_3h, inicio, isoterma_m}.

    `mm_3h` es la mayor suma de `precipitation` en 3 horas seguidas e `inicio` la marca
    `time` de su primera hora. `isoterma_m` es la `freezing_level_height` de la hora
    central de esa ventana; None si esa hora no trae dato.

    Devuelve None cuando no hay ventana evaluable: sin `precipitation`, con menos de
    VENTANA_HORAS horas o con algún `None` en la serie, porque un hueco puede esconder
    la verdadera peor ventana y BRASA nunca inventa una lectura.
    """
    times = hourly.get("time") or []
    mm = hourly.get("precipitation") or []
    isoterma = hourly.get("freezing_level_height") or []
    horas = min(len(times), len(mm))
    if any(_hora(mm[i]) is None for i in range(horas)):
        return None
    mejor = None
    for i in range(horas - VENTANA_HORAS + 1):
        total = round(sum(float(mm[j]) for j in range(i, i + VENTANA_HORAS)), 1)
        central = i + VENTANA_HORAS // 2
        iso = _hora(isoterma[central]) if central < len(isoterma) else None
        if mejor is None or total > mejor["mm_3h"]:
            mejor = {"mm_3h": total, "inicio": times[i], "isoterma_m": iso}
    return mejor


def senal(hourly: dict[str, Any]) -> dict[str, Any]:
    """Resumen para el futuro aviso de aluvión.

    {"mm_3h": float|None, "isoterma_m": float|None, "intensa": bool, "ventana": str|None}.
    `intensa` es mm_3h >= MM_3H_INTENSA; la isoterma alta (>= ISOTERMA_ALTA_M) se informa
    en `isoterma_m` pero no decide la señal. Sin datos los campos quedan en None e
    `intensa` en False; si las series no permiten evaluar ninguna ventana, `ventana` es None.
    """
    peor = ventana(hourly)
    if peor is None:
        return {"mm_3h": None, "isoterma_m": None, "intensa": False, "ventana": None}
    return {"mm_3h": peor["mm_3h"], "isoterma_m": peor["isoterma_m"],
            "intensa": peor["mm_3h"] >= MM_3H_INTENSA, "ventana": peor["inicio"]}

"""Comparador de riesgo semana a semana: el pronóstico de hoy contra el de hace siete días.

El pronóstico de una comuna se sobrescribe cada vez que el cron recalcula, así que sin una foto
diaria no se puede responder «¿el viernes viene peor que lo que decíamos la semana pasada?».
`risk_snapshot` guarda esa foto; este módulo es la parte que compara.

Lo que compara son **dos pronósticos para el mismo día**, emitidos con siete días de diferencia:
mide cómo cambió la expectativa, no lo que pasó en el cerro. Por eso todas las frases hablan de
pronóstico y ninguna dice que vaya a haber un incendio.
"""

from __future__ import annotations

from typing import Any

from backend.risk import RANK

CHANGE_LABELS = {
    "sube": "Más alto que el pronóstico de la semana pasada",
    "baja": "Más bajo que el pronóstico de la semana pasada",
    "igual": "Igual que el pronóstico de la semana pasada",
    "sin_anterior": "No hay pronóstico de la semana pasada para ese día",
}

MISSING_LABELS = {
    "hoy": "Hoy no hay pronóstico para ese día",
    "semana_pasada": "No hay pronóstico de la semana pasada para ese día",
    "ambos": "No hay pronóstico ni de hoy ni de la semana pasada",
}


def rank(level: str | None) -> int | None:
    """Posición del nivel en la escala, o None si no hay nivel reconocible."""
    return RANK.get(level) if level else None


def compare(current: str | None, previous: str | None) -> str | None:
    """Qué pasó entre los dos pronósticos del mismo día: sube, baja, igual o None si falta alguno."""
    now_rank, then_rank = rank(current), rank(previous)
    if now_rank is None or then_rank is None:
        return None
    if now_rank > then_rank:
        return "sube"
    if now_rank < then_rank:
        return "baja"
    return "igual"


def row(target_date: str, current: dict[str, Any] | None, previous: dict[str, Any] | None) -> dict[str, Any]:
    """Una fila del comparador: los dos niveles, qué falta, el cambio y la fecha del pronóstico viejo."""
    current_level = (current or {}).get("level_combined") or (current or {}).get("level")
    previous_level = (previous or {}).get("level_combined") or (previous or {}).get("level")
    if rank(current_level) is None:
        missing = "ambos" if rank(previous_level) is None else "hoy"
    elif rank(previous_level) is None:
        missing = "semana_pasada"
    else:
        missing = None
    change = compare(current_level, previous_level) or "sin_anterior"
    return {
        "target_date": target_date,
        "current": current_level,
        "previous": previous_level,
        "change": change,
        "change_label": MISSING_LABELS[missing] if missing else CHANGE_LABELS[change],
        "missing": missing,
        "previous_at": (previous or {}).get("snapshot_date"),
        "current_score": (current or {}).get("score"),
        "previous_score": (previous or {}).get("score"),
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Cuántos días suben, bajan, siguen igual, no se comparan o no tienen pronóstico de hoy."""
    out = {"sube": 0, "baja": 0, "igual": 0, "sin_anterior": 0, "sin_hoy": 0}
    for item in rows:
        out[item["change"]] = out.get(item["change"], 0) + 1
        if item.get("missing") in ("hoy", "ambos"):
            out["sin_hoy"] += 1
    return out

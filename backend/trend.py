"""Comparador de riesgo semana a semana: el pronóstico de hoy contra el de hace siete días.

El pronóstico de una comuna se sobrescribe cada vez que el cron recalcula, así que sin una foto
diaria no se puede responder «¿el viernes viene peor que lo que decíamos la semana pasada?».
`risk_snapshot` guarda esa foto; este módulo es la parte que compara.

Lo que compara son **dos pronósticos para el mismo día**, emitidos con siete días de diferencia:
mide cómo cambió la expectativa, no lo que pasó en el cerro. Por eso todas las frases hablan de
pronóstico y ninguna dice que vaya a haber un incendio.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

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
        # Un cambio desconocido no se compara y no debe inventar contadores nuevos.
        change = item.get("change")
        out[change if change in CHANGE_LABELS else "sin_anterior"] += 1
        if item.get("missing") in ("hoy", "ambos"):
            out["sin_hoy"] += 1
    return out


CHILE_TZ = ZoneInfo("America/Santiago")

METODO = (
    "Compara el pronóstico de cada día con el que BRASA emitió exactamente 7 días antes "
    "para ese mismo día (tabla risk_snapshot). Mide cómo cambió la expectativa: no es lo "
    "que pasó en el cerro ni afirma que habrá un incendio."
)


def compute(db, comuna_code: int, weeks: int = 1, today: str | None = None) -> dict[str, Any]:
    """El comparador completo de una comuna: mismas consultas que `/api/risk/{code}/trend`.

    Lo usan la ruta pública y el resumen de lugar (`build_summary`), así Mi zona y el
    enlace de familia leen la comparación sin otra llamada.
    """
    today = today or datetime.now(CHILE_TZ).date().isoformat()
    current = {
        r["date"]: {"level": r["level"], "level_combined": r["level_combined"], "score": r["score"]}
        for r in db.query(
            "SELECT date, level, level_combined, score FROM risk_daily WHERE comuna_code = ? AND date >= ?", (comuna_code, today)
        )
    }
    previous: dict[str, dict] = {}
    offset_days = weeks * 7
    for r in db.query(
        "SELECT snapshot_date, target_date, level, level_combined, score FROM risk_snapshot "
        "WHERE comuna_code = ? ORDER BY snapshot_date DESC",
        (comuna_code,),
    ):
        if (date.fromisoformat(r["target_date"]) - date.fromisoformat(r["snapshot_date"])).days != offset_days:
            continue
        previous.setdefault(
            r["target_date"],
            {"level": r["level"], "level_combined": r["level_combined"], "score": r["score"], "snapshot_date": r["snapshot_date"]},
        )
    rows = [row(target, current.get(target), previous.get(target)) for target in sorted(set(current) | set(previous))]
    return {
        "rows": rows,
        "summary": summarize(rows),
        "snapshots_from": min((p["snapshot_date"] for p in previous.values()), default=None),
        "weeks": weeks,
        "method": METODO,
    }


def vacio() -> dict[str, Any]:
    """Sin comuna no hay comparación: forma explícita, nunca una comparación inventada."""
    return {"rows": [], "summary": {"sube": 0, "baja": 0, "igual": 0, "sin_anterior": 7, "sin_hoy": 0},
            "snapshots_from": None, "weeks": 1, "method": METODO}

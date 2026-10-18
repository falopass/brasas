"""Frescura del dato satelital: una sola regla para toda la aplicación.

Un punto de calor sin edad se lee como si fuera de ahora. La regla de los 30 minutos se usa en el
pill de la cabecera, en Mi zona, en la ficha de incidente, en el modo vecino y en Riesgo; tenerla
en un solo lugar evita que cada vista invente su propio umbral y que dos pantallas digan cosas
distintas del mismo dato.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

STALE_AFTER_S = 30 * 60


def age_seconds(stamp: str | None, now: datetime | None = None) -> int | None:
    """Segundos desde una marca ISO de la ingesta. None si no hay marca o no se puede leer."""
    if not stamp:
        return None
    try:
        moment = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    reference = now or datetime.now(timezone.utc)
    return max(0, int((reference - moment).total_seconds()))


def status(last_ingest_at: str | None, now: datetime | None = None) -> dict[str, Any]:
    """Contrato que consume la interfaz, para que el cliente no repita la aritmética.

    `stale` es True también cuando no hay marca: una aplicación recién instalada no debe decir
    «al día» de un dato que todavía no existe.
    """
    age = age_seconds(last_ingest_at, now)
    return {"last_ingest_at": last_ingest_at, "age_seconds": age,
            "stale_after_s": STALE_AFTER_S, "stale": age is None or age > STALE_AFTER_S}

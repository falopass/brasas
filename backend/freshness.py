"""Frescura del dato satelital: una sola regla para toda la aplicación.

Un punto de calor sin edad se lee como si fuera de ahora. La regla de los 30 minutos se usa en el
pill de la cabecera, en Mi zona, en la ficha de incidente, en el modo vecino y en Riesgo; tenerla
en un solo lugar evita que cada vista invente su propio umbral y que dos pantallas digan cosas
distintas del mismo dato.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

STALE_AFTER_S = 30 * 60

# Umbral propio por fuente: GOES barre el disco cada ~10 minutos, así que 45 minutos sin dato
# ya es un problema; FIRMS NRT llega con horas de latencia de diseño y solo se declara viejo
# pasadas 6 horas. Una fuente sin umbral propio usa STALE_AFTER_S.
STALE_POR_FUENTE: dict[str, int] = {
    "goes": 45 * 60,
    "firms": 6 * 3600,
}


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
    return {
        "last_ingest_at": last_ingest_at,
        "age_seconds": age,
        "stale_after_s": STALE_AFTER_S,
        "stale": age is None or age > STALE_AFTER_S,
    }


def status_por_fuente(marcas: Mapping[str, str | None], ahora: datetime | None = None) -> dict[str, Any]:
    """Frescura por fuente: a diferencia de `status` (una sola marca global), recibe la marca de
    ingesta de cada fuente y dice cuál está vieja.

    Si una fuente se cae y las demás siguen entrando, la marca global se refresca igual y la
    aplicación diría «al día» aunque falte la mitad de los sensores; aquí `stale` global es True
    si cualquier fuente lo está y `fuentes_viejas` nombra cuáles, para que el vecino no lea
    «no vemos datos» como «no hay fuego». Cada fuente puede tener su propio umbral
    (`STALE_POR_FUENTE`); sin marca o con marca ilegible cuenta como vieja, igual que `status`.
    """
    fuentes: dict[str, dict[str, Any]] = {}
    viejas: list[str] = []
    for nombre, marca in marcas.items():
        limite = STALE_POR_FUENTE.get(nombre.casefold(), STALE_AFTER_S)
        age = age_seconds(marca, ahora)
        vieja = age is None or age > limite
        fuentes[nombre] = {"last_ingest_at": marca, "age_seconds": age, "stale_after_s": limite, "stale": vieja}
        if vieja:
            viejas.append(nombre)
    return {"fuentes": fuentes, "fuentes_viejas": viejas, "stale": bool(viejas)}

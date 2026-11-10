"""Reloj del servidor: `utcnow` y `stamp` en un módulo sin dependencias.

Antes vivían en `services.py` y `diagnostics` los importaba de ahí, lo que obligaba
a `services` a importar `diagnostics` dentro de una función. Ahora cualquier módulo
puede tomarlos sin ciclo. `services` sigue re-exportándolos para no tocar al resto.
"""
from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Ahora en UTC; en tests se parcha `services.utcnow`, no esta función."""
    return datetime.now(timezone.utc)


def stamp(moment: datetime | None = None) -> str:
    """Marca ISO-8601 con `Z`: el formato de todas las fechas guardadas."""
    return (moment or utcnow()).strftime("%Y-%m-%dT%H:%M:%SZ")

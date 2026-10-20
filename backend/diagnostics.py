"""Diagnóstico operativo: resumen de errores de la ingesta para /api/status.

Conteos, instantes y el último mensaje de la propia ingesta (recortado): sirve para
diagnosticar fallos sin acceso a los registros del contenedor (OPS-14). Sin datos personales.
Los mensajes se publican en un endpoint público y sin autenticación: `scrub` enmascara las
claves y tokens que puedan venir en una URL o en una cabecera antes de recortarlos.
"""

from __future__ import annotations

import json
import re
from datetime import timedelta
from typing import Any

from backend.db import Database
from backend.services import stamp, utcnow

WINDOW_H = 24

# Una clave real (MAP_KEY de FIRMS y similares) tiene 20 caracteres o más; los valores cortos
# se dejan tal cual para no enmascarar texto corriente como «key=id».
_SECRETS = (
    (re.compile(r"\b(MAP_KEY|key)=[A-Za-z0-9]{20,}", re.IGNORECASE), r"\1=***"),
    (re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE), "Bearer ***"),
    (re.compile(r"\bX-Internal-Token:\s*[A-Za-z0-9._~+/=-]+", re.IGNORECASE), "X-Internal-Token: ***"),
)


def scrub(text: str) -> str:
    """Enmascara claves y tokens de un mensaje antes de publicarlo."""
    for pattern, replacement in _SECRETS:
        text = pattern.sub(replacement, text)
    return text


def error_summary(db: Database) -> dict[str, Any]:
    """Errores por producto en las últimas `WINDOW_H` horas y claves `*_error` del último ciclo.

    Deriva los conteos de `failures_24h` para que los dos bloques de `/api/status` compartan una
    sola consulta a `ingest_runs`. El mensaje del último error no se publica aquí.
    """
    by_product = {
        product: {"runs": info["runs"], "failed": info["failed"], "last_failed_at": info["last_failed_at"]}
        for product, info in failures_24h(db).items()
    }
    last_cycle = json.loads(db.kv_get("last_cycle") or "{}")
    return {
        "window_h": WINDOW_H,
        "by_product": by_product,
        "cycle_errors": sorted(scrub(k) for k in last_cycle if k.endswith("_error")),
    }


MAX_ERROR_LEN = 160


def failures_24h(db: Database) -> dict[str, Any]:
    """Corridas y fallos por producto en las últimas `WINDOW_H` horas, con el último error.

    Incluye todo producto con corridas en la ventana, aunque no haya fallado: `failed: 0` y
    `last_error: null`. El mensaje es el `message` de la corrida fallida más reciente (el `id` más
    alto), enmascarado con `scrub` y recortado a `MAX_ERROR_LEN` caracteres (en ese orden, para no
    partir una clave). Una sola consulta: el último mensaje sale de una subconsulta correlacionada.
    """
    since = stamp(utcnow() - timedelta(hours=WINDOW_H))
    out: dict[str, dict[str, Any]] = {}
    for row in db.query(
        "SELECT product, COUNT(*) AS runs, SUM(ok = 0) AS failed, "
        "MAX(CASE WHEN ok = 0 THEN started_at END) AS last_failed_at, "
        "(SELECT e.message FROM ingest_runs e WHERE e.product = r.product AND e.ok = 0 "
        "AND e.started_at >= ? ORDER BY e.id DESC LIMIT 1) AS last_error "
        "FROM ingest_runs r WHERE r.started_at >= ? GROUP BY product ORDER BY product",
        (since, since),
    ):
        message = row["last_error"]
        out[row["product"]] = {
            "runs": row["runs"],
            "failed": row["failed"] or 0,
            "last_failed_at": row["last_failed_at"],
            "last_error": scrub(message)[:MAX_ERROR_LEN] if message else None,
        }
    return out

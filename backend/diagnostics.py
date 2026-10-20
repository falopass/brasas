"""Diagnóstico operativo: resumen de errores de la ingesta para /api/status.

Conteos, instantes y el último mensaje de la propia ingesta (recortado): sirve para
diagnosticar fallos sin acceso a los registros del contenedor (OPS-14). Sin datos personales.
"""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

from backend.db import Database
from backend.services import stamp, utcnow

WINDOW_H = 24


def error_summary(db: Database) -> dict[str, Any]:
    """Errores por producto en las últimas `WINDOW_H` horas y claves `*_error` del último ciclo."""
    since = stamp(utcnow() - timedelta(hours=WINDOW_H))
    by_product = {
        row["product"]: {"runs": row["runs"], "failed": row["failed"] or 0, "last_failed_at": row["last_failed_at"]}
        for row in db.query(
            "SELECT product, COUNT(*) AS runs, SUM(ok = 0) AS failed, "
            "MAX(CASE WHEN ok = 0 THEN started_at END) AS last_failed_at "
            "FROM ingest_runs WHERE started_at >= ? GROUP BY product ORDER BY product",
            (since,),
        )
    }
    last_cycle = json.loads(db.kv_get("last_cycle") or "{}")
    return {
        "window_h": WINDOW_H,
        "by_product": by_product,
        "cycle_errors": sorted(k for k in last_cycle if k.endswith("_error")),
    }


MAX_ERROR_LEN = 160


def failures_24h(db: Database) -> dict[str, Any]:
    """Corridas y fallos por producto en las últimas `WINDOW_H` horas, con el último error.

    Incluye todo producto con corridas en la ventana, aunque no haya fallado: `failed: 0` y
    `last_error: null`. El mensaje es el `message` que dejó la ingesta, recortado a
    `MAX_ERROR_LEN` caracteres.
    """
    since = stamp(utcnow() - timedelta(hours=WINDOW_H))
    out = {
        row["product"]: {"runs": row["runs"], "failed": row["failed"] or 0, "last_failed_at": row["last_failed_at"], "last_error": None}
        for row in db.query(
            "SELECT product, COUNT(*) AS runs, SUM(ok = 0) AS failed, "
            "MAX(CASE WHEN ok = 0 THEN started_at END) AS last_failed_at "
            "FROM ingest_runs WHERE started_at >= ? GROUP BY product ORDER BY product",
            (since,),
        )
    }
    for row in db.query(
        "SELECT r.product, r.message FROM ingest_runs r JOIN (SELECT product, MAX(id) AS id "
        "FROM ingest_runs WHERE ok = 0 AND started_at >= ? GROUP BY product) last ON last.id = r.id",
        (since,),
    ):
        if row["product"] in out and row["message"]:
            out[row["product"]]["last_error"] = row["message"][:MAX_ERROR_LEN]
    return out

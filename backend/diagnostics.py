"""Diagnóstico operativo: resumen de errores de la ingesta para /api/status.

Solo conteos e instantes, sin mensajes ni datos personales: sirve para diagnosticar
fallos sin acceso a los registros del contenedor (OPS-14).
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
            "FROM ingest_runs WHERE started_at >= ? GROUP BY product ORDER BY product", (since,))}
    last_cycle = json.loads(db.kv_get("last_cycle") or "{}")
    return {
        "window_h": WINDOW_H,
        "by_product": by_product,
        "cycle_errors": sorted(k for k in last_cycle if k.endswith("_error")),
    }

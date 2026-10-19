"""Radar de respuesta oficial: cuánto tarda la respuesta de CONAF según su propio reporte.

El CSV de GEPRIF trae tres marcas por incendio: detección (`f_deteccion`), aviso a los equipos
(`f_aviso`) y despacho de recursos (`f_despacho`). Con esas marcas, ya guardadas en
`official_fires`, se calculan medianas de minutos por temporada, por tramo de superficie y por
comuna. El archivo no trae la hora de arribo, así que lo publicado aquí termina en el despacho:
son los tiempos que declara CONAF, no una medición propia de BRASA.
"""
from __future__ import annotations

import statistics
from datetime import datetime
from typing import Any

# Más de una semana entre dos marcas no es una espera: es un dato malo del archivo origen.
MAX_MINUTES = 7 * 24 * 60

PAIRS = (("detection_to_alert", "detected_at", "alerted_at"),
         ("alert_to_dispatch", "alerted_at", "dispatched_at"),
         ("detection_to_dispatch", "detected_at", "dispatched_at"))

AREA_BUCKETS = ("<1 ha", "1-10", "10-100", ">100")
MIN_COMUNA_FIRES = 3


def minutes(a: str | None, b: str | None) -> float | None:
    """Minutos entre dos marcas ISO, o None si falta alguna, no se puede leer o el
    resultado es imposible (negativo —relojes desfasados— o de más de una semana)."""
    if not a or not b:
        return None
    try:
        start = datetime.fromisoformat(str(a).replace("Z", "+00:00"))
        end = datetime.fromisoformat(str(b).replace("Z", "+00:00"))
        delta = (end - start).total_seconds() / 60
    except (ValueError, TypeError):
        return None
    return delta if 0 <= delta <= MAX_MINUTES else None


def _bucket(area_ha: Any) -> str | None:
    """Tramo de superficie. Sin superficie el incendio no entra a ningún tramo («sin dato»)."""
    try:
        area = float(area_ha)
    except (TypeError, ValueError):
        return None
    if area < 1:
        return "<1 ha"
    if area < 10:
        return "1-10"
    if area <= 100:
        return "10-100"
    return ">100"


def _stat(values: list[float]) -> dict[str, Any]:
    """Mediana redondeada a un decimal y cuántos datos la sostienen."""
    return {"median_min": round(statistics.median(values), 1) if values else None, "n": len(values)}


def aggregate(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Medianas de los tres tiempos de respuesta sobre filas de `official_fires`.

    `excluded` cuenta los incendios de los que no se pudo calcular ningún par (sin marcas
    publicadas o con marcas imposibles). Las comunas piden al menos 3 incendios con
    detección → aviso calculable para no publicar medianas de dos datos.
    """
    totals: dict[str, list[float]] = {key: [] for key, _, _ in PAIRS}
    by_bucket: dict[str, dict[str, Any]] = {}
    by_comuna: dict[str, list[float]] = {}
    excluded = 0
    for row in rows:
        gaps = {key: minutes(row.get(a), row.get(b)) for key, a, b in PAIRS}
        if all(v is None for v in gaps.values()):
            excluded += 1
        for key, value in gaps.items():
            if value is not None:
                totals[key].append(value)
        bucket = _bucket(row.get("area_ha"))
        if bucket:
            entry = by_bucket.setdefault(bucket, {"n_fires": 0, **{k: [] for k, _, _ in PAIRS}})
            entry["n_fires"] += 1
            for key, value in gaps.items():
                if value is not None:
                    entry[key].append(value)
        comuna = (row.get("comuna") or "").strip()
        if comuna and gaps["detection_to_alert"] is not None:
            by_comuna.setdefault(comuna, []).append(gaps["detection_to_alert"])
    buckets = [{"bucket": label, **entry} for label, entry in by_bucket.items()]
    buckets.sort(key=lambda b: AREA_BUCKETS.index(b["bucket"]))
    for entry in buckets:
        entry.update({key: _stat(entry[key]) for key, _, _ in PAIRS})
    comunas = [{"comuna": name, "n": len(values), "detection_to_alert": _stat(values)}
               for name, values in by_comuna.items() if len(values) >= MIN_COMUNA_FIRES]
    comunas.sort(key=lambda c: (-c["n"], c["comuna"]))
    return {"overall": {key: _stat(values) for key, values in totals.items()},
            "comunas": comunas, "buckets": buckets, "excluded": excluded}

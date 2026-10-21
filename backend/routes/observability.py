"""Observabilidad de las rutas públicas: cuántas veces se pidió cada una, cuánto tardó y qué devolvió.

Una ventana deslizante en memoria de 60 minutos guarda tres datos por petición a `/api/…`: la ruta
**plantillada** (`/api/incidents/{incident_id}`), el código de estado y los milisegundos hasta que
la respuesta empieza a salir. No se guardan IP, query string, cabeceras ni cuerpos, y nada se
escribe en disco: la medición se reinicia con el proceso y cada instancia mide solo su propio
tráfico. El middleware que anota vive en `backend/main.py`; aquí viven la ventana y la lectura.
"""

from __future__ import annotations

import math
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Request

from backend.services import stamp

router = APIRouter(prefix="/api")

WINDOW_MIN = 60
MAX_SAMPLES = 20_000  # tope de memoria de la ventana
UNMATCHED = "/api/sin-ruta"  # lo que no calza con ninguna ruta no se guarda crudo: podría traer datos de la URL

# (instante monotónico, ruta plantillada, código HTTP, milisegundos)
SAMPLES: deque[tuple[float, str, int, float]] = deque()


def route_of(request: Request) -> str:
    """La ruta plantillada que resolvió FastAPI; si ninguna calzó, una etiqueta fija."""
    return getattr(request.scope.get("route"), "path", None) or UNMATCHED


def record(path: str, status: int, ms: float) -> None:
    """Anota una petición y poda lo que quedó fuera de la ventana o pasado el tope de memoria."""
    now = time.monotonic()
    SAMPLES.append((now, path, status, ms))
    cutoff = now - WINDOW_MIN * 60
    # shortcut: sobre MAX_SAMPLES muestras en la hora se descartan las más viejas; si el tráfico
    # llega a ese volumen, medir por cubetas en vez de guardar cada muestra.
    while SAMPLES and (SAMPLES[0][0] < cutoff or len(SAMPLES) > MAX_SAMPLES):
        SAMPLES.popleft()


def _percentile(ordered: list[float], p: int) -> int:
    """Percentil por rango más cercano: con pocas muestras devuelve una de ellas, no una interpolación."""
    return round(ordered[max(0, math.ceil(p / 100 * len(ordered)) - 1)])


def _row(path: str, samples: list[tuple[float, str, int, float]]) -> dict[str, Any]:
    ordered = sorted(ms for _, _, _, ms in samples)
    return {
        "path": path,
        "n": len(samples),
        "p50_ms": _percentile(ordered, 50),
        "p95_ms": _percentile(ordered, 95),
        "errors_4xx": sum(1 for _, _, status, _ in samples if 400 <= status < 500),
        "errors_5xx": sum(1 for _, _, status, _ in samples if 500 <= status < 600),
        "max_ms": round(ordered[-1]),
    }


@router.get("/observability/routes")
async def route_stats() -> dict[str, Any]:
    """Conteo, latencia y errores por ruta en la última hora, ordenado por p95 descendente."""
    # async a propósito: corre en el hilo del event loop, el mismo donde el middleware anota,
    # así `SAMPLES` no se muta mientras se recorre.
    cutoff = time.monotonic() - WINDOW_MIN * 60
    by_path: dict[str, list[tuple[float, str, int, float]]] = {}
    for sample in SAMPLES:
        if sample[0] >= cutoff:
            by_path.setdefault(sample[1], []).append(sample)
    rows = [_row(path, samples) for path, samples in by_path.items()]
    rows.sort(key=lambda row: (-row["p95_ms"], row["path"]))
    return {
        "window_min": WINDOW_MIN,
        "desde": stamp(datetime.now(timezone.utc) - timedelta(minutes=WINDOW_MIN)),
        "aviso": (
            "Medición por proceso: la ventana se reinicia con el contenedor y cada instancia mide "
            "solo su propio tráfico. Guarda solo ruta plantillada, código y milisegundos; nunca IP, "
            "query string, cabeceras ni cuerpos."
        ),
        "routes": rows,
    }

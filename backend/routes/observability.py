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

from fastapi import APIRouter, Depends, Request

from backend.geo import _fold, normalizar_comuna, territory
from backend.risk import local_day
from backend.routes.common import services
from backend.services import Services, stamp

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
    ordered = sorted(ms for samples in by_path.values() for _, _, _, ms in samples)
    return {
        "window_min": WINDOW_MIN,
        "desde": stamp(datetime.now(timezone.utc) - timedelta(minutes=WINDOW_MIN)),
        "aviso": (
            "Medición por proceso: la ventana se reinicia con el contenedor y cada instancia mide "
            "solo su propio tráfico. Guarda solo ruta plantillada, código y milisegundos; nunca IP, "
            "query string, cabeceras ni cuerpos."
        ),
        "n": len(ordered),
        "p50_ms": _percentile(ordered, 50) if ordered else None,
        "p95_ms": _percentile(ordered, 95) if ordered else None,
        "routes": rows,
    }


# RISK-09: resumen público de la concordancia. La misma regla que scripts/calibrar_riesgo.py
# (evento comuna-día en hora de Chile, horas de Botón Rojo > 0, tasa y lift), pero nacional y
# en vivo. El script no viaja en la imagen: el contenedor solo copia backend/ y web/.
CONCORDANCIA_KEY = "obs:concordancia"
CONCORDANCIA_TTL_S = 3600
_NIVELES = ("bajo", "moderado", "alto", "extremo")
_CLASES = ("level", "level_combined", "fwi_level")
_ALTO_EXTREMO = frozenset({"alto", "extremo"})
CONCORDANCIA_METHOD = (
    "concordancia comuna-día entre el pronóstico guardado, los incendios de CONAF y el Botón Rojo, "
    "sin ajuste de umbrales"
)
CONCORDANCIA_NOTE = (
    "Compara el pronóstico guardado en la base con los incendios del reporte público de CONAF "
    "por comuna y día de Chile, sin ajustar umbrales automáticamente. "
    "Cada incendio cuenta una vez por comuna y día, en hora de Chile. "
    "La tasa es días con incendio dividido por días con ese nivel. "
    "El lift es esa tasa dividida por la tasa de todos los días con dato de la misma clase. "
    "Si el denominador es cero, la tasa queda vacía: no se inventa un porcentaje. "
    "coincidencia_br_alto_extremo es la fracción de los días con Botón Rojo cuyo level_combined "
    "fue alto o extremo, contando también los días de Botón Rojo que no tienen pronóstico guardado."
)


def _tasa(parte: int, total: int) -> float | None:
    """None si no hay denominador: un cero inventado se leería como «nunca pasa»."""
    return round(parte / total, 4) if total else None


def _lift(tasa: float | None, base: float | None) -> float | None:
    if tasa is None or not base:
        return None
    return round(tasa / base, 2)


def _lookup_comunas() -> tuple[dict[str, int], set[str]]:
    """Nombre plegado → código, y los nombres que calzan con más de una comuna."""
    lookup: dict[str, int] = {}
    ambiguous: set[str] = set()
    for comuna in territory().comunas:
        key = _fold(comuna.name)
        if key in lookup and lookup[key] != comuna.code:
            ambiguous.add(key)
        lookup[key] = comuna.code
    return lookup, ambiguous


def _eventos_comuna_dia(fires: list[dict[str, Any]]) -> set[tuple[int, str]]:
    """Incendios de CONAF reducidos a (comuna, día de Chile). El nombre que no calza no cuenta."""
    lookup, ambiguous = _lookup_comunas()
    events: set[tuple[int, str]] = set()
    for fire in fires:
        started = fire.get("started_at")
        name = (fire.get("comuna") or "").strip()
        try:
            day = local_day(started) if started else None
        except (TypeError, ValueError):
            day = None
        if day is None or not name:
            continue
        key = normalizar_comuna(name)
        code = lookup.get(key)
        if code is None or key in ambiguous:
            continue
        events.add((int(code), day))
    return events


def _clase(
    rows: list[dict[str, Any]], events: set[tuple[int, str]], br_keys: set[tuple[int, str]], column: str
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Conteos por nivel y el bloque alto+extremo de una columna de risk_daily."""
    buckets = {name: {"dias": 0, "con_incendio": 0} for name in _NIVELES}
    dias_con_dato = incendios_con_dato = 0
    for row in rows:
        value = row.get(column)
        if value is None:
            continue
        has_fire = (int(row["comuna_code"]), row["date"]) in events
        dias_con_dato += 1
        incendios_con_dato += 1 if has_fire else 0
        cell = buckets.get(value)
        if cell is None:
            continue
        cell["dias"] += 1
        cell["con_incendio"] += 1 if has_fire else 0
    base = _tasa(incendios_con_dato, dias_con_dato)
    niveles = {}
    for name in _NIVELES:
        dias, fuegos = buckets[name]["dias"], buckets[name]["con_incendio"]
        tasa = _tasa(fuegos, dias)
        niveles[name] = {"dias": dias, "con_incendio": fuegos, "tasa": tasa, "lift": _lift(tasa, base)}
    ae_dias = buckets["alto"]["dias"] + buckets["extremo"]["dias"]
    ae_fuegos = buckets["alto"]["con_incendio"] + buckets["extremo"]["con_incendio"]
    ae_tasa = _tasa(ae_fuegos, ae_dias)
    ae_br = sum(
        1
        for row in rows
        if row.get(column) in _ALTO_EXTREMO and (int(row["comuna_code"]), row["date"]) in br_keys
    )
    alto_extremo = {
        "dias": ae_dias,
        "con_incendio": ae_fuegos,
        "tasa": ae_tasa,
        "lift": _lift(ae_tasa, base),
        "proporcion_incendios": _tasa(ae_fuegos, incendios_con_dato),
        "eventos_con_dato": incendios_con_dato,
        "dias_con_boton_rojo": ae_br,
        "coincidencia_boton_rojo": _tasa(ae_br, ae_dias),
    }
    return niveles, alto_extremo


def calcular_concordancia(db: Any) -> dict[str, Any]:
    """Tabla nacional sobre la base viva. Conteos en 0 y tasas en None si aún no hay días."""
    risk_days = db.query("SELECT comuna_code, date, level, level_combined, fwi_level FROM risk_daily")
    fires = db.query("SELECT comuna, started_at FROM official_fires")
    boton = db.query("SELECT comuna_code, date FROM boton_rojo WHERE hours > 0")
    events = _eventos_comuna_dia(fires)
    risk_keys = {(int(row["comuna_code"]), row["date"]) for row in risk_days}
    br_keys = {(int(row["comuna_code"]), row["date"]) for row in boton}
    por_dia = {(int(row["comuna_code"]), row["date"]): row for row in risk_days}
    br_alto = sum(
        1 for key in br_keys if (por_dia.get(key) or {}).get("level_combined") in _ALTO_EXTREMO
    )
    clases: dict[str, Any] = {}
    alto_extremo: dict[str, Any] = {}
    for column in _CLASES:
        niveles, bloque = _clase(risk_days, events, br_keys, column)
        clases[column] = niveles
        alto_extremo[column] = bloque
    return {
        "dias_riesgo": len(risk_days),
        "eventos_comuna_dia": len(events),
        "eventos_con_riesgo": len(events & risk_keys),
        "clases": clases,
        "alto_extremo": alto_extremo,
        "dias_boton_rojo": len(br_keys),
        "boton_rojo_en_alto_extremo": br_alto,
        "coincidencia_br_alto_extremo": _tasa(br_alto, len(br_keys)),
        "method": CONCORDANCIA_METHOD,
        "note": CONCORDANCIA_NOTE,
    }


@router.get("/observability/concordancia")
def concordancia(svc: Services = Depends(services)) -> dict[str, Any]:
    """Concordancia del pronóstico guardado con CONAF. Caché de una hora; no escribe umbrales."""
    cached = svc.db.cache_get(CONCORDANCIA_KEY)
    if isinstance(cached, dict):
        return cached
    payload = calcular_concordancia(svc.db)
    svc.db.cache_set(CONCORDANCIA_KEY, payload, CONCORDANCIA_TTL_S)
    return payload

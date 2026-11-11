"""Observabilidad de las rutas públicas: cuántas veces se pidió cada una, cuánto tardó y qué devolvió.

Una ventana deslizante en memoria de 60 minutos guarda tres datos por petición a `/api/…`: la ruta
**plantillada** (`/api/incidents/{incident_id}`), el código de estado y los milisegundos hasta que
la respuesta empieza a salir. No se guardan IP, query string, cabeceras ni cuerpos, y nada se
escribe en disco: la medición se reinicia con el proceso y cada instancia mide solo su propio
tráfico. El middleware que anota vive en `backend/main.py`; aquí viven la ventana y la lectura.
"""

from __future__ import annotations

import json
import math
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query, Request

from backend.freshness import familia
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


# QA-3.2: descartes por fuente en «Calidad de los datos». Lee los conteos que el parser
# guardó por corrida en `ingest_runs.discards` y el destino posterior de las detecciones
# (vínculo a incidentes fijos o descartados, confianza). Vacíos como null, nunca 0.
DESCARTES_TTL_S = 300
# Las corridas de la ventana guardan también detecciones viejas (FIRMS pide 2 días y el
# relleno de GOES mira hasta 24 h atrás): las nuevas se identifican por `run_id`, así que
# la lectura de observations cubre la ventana más ese arrastre, siempre acotada por el
# índice de `observed_at`.
OBS_LOOKBACK_H = 72
DESCARTES_METHOD = (
    "corridas satelitales con ok=1 de ingest_runs en la ventana (started_at), conteos por "
    "fuente guardados por el parser en la columna discards y el estado posterior de las "
    "detecciones en incident_observations → incidents (fixed_source y status)"
)
DESCARTES_NOTE = (
    "«Recibidas», «fuera de Chile» y «fila inválida» existen solo para corridas que guardaron "
    "el conteo del parser; si ninguna corrida de la fuente lo trajo salen en null (sin medir), "
    "nunca en 0, y corridas_sin_medir dice cuántas no lo midieron. «Nuevas» son las detecciones "
    "que esas corridas guardaron por primera vez; «repetidas», las que el parser entregó y ya "
    "estaban guardadas (deduplicación operativa, no un descarte de calidad). «Fuente fija» "
    "cuenta detecciones ligadas a un incidente marcado como fuente de calor fija probable: no "
    "generan aviso automático. «Fuera del país» cuenta las ligadas a un incidente «descartado», "
    "que quedó sin comuna chilena. «Confianza baja» se guarda igual, pero no cuenta como "
    "evidencia confiable para declarar un incidente «posible»."
)


def _fila_descartes() -> dict[str, Any]:
    return {
        "recibidas": 0,
        "nuevas": 0,
        "repetidas": None,
        "fuera_de_chile": 0,
        "fila_invalida": 0,
        "fuente_fija": 0,
        "fuera_del_pais": 0,
        "confianza_baja": 0,
        "corridas": 0,
        "corridas_sin_medir": 0,
        "_entregadas": None,            # lo que el parser devolvió por fuente; None hasta la primera corrida atribuible
        "_entregadas_incompleta": False,  # hay corridas multi-fuente sin medir: entregadas queda a medias
    }


def calcular_descartes(db: Any, horas: int) -> dict[str, Any]:
    """Descartes por fuente en la ventana: lo que el parser dejó fuera y el destino de lo guardado."""
    now = datetime.now(timezone.utc)
    since = stamp(now - timedelta(hours=horas))
    runs = db.query(
        "SELECT id, provider, product, n_records, discards FROM ingest_runs "
        "WHERE started_at >= ? AND ok = 1",
        (since,),
    )
    fuentes: dict[str, dict[str, Any]] = {}
    run_ids: set[int] = set()
    for run in runs:
        if familia(run["provider"], run["product"]) not in ("GOES", "FIRMS"):
            continue
        run_ids.add(run["id"])
        medidos = json.loads(run["discards"]) if run["discards"] else None
        # `product` lista todas las fuentes pedidas: una fuente que falló dentro de una
        # corrida correcta no está en `discards` y cuenta como corrida sin medir.
        sources = [part.strip() for part in run["product"].split(",")]
        for source in sources:
            fila = fuentes.setdefault(source, _fila_descartes())
            fila["corridas"] += 1
            counts = (medidos or {}).get(source)
            if counts:
                recibidas = counts.get("recibidas") or 0
                fuera = counts.get("fuera_de_chile") or 0
                invalidas = counts.get("fila_invalida") or 0
                fila["recibidas"] += recibidas
                fila["fuera_de_chile"] += fuera
                fila["fila_invalida"] += invalidas
                fila["_entregadas"] = (fila["_entregadas"] or 0) + recibidas - fuera - invalidas
                continue
            fila["corridas_sin_medir"] += 1
            if len(sources) == 1:
                # Corrida de una sola fuente (un barrido GOES): n_records es lo que el parser entregó.
                fila["_entregadas"] = (fila["_entregadas"] or 0) + run["n_records"]
            else:
                fila["_entregadas_incompleta"] = True
    observations = db.query(
        "SELECT o.source, o.confidence, o.observed_at, o.run_id, i.fixed_source, i.status "
        "FROM observations o LEFT JOIN incident_observations io ON io.observation_id = o.id "
        "LEFT JOIN incidents i ON i.id = io.incident_id WHERE o.observed_at >= ?",
        (stamp(now - timedelta(hours=horas + OBS_LOOKBACK_H)),),
    )
    for obs in observations:
        fila = fuentes.get(obs["source"])
        if fila is None:
            continue
        if obs["run_id"] in run_ids:
            fila["nuevas"] += 1
        if obs["observed_at"] >= since:
            if obs["confidence"] == "baja":
                fila["confianza_baja"] += 1
            if obs["fixed_source"] == 1:
                fila["fuente_fija"] += 1
            if obs["status"] == "descartado":
                fila["fuera_del_pais"] += 1
    salida = []
    for source in sorted(fuentes):
        fila = fuentes[source]
        entregadas = fila.pop("_entregadas")
        incompleta = fila.pop("_entregadas_incompleta")
        # Con corridas sin medir la suma del parser sería un total parcial disfrazado de
        # total de la ventana: null («sin medir»), nunca un 0 ni un número a medias.
        if fila["corridas_sin_medir"]:
            fila["recibidas"] = fila["fuera_de_chile"] = fila["fila_invalida"] = None
        fila["repetidas"] = max(0, entregadas - fila["nuevas"]) if entregadas is not None and not incompleta else None
        salida.append({"source": source, **fila})
    return {
        "generated_at": stamp(now),
        "horas": horas,
        "desde": since,
        "fuentes": salida,
        "method": DESCARTES_METHOD,
        "note": DESCARTES_NOTE,
    }


@router.get("/observability/descartes")
def descartes(horas: int = Query(24, ge=1, le=168), svc: Services = Depends(services)) -> dict[str, Any]:
    """Descartes por fuente en la ventana pedida (1-168 h). Caché de 5 min; vacíos en null."""
    key = f"obs:descartes:{horas}"
    cached = svc.db.cache_get(key)
    if isinstance(cached, dict):
        return cached
    payload = calcular_descartes(svc.db, horas)
    svc.db.cache_set(key, payload, DESCARTES_TTL_S)
    return payload

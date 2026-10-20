"""Clima de fondo: estado de El Niño / La Niña (ENSO) según el índice ONI de la NOAA CPC.

La fase usa el umbral estándar del CPC sobre el último trimestre móvil publicado:
ONI ≥ +0,5 °C → «nino» (El Niño); ONI ≤ −0,5 °C → «nina» (La Niña); entre medio → «neutral».

El CPC actualiza la tabla semanalmente: la respuesta se guarda unas horas en caché para no
golpear la fuente a cada visita, y la última lectura buena queda en `kv` para responder con
ella (con su fecha original) cuando la NOAA no contesta. Sin dato guardado, los campos
salen en null: nunca se inventa un valor.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from backend import fwi as fwi_mod
from backend.providers import air, noaa
from backend.routes.common import services
from backend.services import Services, stamp

router = APIRouter(prefix="/api")

CACHE_KEY = "climate:enso"
CACHE_TTL = 6 * 3600  # el ONI cambia a lo sumo semanalmente
FAIL_TTL = 600  # si la NOAA cae, no se reintenta a cada solicitud
LAST_KEY = "enso_last"  # última lectura buena, sin expiración

AIR_TTL = 3 * 3600  # CAMS se actualiza pocas veces al día
AIR_FAIL_TTL = 600  # si el proveedor cae, no se reintenta a cada visita
AIR_TIMEOUT_S = 4  # la tarjeta del lugar nunca espera más que esto

FWI_CACHE_TTL = 3600  # la historia solo crece una vez al día, con la pasada del FWI
FWI_WINDOW_DAYS = 365


@router.get("/climate/enso")
async def enso(svc: Services = Depends(services)):
    cached = svc.db.cache_get(CACHE_KEY)
    if cached:
        return cached
    try:
        reading = await noaa.fetch_oni(svc.client)
    except noaa.NoaaError:
        reading = None
    if reading:
        payload = {
            "phase": noaa.phase_of(reading.oni),
            "oni": reading.oni,
            "season": reading.season,
            "year": reading.year,
            "updated_at": stamp(),
            "source": noaa.SOURCE,
            "source_url": noaa.SOURCE_URL,
        }
        svc.db.cache_set(CACHE_KEY, payload, CACHE_TTL)
        svc.db.kv_set(LAST_KEY, json.dumps(payload))
        return payload
    saved = svc.db.kv_get(LAST_KEY)
    payload = (
        json.loads(saved)
        if saved
        else {
            "phase": None,
            "oni": None,
            "season": None,
            "year": None,
            "updated_at": None,
            "source": noaa.SOURCE,
            "source_url": noaa.SOURCE_URL,
        }
    )
    svc.db.cache_set(CACHE_KEY, payload, FAIL_TTL)
    return payload


@router.get("/climate/fwi/percentile/{code}")
def fwi_percentile(code: int, svc: Services = Depends(services)):
    """El FWI vigente de una comuna leído contra su propia historia del último año."""
    cache_key = f"climate:fwi-percentile:{code}"
    cached = svc.db.cache_get(cache_key)
    if cached:
        return cached
    today = datetime.now(timezone.utc).date()
    rows = svc.db.query(
        "SELECT date, fwi, level FROM fwi_daily WHERE comuna_code = ? AND date >= ? ORDER BY date",
        (code, (today - timedelta(days=FWI_WINDOW_DAYS)).isoformat()),
    )
    if not rows:
        raise HTTPException(404, {"code": "SIN_HISTORIAL", "message": "Todavía no hay historial de FWI para esta comuna."})
    # La tabla también guarda el pronóstico de los próximos días: el valor vigente es el
    # último que ya llegó a su fecha; si no hay ninguno, se usa el dato más reciente.
    current = next((row for row in reversed(rows) if row["date"] <= today.isoformat()), rows[-1])
    payload = {
        "comuna_code": code,
        "value": current["fwi"],
        "level": current["level"],
        "percentile": fwi_mod.percentile(current["fwi"], [row["fwi"] for row in rows]),
        "days": len(rows),
        "since": rows[0]["date"],
        "source": "FWI de BRASA (Van Wagner)",
        "note": (
            "El FWI vigente de la comuna comparado con su propia historia del último "
            "año: el percentil es el porcentaje de esos días con un FWI menor o igual "
            "(los empates cuentan la mitad). Sale en null mientras la historia tenga "
            "menos de 10 días: con tan pocos datos no se inventa una cifra."
        ),
    }
    svc.db.cache_set(cache_key, payload, FWI_CACHE_TTL)
    return payload


@router.get("/air")
async def air_forecast(lat: float = Query(..., ge=-90, le=90), lon: float = Query(..., ge=-180, le=180), svc: Services = Depends(services)):
    """PM2,5/PM10 pronosticados para las próximas 24 h en un punto (modelo CAMS).

    Nunca responde error: si el proveedor no contesta a tiempo, `available` sale en
    false y la vista no muestra la línea de humo. Solo valor y hora: no hay umbrales
    ni categorías de salud propios."""
    key = f"air:{round(lat * 20) / 20:.2f}:{round(lon * 20) / 20:.2f}"
    cached = svc.db.cache_get(key)
    if cached:
        return cached
    meta = {"source": air.SOURCE, "source_url": air.SOURCE_URL, "license": air.LICENSE}
    try:
        series = await asyncio.wait_for(air.hourly(svc.client, lat, lon), AIR_TIMEOUT_S)
        payload = {"available": True, "hourly": air.next_24h(series), "stamp": stamp(), **meta}
    except (air.AirError, TimeoutError):
        payload = {"available": False, "stamp": stamp(), **meta}
    svc.db.cache_set(key, payload, AIR_TTL if payload["available"] else AIR_FAIL_TTL)
    return payload

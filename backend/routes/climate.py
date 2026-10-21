"""Clima de fondo: estado de El Niño / La Niña (ENSO) según el índice ONI de la NOAA CPC.

La fase usa el umbral estándar del CPC sobre el último trimestre móvil publicado:
ONI ≥ +0,5 °C → «nino» (El Niño); ONI ≤ −0,5 °C → «nina» (La Niña); entre medio → «neutral».

El CPC actualiza la tabla semanalmente: la respuesta se guarda unas horas en caché para no
golpear la fuente a cada visita, y la última lectura buena queda en `kv` para responder con
ella (con su fecha original) cuando la NOAA no contesta. Sin dato guardado, los campos
salen en null: nunca se inventa un valor.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException

from backend import fwi as fwi_mod
from backend.providers import noaa
from backend.routes.common import services
from backend.services import Services, stamp

router = APIRouter(prefix="/api")

CACHE_KEY = "climate:enso"
CACHE_TTL = 6 * 3600  # el ONI cambia a lo sumo semanalmente
FAIL_TTL = 600  # si la NOAA cae, no se reintenta a cada solicitud
LAST_KEY = "enso_last"  # última lectura buena, sin expiración

FWI_CACHE_TTL = 3600  # la historia solo crece una vez al día, con la pasada del FWI
FWI_WINDOW_DAYS = 365

CHILE_TZ = ZoneInfo("America/Santiago")


def _chile_today() -> date:
    return datetime.now(CHILE_TZ).date()


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
    payload = {
        "phase": None,
        "oni": None,
        "season": None,
        "year": None,
        "updated_at": None,
        "source": noaa.SOURCE,
        "source_url": noaa.SOURCE_URL,
    }
    saved = svc.db.kv_get(LAST_KEY)
    if saved:
        try:
            reading = json.loads(saved)
        except json.JSONDecodeError:
            reading = None  # respaldo ilegible: equivale a no tener lectura
        if isinstance(reading, dict):
            payload.update(reading)
    svc.db.cache_set(CACHE_KEY, payload, FAIL_TTL)
    return payload


@router.get("/climate/fwi/percentile/{code}")
def fwi_percentile(code: int, svc: Services = Depends(services)):
    """El FWI vigente de una comuna leído contra su propia historia del último año."""
    today = _chile_today()
    cache_key = f"climate:fwi-percentile:{code}:{today.isoformat()}"
    cached = svc.db.cache_get(cache_key)
    if cached:
        return cached
    rows = svc.db.query(
        "SELECT date, fwi, level FROM fwi_daily WHERE comuna_code = ? AND date >= ? AND date <= ? ORDER BY date",
        (code, (today - timedelta(days=FWI_WINDOW_DAYS)).isoformat(), today.isoformat()),
    )
    if not rows:
        raise HTTPException(404, {"code": "SIN_HISTORIAL", "message": "Todavía no hay historial de FWI para esta comuna."})
    # La tabla también guarda el pronóstico de los próximos días: ni el valor vigente ni
    # la historia cuentan una fecha que todavía no llega.
    current = rows[-1]
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

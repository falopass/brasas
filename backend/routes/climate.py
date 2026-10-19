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

from fastapi import APIRouter, Depends

from backend.providers import noaa
from backend.routes.common import services
from backend.services import Services, stamp

router = APIRouter(prefix="/api")

CACHE_KEY = "climate:enso"
CACHE_TTL = 6 * 3600        # el ONI cambia a lo sumo semanalmente
FAIL_TTL = 600              # si la NOAA cae, no se reintenta a cada solicitud
LAST_KEY = "enso_last"      # última lectura buena, sin expiración


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
        payload = {"phase": noaa.phase_of(reading.oni), "oni": reading.oni,
                   "season": reading.season, "year": reading.year, "updated_at": stamp(),
                   "source": noaa.SOURCE, "source_url": noaa.SOURCE_URL}
        svc.db.cache_set(CACHE_KEY, payload, CACHE_TTL)
        svc.db.kv_set(LAST_KEY, json.dumps(payload))
        return payload
    saved = svc.db.kv_get(LAST_KEY)
    payload = json.loads(saved) if saved else {
        "phase": None, "oni": None, "season": None, "year": None, "updated_at": None,
        "source": noaa.SOURCE, "source_url": noaa.SOURCE_URL}
    svc.db.cache_set(CACHE_KEY, payload, FAIL_TTL)
    return payload

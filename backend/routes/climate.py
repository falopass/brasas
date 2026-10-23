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
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query

from backend import fwi as fwi_mod
from backend import lluvia as lluvia_mod
from backend.geo import territory
from backend.providers import noaa, weather
from backend.routes.common import services
from backend.services import Services, stamp

router = APIRouter(prefix="/api")

CACHE_KEY = "climate:enso"
CACHE_TTL = 6 * 3600  # el ONI cambia a lo sumo semanalmente
FAIL_TTL = 600  # si la NOAA cae, no se reintenta a cada solicitud
LAST_KEY = "enso_last"  # última lectura buena, sin expiración

FWI_CACHE_TTL = 3600  # la historia solo crece una vez al día, con la pasada del FWI
FWI_WINDOW_DAYS = 365

LLUVIA_TTL_S = 1800   # el pronóstico se renueva; media hora por celda como el viento del lugar
LLUVIA_RETRY_S = 300  # ante un fallo del proveedor no se golpea a Open-Meteo a cada visita

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


@router.get("/climate/lluvia")
async def lluvia_punto(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    svc: Services = Depends(services),
):
    """La señal de `backend/lluvia.py` servida como dato, para «Mi zona» (AGUA-09).

    Es la peor ventana de 3 horas del pronóstico horario del punto y la isoterma 0 °C de
    su hora central: un dato del pronóstico, nunca un aviso de aluvión (los umbrales
    siguen provisionales y BRASA no emite ese aviso). La celda de 0,1° comparte la llamada
    a Open-Meteo entre lugares cercanos, como `risk_point_at`; si el proveedor falla,
    `senal` sale en null — nunca se inventa una lectura.
    """
    cache_key = f"lluvia:{round(lat, 1)}:{round(lon, 1)}"
    cached = svc.db.cache_get(cache_key)
    if cached is not None:
        return cached
    try:
        hourly = (
            await weather.forecast_hourly(
                svc.client,
                [(round(lat, 1), round(lon, 1))],
                days=2,
                extra_vars=["precipitation", "freezing_level_height"],
            )
        )[0]
        senal = lluvia_mod.senal(hourly, now=datetime.now(timezone.utc))
    except weather.WeatherError:
        senal = None
    payload = {
        "senal": senal,
        "computed_at": stamp(),
        "source": "Open-Meteo · pronóstico horario",
        "source_url": "https://open-meteo.com/",
        "note": "Peor ventana de lluvia en 3 horas e isoterma 0 °C en el punto consultado. "
                + lluvia_mod.ETIQUETA
                + " BRASA no emite avisos de aluvión.",
    }
    svc.db.cache_set(cache_key, payload, LLUVIA_TTL_S if senal else LLUVIA_RETRY_S)
    return payload


@router.get("/climate/quema/{code}")
def quema_hoy(code: int, svc: Services = Depends(services)):
    """El insumo del bloque «¿Puedo quemar hoy?» (QUEMA-01): riesgo 30-30-30 y Botón Rojo del día.

    Es solo lectura de lo ya calculado (`risk_daily`, `boton_rojo`); la vista decide el
    mensaje. Sin dato del día los campos salen en null: no se inventa un nivel. BRASA
    nunca habilita una quema — la autorización corresponde a CONAF o al municipio.
    """
    if territory().by_code.get(code) is None:
        raise HTTPException(404, "Comuna no encontrada.")
    today = _chile_today().isoformat()
    risk = svc.db.one("SELECT level FROM risk_daily WHERE comuna_code = ? AND date = ?", (code, today))
    br = svc.db.one("SELECT hours FROM boton_rojo WHERE comuna_code = ? AND date = ?", (code, today))
    return {
        "date": today,
        "comuna_code": code,
        "level": risk["level"] if risk else None,
        "boton_rojo_hours": br["hours"] if br else None,
        "source": "Riesgo 30-30-30 de BRASA (Open-Meteo) y Botón Rojo de CONAF",
        "source_url": "https://www.conaf.cl/",
        "note": "Las quemas exigen aviso a CONAF; la autorización la da CONAF o el municipio.",
    }

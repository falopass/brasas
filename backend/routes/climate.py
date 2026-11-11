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
import logging
import os
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query

from backend import fwi as fwi_mod
from backend import lluvia as lluvia_mod
from backend import scars as scars_mod
from backend.geo import territory
from backend.providers import dmc_stations, elevation, noaa, sinca, weather
from backend.routes.common import services
from backend.services import Services, stamp

router = APIRouter(prefix="/api")
log = logging.getLogger(__name__)

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


async def senal_celda(svc: Services, lat: float, lon: float) -> dict:
    """La señal de lluvia del punto, leída o calculada por su celda de 0,1°.

    Devuelve {"senal", "computed_at"}: la peor ventana de 3 horas del pronóstico horario
    y la isoterma 0 °C de su hora central, según `backend/lluvia.py`. La celda comparte
    la llamada a Open-Meteo entre lugares cercanos (media hora de caché, o LLUVIA_RETRY_S
    tras un fallo); si el proveedor cae, `senal` sale en null — nunca se inventa una
    lectura. La usa el punto `/api/climate/lluvia` y la pasada horaria del aviso de
    aluvión (AGUA-04), que así no duplica llamadas a Open-Meteo.
    """
    cache_key = f"lluvia:{round(lat, 1)}:{round(lon, 1)}"
    cached = svc.db.cache_get(cache_key)
    if isinstance(cached, dict) and "senal" in cached:
        return {"senal": cached.get("senal"), "computed_at": cached.get("computed_at") or stamp()}
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
    computed_at = stamp()
    svc.db.cache_set(
        cache_key,
        {"senal": senal, "computed_at": computed_at},
        LLUVIA_TTL_S if senal else LLUVIA_RETRY_S,
    )
    return {"senal": senal, "computed_at": computed_at}


async def _slope_deg(svc: Services, lat: float, lon: float, senal: dict | None, scar_ha: float) -> float | None:
    """Pendiente en grados, solo si hay lluvia, cicatriz o el relieve ya está en caché.

    `slope_aspect` devuelve None si Open-Meteo falla. Cualquier otro error se trata
    igual: la señal de lluvia no puede caerse porque falte el DEM.
    """
    hay_lluvia = bool(senal and (senal.get("mm_3h") or 0) > 0)
    if not (hay_lluvia or scar_ha > 0 or svc.db.cache_get(elevation.cache_key(lat, lon))):
        return None
    try:
        slope_info = await elevation.slope_aspect(svc.db, svc.client, lat, lon)
    except Exception as exc:
        log.warning("Pendiente no disponible en la lluvia del punto: %s", exc)
        return None
    if not slope_info:
        return None
    return float(slope_info[0])


async def _relieve(svc: Services, lat: float, lon: float, senal: dict | None, scar_ha: float) -> dict | None:
    """{"slope_max_deg", "elev_max_m"} a escala de ladera, con la misma guarda de cupo.

    Solo se pide el DEM si hay lluvia prevista, cicatriz a ≤ 5 km o el relieve ya está
    en caché: cada punto nuevo descuenta el cupo de Open-Meteo. Un fallo deja el relieve
    en null — el cruce de aluvión lo declara, no lo inventa.
    """
    hay_lluvia = bool(senal and (senal.get("mm_3h") or 0) > 0)
    if not (hay_lluvia or scar_ha > 0 or svc.db.cache_get(elevation.relieve_cache_key(lat, lon))):
        return None
    try:
        return await elevation.relieve(svc.db, svc.client, lat, lon)
    except Exception as exc:
        log.warning("Relieve de ladera no disponible en la lluvia del punto: %s", exc)
        return None


@router.get("/climate/lluvia")
async def lluvia_punto(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    svc: Services = Depends(services),
):
    """La señal de `backend/lluvia.py` servida como dato, para «Mi zona» (AGUA-09, AGUA-04).

    Es la peor ventana de 3 horas del pronóstico horario del punto y la isoterma 0 °C de
    su hora central: un dato del pronóstico. La celda de 0,1° comparte la llamada a
    Open-Meteo entre lugares cercanos, como `risk_point_at`; si el proveedor falla,
    `senal` sale en null — nunca se inventa una lectura.

    `terreno` cruza esa señal con la pendiente del punto (Copernicus DEM GLO-90), el
    relieve de ladera a 1000 m y la cicatriz a ≤ 5 km del último año (`cicatriz_cerca`,
    AGUA-04): `aviso` es el criterio calibrado que también dispara el aviso a los lugares
    guardados. La celda solo guarda la señal: dos lugares de la misma celda no comparten
    pendiente ni cicatriz.
    """
    dato = await senal_celda(svc, lat, lon)
    senal, computed_at = dato["senal"], dato["computed_at"]
    cicatriz = scars_mod.cicatriz_cerca(svc.db, lat, lon, lluvia_mod.CICATRIZ_DIAS)
    scar_ha = cicatriz["ha"]
    slope_deg = await _slope_deg(svc, lat, lon, senal, scar_ha)
    relieve = await _relieve(svc, lat, lon, senal, scar_ha)
    return {
        "senal": senal,
        "computed_at": computed_at,
        "source": "Open-Meteo · pronóstico horario",
        "source_url": "https://open-meteo.com/",
        "note": "Peor ventana de lluvia en 3 horas e isoterma 0 °C en el punto consultado. "
                + lluvia_mod.ETIQUETA
                + " BRASA avisa a los lugares guardados cuando se cumple el criterio calibrado (docs/ALUVIONES.md).",
        "terreno": lluvia_mod.evaluar_terreno(
            senal, slope_deg, scar_ha, cicatriz.get("dias_desde"), relieve=relieve,
            cicatriz=cicatriz if cicatriz["ha"] > 0 else None,
        ),
    }


DMC_NET_TTL_S = 600   # la red EMA publica cada ~10 minutos; una descarga sirve a todos los lugares
DMC_NET_RETRY_S = 300


@router.get("/climate/station")
async def estacion_cercana(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    svc: Services = Depends(services),
):
    """Última lectura de la estación automática de la DMC más cercana al punto (OFI-33).

    Una sola descarga de la red EMA queda en caché y sirve a todos los lugares: el vecino
    ve una medición real (temperatura, humedad, viento) al lado del pronóstico. Sin
    credenciales en el servidor, sin estación a menos de 25 km o con la fuente caída,
    `station` sale en null — nunca una lectura inventada.
    """
    payload = {"station": None, "source": dmc_stations.SOURCE, "source_url": dmc_stations.SOURCE_URL,
               "note": ("Medición real de la estación automática DMC más cercana (hasta 25 km y "
                        "de las últimas 3 horas); no es un pronóstico.")}
    if not (svc.settings.dmc_usuario and svc.settings.dmc_token):
        return payload
    stations = svc.db.cache_get("dmc:red")
    if stations is None:
        try:
            stations = await dmc_stations.fetch_network(svc.client, svc.settings.dmc_usuario,
                                                      svc.settings.dmc_token)
        except dmc_stations.DmcStationsError as exc:
            log.warning("Red EMA de la DMC sin datos: %s", exc)
            stations = []
        svc.db.cache_set("dmc:red", stations, DMC_NET_TTL_S if stations else DMC_NET_RETRY_S)
    if stations:
        payload["station"] = dmc_stations.nearest(stations, lat, lon)
    return payload


SINCA_NET_TTL_S = 1800   # el resumen por estación se actualiza cada hora; la descarga sirve a todos
SINCA_NET_RETRY_S = 300


@router.get("/climate/air")
async def aire_medido(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    svc: Services = Depends(services),
):
    """El MP2,5 medido por la estación SINCA más cercana al punto (OFI-10).

    Una descarga del listado de la red queda en caché 30 min y sirve a todos los lugares:
    el vecino ve una medición real (con su ICAP y estado) al lado del pronóstico de humo.
    La red no exige credenciales. Sin estación a menos de 60 km, lectura atrasada o fuente
    caída, `air` sale en null — nunca un valor inventado. Los valores SINCA son
    **preliminares** hasta que el MMA los valida; así se declaran.
    """
    payload = {"air": None, "source": sinca.SOURCE, "source_url": sinca.SOURCE_URL,
               "source_mode": "unavailable", "status": "unavailable", "fetched_at": None,
               "note": ("MP2,5 medido por la estación SINCA más cercana (hasta 60 km y de las "
                        "últimas 6 horas), con su ICAP. Dato preliminar del MMA, no un pronóstico.")}
    snap_path = os.getenv("SINCA_SNAPSHOT_PATH", "").strip() or str(svc.settings.data_dir / "sinca_snapshot.json")
    cached = svc.db.cache_get("sinca:red")
    if isinstance(cached, dict) and cached.get("source_mode") == "snapshot":
        if sinca.snapshot_remaining_ttl_s(cached) <= 0:
            cached = None
    if cached is None:
        try:
            meta = await sinca.fetch_network_with_meta(svc.client, snapshot_path=snap_path)
        except sinca.SincaError as exc:
            log.warning("Red SINCA sin datos: %s", exc)
            meta = {"stations": [], "source_mode": "unavailable", "status": "unavailable", "fetched_at": None}
        if meta.get("stations"):
            if meta.get("source_mode") == "snapshot":
                rem = sinca.snapshot_remaining_ttl_s(meta)
                ttl = min(SINCA_NET_TTL_S, rem) if rem > 0 else 0
            else:
                ttl = SINCA_NET_TTL_S
        else:
            ttl = SINCA_NET_RETRY_S
        if ttl > 0:
            svc.db.cache_set("sinca:red", meta, ttl)
    elif isinstance(cached, list):
        meta = {"stations": cached, "source_mode": "live" if cached else "unavailable",
                "status": "ok" if cached else "unavailable", "fetched_at": None}
    else:
        meta = cached
    stations = meta.get("stations") or []
    payload["source_mode"] = meta.get("source_mode") or ("live" if stations else "unavailable")
    payload["status"] = meta.get("status") or ("ok" if stations else "unavailable")
    payload["fetched_at"] = meta.get("fetched_at")
    if stations:
        air = sinca.nearest(stations, lat, lon)
        if air is not None:
            air = {**air, "source_mode": payload["source_mode"], "fetched_at": payload["fetched_at"]}
        payload["air"] = air
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

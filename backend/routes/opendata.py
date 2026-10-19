"""Datos abiertos de BRASA en GeoJSON, de solo lectura.

Seis conjuntos con la misma forma (`FeatureCollection`) para que cualquiera pueda
reusar lo que BRASA ya calcula: incidentes abiertos, detecciones satelitales, riesgo por
comuna, rayos GLM recientes, los polígonos de humo que ve GOES-19 y el pronóstico oficial
Botón Rojo de CONAF (`boton-rojo.json`, un FeatureCollection de puntos servido como JSON).
Un séptimo (`response.json`) resume cuánto tarda la respuesta oficial según las marcas que
publica CONAF. No hay datos de personas aquí: ni lugares guardados, ni dispositivos, ni
reportes sin verificar.

Cada conjunto dice su fuente y su límite. El índice (`GET /api/opendata/`) los describe, así que la
API se explica sola y no depende de una página que se desactualice.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from backend import response as response_mod
from backend.geo import territory
from backend.providers import conaf, glm, smoke
from backend.routes.common import services
from backend.services import Services

router = APIRouter(prefix="/api/opendata")

CHILE_TZ = ZoneInfo("America/Santiago")
MAX_FEATURES = 5000

STATUS_LABELS = {
    "anomalia": "Anomalía de calor", "posible": "Posible incendio", "reportado": "Reportado por vecinos",
    "confirmado": "Confirmado por CONAF", "controlado": "Controlado", "extinguido": "Extinguido",
    "descartado": "Descartado",
}
OPEN_STATES = ("anomalia", "posible", "reportado", "confirmado", "controlado")

NOT_OFFICIAL = ("BRASA no es una fuente oficial. Los incidentes agrupan detecciones satelitales y pueden "
                "ser quemas, industrias o falsos positivos; «confirmado» solo cuando lo informa CONAF. "
                "Sigue a SENAPRED y a CONAF para decisiones de emergencia.")


def _response(collection: dict[str, Any], max_age: int, media_type: str = "application/geo+json") -> Response:
    """El conjunto con su tipo MIME y caché corta: los datos cambian cada pocos minutos."""
    return Response(content=json.dumps(collection, ensure_ascii=False, separators=(",", ":")),
                    media_type=media_type,
                    headers={"Cache-Control": f"public, max-age={max_age}"})


def _point(lon: float, lat: float) -> dict[str, Any]:
    return {"type": "Point", "coordinates": [round(lon, 4), round(lat, 4)]}


def _collection(features: list[dict[str, Any]], source: str, **extra: Any) -> dict[str, Any]:
    # Quien consulta pide MAX_FEATURES + 1 elementos: el extra solo marca que hubo recorte.
    delivered = features[:MAX_FEATURES]
    return {"type": "FeatureCollection", "source": source, "not_official": NOT_OFFICIAL,
            "count": len(delivered), "limit": MAX_FEATURES, "truncated": len(features) > MAX_FEATURES,
            **extra, "features": delivered}


@router.get("")
def index() -> dict[str, Any]:
    """Índice de los conjuntos: qué hay, con qué parámetros y qué significa cada campo."""
    return {
        "name": "BRASA Chile · datos abiertos",
        "access": "solo lectura, sin registro ni clave",
        "not_official": NOT_OFFICIAL,
        "datasets": [
            {"id": "incidents", "url": "/api/opendata/incidents.geojson",
             "params": {"hours": "1–336 (48 por defecto)", "include_fixed": "true/false (fuentes fijas probables)"},
             "geometry": "Point: centro de la evidencia del incidente",
             "properties": ["id", "status", "status_label", "n_obs", "n_reliable", "sensors", "fixed_source",
                            "max_frp", "first_seen_at", "last_seen_at", "comuna", "region", "bbox"],
             "source": "NASA FIRMS y NOAA GOES agrupados por BRASA"},
            {"id": "observations", "url": "/api/opendata/observations.geojson",
             "params": {"hours": "1–72 (6 por defecto)", "source": "filtro opcional por producto"},
             "geometry": "Point: centro del píxel de la detección",
             "properties": ["id", "source", "sensor", "satellite", "confidence", "frp_mw", "observed_at", "comuna"],
             "source": "NASA FIRMS (VIIRS/MODIS) y NOAA GOES"},
            {"id": "risk", "url": "/api/opendata/risk.geojson",
             "params": {"day": "AAAA-MM-DD (hoy por defecto)"},
             "geometry": "Point: centroide de la comuna (el polígono está en el visor)",
             "properties": ["comuna_code", "comuna", "region", "level", "level_combined", "score", "fwi",
                            "fwi_level"],
             "source": "Open-Meteo (pronóstico, centro de cada comuna) y BRASA"},
            {"id": "lightning", "url": "/api/opendata/lightning.geojson",
             "params": {"hours": "1–6 (1 por defecto)"},
             "geometry": "Point: centro óptico del destello detectado",
             "properties": ["id", "observed_at", "age_s", "energy_j", "area_km2"],
             "source": "NOAA GOES-19 GLM (dominio público)"},
            {"id": "smoke", "url": "/api/opendata/smoke.geojson",
             "params": {"hours": "1–6 (1 por defecto)"},
             "geometry": "Polygon: mancha contigua de humo del barrido (10 min)",
             "properties": ["observed_at", "age_min", "cells"],
             "source": "NOAA GOES-19 ABI-L2-ADPF (dominio público)"},
            {"id": "response", "url": "/api/opendata/response.json",
             "params": {"season": "AAAA-AAAA (la más reciente en la tabla por defecto)"},
             "properties": ["season", "overall", "comunas", "buckets", "count", "excluded"],
             "source": conaf.FIRES_SOURCE},
            {"id": "boton-rojo", "url": "/api/opendata/boton-rojo.json",
             "params": {"day": "AAAA-MM-DD (un solo día; todos los guardados por defecto)",
                        "days": "1–14 (14 por defecto: los días más recientes de la tabla)"},
             "geometry": "Point: centroide de la comuna (el polígono está en el visor)",
             "properties": ["comuna_code", "comuna", "region", "date", "hours", "area_ha",
                            "proportion", "fetched_at"],
             "source": conaf.SOURCE},
        ],
        "limits": {"max_features": MAX_FEATURES, "cached": "60 a 600 segundos por conjunto",
                   "truncated": ("true cuando el conjunto tenía más de max_features elementos y se entregó "
                                 "recortado; pide una ventana más corta (hours menor) o filtra por source"),
                   "response": "se calcula solo sobre la temporada pedida"},
        "license": ("Los datos de origen conservan su condición: CONAF y DMC son de sus organismos "
                    "(la DMC los publica como dominio público); NASA y NOAA son de dominio público. "
                    "El cálculo derivado de BRASA se puede reusar citando la fuente."),
    }


@router.get("/incidents.geojson")
def incidents_geojson(
    hours: int = Query(48, ge=1, le=24 * 14),
    include_fixed: bool = Query(False, description="Incluir fuentes de calor fijas probables (volcanes, industria)"),
    svc: Services = Depends(services),
):
    """Incidentes abiertos (agrupaciones de detecciones) de las últimas horas."""
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    states = ",".join("?" * len(OPEN_STATES))
    sql = (f"SELECT * FROM incidents WHERE status IN ({states}) AND last_seen_at >= ?")
    params: list[Any] = [*OPEN_STATES, since]
    if not include_fixed:
        sql += " AND fixed_source = 0"
    rows = svc.db.query(sql + " ORDER BY last_seen_at DESC LIMIT ?", (*params, MAX_FEATURES + 1))
    t = territory()
    features = []
    for row in rows:
        comuna = t.by_code.get(row["comuna_code"])
        features.append({
            "type": "Feature", "geometry": _point(row["lon"], row["lat"]),
            "properties": {
                "id": row["id"], "status": row["status"],
                "status_label": STATUS_LABELS.get(row["status"], row["status"]),
                "n_obs": row["n_obs"], "n_reliable": row["n_reliable"],
                "sensors": [s.strip() for s in row["sensors"].split(",") if s.strip()],
                "fixed_source": bool(row["fixed_source"]), "max_frp": row["max_frp"],
                "first_seen_at": row["first_seen_at"], "last_seen_at": row["last_seen_at"],
                "comuna": comuna.name if comuna else None, "region": comuna.region if comuna else None,
                "bbox": [row["min_lon"], row["min_lat"], row["max_lon"], row["max_lat"]],
            },
        })
    return _response(_collection(features, "NASA FIRMS y NOAA GOES agrupados por BRASA",
                                 generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                 hours=hours), max_age=60)


@router.get("/observations.geojson")
def observations_geojson(
    hours: int = Query(6, ge=1, le=72),
    source: str | None = Query(None, max_length=64, description="Producto, por ejemplo VIIRS_NOAA20_NRT"),
    svc: Services = Depends(services),
):
    """Detecciones satelitales recientes. Un punto no es un incendio: es una señal de calor."""
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    sql = ("SELECT id, source, sensor, satellite, confidence, frp_mw, observed_at, lat, lon, comuna_code "
           "FROM observations WHERE observed_at >= ?")
    params: list[Any] = [since]
    if source:
        sql += " AND source = ?"
        params.append(source)
    rows = svc.db.query(sql + " ORDER BY observed_at DESC LIMIT ?", (*params, MAX_FEATURES + 1))
    t = territory()
    features = []
    for row in rows:
        comuna = t.by_code.get(row["comuna_code"])
        features.append({
            "type": "Feature", "geometry": _point(row["lon"], row["lat"]),
            "properties": {"id": row["id"], "source": row["source"], "sensor": row["sensor"],
                           "satellite": row["satellite"], "confidence": row["confidence"],
                           "frp_mw": row["frp_mw"], "observed_at": row["observed_at"],
                           "comuna": comuna.name if comuna else None},
        })
    return _response(_collection(features, "NASA FIRMS (VIIRS/MODIS) y NOAA GOES",
                                 generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                 hours=hours), max_age=60)


@router.get("/risk.geojson")
def risk_geojson(day: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"), svc: Services = Depends(services)):
    """Riesgo por comuna de un día: el 30-30-30 y su combinación con el FWI, en el centroide."""
    target = day or datetime.now(CHILE_TZ).date().isoformat()
    try:
        datetime.fromisoformat(target)
    except ValueError:
        raise HTTPException(422, "La fecha debe tener el formato AAAA-MM-DD.") from None
    rows = svc.db.query("SELECT comuna_code, level, level_combined, score, fwi, fwi_level FROM risk_daily "
                        "WHERE date = ? LIMIT ?", (target, MAX_FEATURES + 1))
    t = territory()
    features = []
    for row in rows:
        comuna = t.by_code.get(row["comuna_code"])
        if not comuna:
            continue
        features.append({
            "type": "Feature", "geometry": _point(comuna.center[0], comuna.center[1]),
            "properties": {**dict(row), "comuna": comuna.name, "region": comuna.region},
        })
    return _response(_collection(features, "Open-Meteo y BRASA", date=target,
                                 method=("30-30-30 horario en el centroide; el nivel combinado añade el FWI "
                                         "del mismo día. Es peligro de propagación, no probabilidad de ignición.")),
                     max_age=600)


# Un archivo GLM pesa varios MB y una ventana puede juntar cientos: 5 minutos por ventana.
_LIGHTNING_CACHE_S = 300
_LIGHTNING_CACHE: dict[int, tuple[float, list[dict[str, Any]]]] = {}


@router.get("/lightning.geojson")
async def lightning_geojson(hours: int = Query(1, ge=1, le=6), svc: Services = Depends(services)):
    """Rayos (destellos) del GLM de GOES-19 sobre Chile de las últimas horas (máximo 6).

    Un destello no es un incendio: es luz de tormenta vista desde el satélite. Sobre pasto
    seco puede ser una ignición que todavía no tiene humo, por eso se publica igual.

    El tope de 6 horas por pedido (422 sobre eso) acota el costo: cada hora son ~180
    archivos LCFA de varios MB que se descargan de S3 en cada cache-miss.
    """
    cached = _LIGHTNING_CACHE.get(hours)
    flashes = cached[1] if cached and cached[0] > time.monotonic() else None
    if flashes is None:
        try:
            flashes = await glm.fetch_flashes(svc.client, hours)
        except Exception as exc:  # S3 caído o lento: el conjunto no está disponible, la API sí
            raise HTTPException(503, "Los rayos GLM no están disponibles ahora "
                                f"({type(exc).__name__}). Intenta de nuevo en unos minutos.") from exc
        _LIGHTNING_CACHE[hours] = (time.monotonic() + _LIGHTNING_CACHE_S, flashes)
    now = datetime.now(timezone.utc)
    features = []
    for flash in flashes[:MAX_FEATURES + 1]:
        observed = datetime.fromisoformat(flash["observed_at"].replace("Z", "+00:00"))
        features.append({
            "type": "Feature", "geometry": _point(flash["lon"], flash["lat"]),
            "properties": {"id": flash["id"], "observed_at": flash["observed_at"],
                           "age_s": max(0, int((now - observed).total_seconds())),
                           "energy_j": flash.get("energy_j"), "area_km2": flash.get("area_km2")},
        })
    return _response(_collection(features, "NOAA GOES-19 GLM (dominio público)",
                                 generated_at=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                 hours=hours),
                     max_age=60)


# Un archivo ADPF pesa ~1 MB y una hora junta ~6: 5 minutos por ventana, como el GLM.
_SMOKE_CACHE_S = 300
_SMOKE_CACHE: dict[int, tuple[float, list[dict[str, Any]]]] = {}


@router.get("/smoke.geojson")
async def smoke_geojson(hours: int = Query(1, ge=1, le=6), svc: Services = Depends(services)):
    """Polígonos de humo que GOES-19 ve sobre Chile en las últimas horas.

    Humo de satélite no es incendio confirmado: es aerosol detectado por el ABI cada
    ~10 minutos, útil para ver hacia dónde se mueve la pluma.
    """
    cached = _SMOKE_CACHE.get(hours)
    polys = cached[1] if cached and cached[0] > time.monotonic() else None
    if polys is None:
        try:
            polys = smoke.polygons(await smoke.fetch_smoke(svc.client, hours))
        except Exception as exc:  # S3 caído o sin archivos recientes: el conjunto no está, la API sí
            raise HTTPException(503, "El humo GOES-19 no está disponible ahora "
                                f"({type(exc).__name__}). Intenta de nuevo en unos minutos.") from exc
        _SMOKE_CACHE[hours] = (time.monotonic() + _SMOKE_CACHE_S, polys)
    now = datetime.now(timezone.utc)
    features = []
    for poly in polys[:MAX_FEATURES + 1]:
        observed = datetime.fromisoformat(poly["observed_at"].replace("Z", "+00:00"))
        features.append({
            "type": "Feature", "geometry": poly["geometry"],
            "properties": {"observed_at": poly["observed_at"],
                           "age_min": max(0, int((now - observed).total_seconds() // 60)),
                           "cells": poly["cells"]},
        })
    return _response(_collection(features, "NOAA GOES-19 ABI-L2-ADPF (dominio público)",
                                 generated_at=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                 hours=hours),
                     max_age=60)


@router.get("/boton-rojo.json")
def boton_rojo_json(
    day: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    days: int = Query(14, ge=1, le=14),
    svc: Services = Depends(services),
):
    """Pronóstico oficial Botón Rojo de CONAF: horas en condición por comuna y día.

    Un FeatureCollection de puntos (centroide de la comuna) servido como `application/json`
    para que se baje y abra como cualquier JSON. Con `day` devuelve un solo día; sin él, los
    `days` días más recientes presentes en la tabla (que guarda hasta 14). Botón Rojo marca
    condiciones favorables para que un incendio se inicie y propague: nunca un incendio
    detectado. Con la tabla vacía responde 200 igual, con `count: 0` y `features: []`.
    """
    sql = "SELECT comuna_code, date, hours, area_ha, proportion, fetched_at FROM boton_rojo "
    params: list[Any] = []
    if day:
        try:
            datetime.fromisoformat(day)
        except ValueError:
            raise HTTPException(422, "La fecha debe tener el formato AAAA-MM-DD.") from None
        sql += "WHERE date = ? ORDER BY comuna_code"
        params.append(day)
    else:
        sql += ("WHERE date IN (SELECT DISTINCT date FROM boton_rojo ORDER BY date DESC LIMIT ?) "
                "ORDER BY date, comuna_code")
        params.append(days)
    rows = svc.db.query(sql + " LIMIT ?", (*params, MAX_FEATURES))
    t = territory()
    features = []
    for row in rows:
        comuna = t.by_code.get(row["comuna_code"])
        if not comuna:
            continue
        features.append({
            "type": "Feature", "geometry": _point(comuna.center[0], comuna.center[1]),
            "properties": {"comuna_code": row["comuna_code"], "comuna": comuna.name, "region": comuna.region,
                           "date": row["date"], "hours": row["hours"], "area_ha": row["area_ha"],
                           "proportion": row["proportion"], "fetched_at": row["fetched_at"]},
        })
    extra: dict[str, Any] = {"date": day} if day else {"days": days}
    return _response(_collection(features, conaf.SOURCE, source_url=conaf.DASHBOARD_URL, **extra,
                                 generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                 count=len(features),
                                 method=("Horas al día en condición Botón Rojo por comuna, con la superficie "
                                         "que la cumple y su proporción de la comuna. Información propiedad "
                                         "de CONAF, republicada citándola.")),
                     max_age=600, media_type="application/json")


@router.get("/response.json")
def response_times(season: str | None = Query(None, pattern=r"^\d{4}-\d{4}$"), svc: Services = Depends(services)):
    """Radar de respuesta oficial: medianas de los tiempos entre detección, aviso y despacho de CONAF.

    No es GeoJSON (no hay geometría): es un resumen estadístico de la temporada pedida o de la más
    reciente presente en la tabla. Sin incendios con marcas publicadas responde 200 igual, con
    `count: 0` y una nota: la ausencia de datos también es información.
    """
    if season is None:
        latest = svc.db.one("SELECT MAX(season) AS s FROM official_fires WHERE season IS NOT NULL")
        season = latest["s"] if latest else None
    rows = (svc.db.query("SELECT detected_at, alerted_at, dispatched_at, comuna, area_ha "
                         "FROM official_fires WHERE season = ?", (season,)) if season else [])
    body = {"type": "response_times", "season": season,
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source": conaf.FIRES_SOURCE, "source_url": conaf.FIRES_PAGE_URL,
            "method": ("Medianas de las marcas que publica CONAF en su reporte de incendios: detección, "
                       "aviso a los equipos y despacho de recursos. No es una medición propia de BRASA "
                       "y no incluye la hora de arribo al incendio, porque el CSV no la trae."),
            "count": len(rows), "limit": MAX_FEATURES, "truncated": len(rows) > MAX_FEATURES,
            **response_mod.aggregate(rows)}
    if not rows:
        body["note"] = "Todavía no hay suficientes incendios con horas publicadas."
    return Response(content=json.dumps(body, ensure_ascii=False, separators=(",", ":")),
                    media_type="application/json",
                    headers={"Cache-Control": "public, max-age=600"})

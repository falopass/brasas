"""API pública: configuración, estado de fuentes, observaciones, exploración FIRMS, riesgo y clima."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.geo import territory
from backend.notify import webpush
from backend.providers import firms, weather
from backend.risk import LEVEL_LABELS
from backend.routes.common import services
from backend.services import Services, stamp

router = APIRouter(prefix="/api")
CHILE_TZ = ZoneInfo("America/Santiago")
RECENT_ARCHIVE_DAYS = 60


@router.get("/health")
def health():
    return {"status": "ok", "name": "BRASA Chile", "version": "0.2.0", "time_utc": stamp()}


@router.get("/config")
def config(svc: Services = Depends(services)):
    s = svc.settings
    _, public_key = webpush.ensure_keys(svc.db)
    return {
        "version": "0.2.0",
        "ion_public_token": s.cesium_ion_token,
        "firms_configured": bool(s.firms_map_key),
        "goes_enabled": s.goes_enabled,
        "telegram": {"enabled": bool(s.telegram_bot_token and s.telegram_bot_username), "username": s.telegram_bot_username or None},
        "push": {"public_key": public_key},
        "moderation_enabled": bool(s.admin_token),
        "zones": territory().zones(),
        "risk_levels": LEVEL_LABELS,
    }


@router.get("/status")
def status(svc: Services = Depends(services)):
    """Estado de cada fuente: última ejecución, último éxito y latencia de datos."""
    runs = svc.db.query(
        "SELECT r.provider, r.product, r.started_at, r.finished_at, r.ok, r.n_records, r.n_new, r.message FROM ingest_runs r "
        "JOIN (SELECT product, MAX(id) AS id FROM ingest_runs GROUP BY product) last ON last.id = r.id ORDER BY r.provider")
    last_ok = {r["product"]: r["finished_at"] for r in svc.db.query(
        "SELECT product, MAX(finished_at) AS finished_at FROM ingest_runs WHERE ok = 1 GROUP BY product")}
    newest = {r["source"]: r["t"] for r in svc.db.query("SELECT source, MAX(observed_at) AS t FROM observations GROUP BY source")}
    for r in runs:
        r["last_ok_at"] = last_ok.get(r["product"])
        r["ok"] = bool(r["ok"])
    return {
        "time_utc": stamp(),
        "last_ingest_at": svc.db.kv_get("last_ingest_at"),
        "risk_computed_at": svc.db.kv_get("risk_computed_at"),
        "scheduler_enabled": svc.settings.scheduler_enabled,
        # "interna": tareas en este proceso · "cron": la dispara un programador externo (Cloudflare) · "apagada"
        "ingest_mode": "interna" if svc.settings.scheduler_enabled else "cron" if svc.settings.internal_token else "apagada",
        "firms_configured": bool(svc.settings.firms_map_key),
        "runs": runs,
        "newest_observation": newest,
    }


@router.get("/observations")
def observations(
    hours: int = Query(48, ge=1, le=24 * 14),
    bbox: str | None = Query(None, description="west,south,east,north"),
    reliable: bool = Query(False, description="Solo confianza nominal/alta (VIIRS/MODIS) o alta/media (GOES)"),
    svc: Services = Depends(services),
):
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    sql = "SELECT * FROM observations WHERE observed_at >= ?"
    params: list = [since]
    if bbox:
        try:
            west, south, east, north = (float(v) for v in bbox.split(","))
        except ValueError:
            raise HTTPException(422, "bbox debe ser west,south,east,north") from None
        sql += " AND lon BETWEEN ? AND ? AND lat BETWEEN ? AND ?"
        params += [west, east, south, north]
    if reliable:
        sql += " AND confidence IN ('alta','nominal','media')"
    rows = svc.db.query(sql + " ORDER BY observed_at DESC LIMIT 20000", tuple(params))
    by_code = territory().by_code
    for row in rows:
        comuna = by_code.get(row["comuna_code"])
        row["comuna"] = comuna.name if comuna else None
        row["region"] = comuna.region if comuna else None
    return {
        "type": "observations", "hours": hours, "count": len(rows),
        "data_as_of": svc.db.kv_get("last_ingest_at"),
        "explanation": "Detecciones térmicas satelitales: no son incendios confirmados ni perímetros.",
        "points": rows,
    }


@router.get("/explore")
async def explore(
    zone: str = "chile",
    mode: Literal["recent", "historical"] = "recent",
    days: int = Query(3, ge=1, le=10),
    start: date | None = None,
    svc: Services = Depends(services),
):
    """Consulta directa a FIRMS por zona y ventana (reciente o histórica)."""
    zones = territory().zones()
    if zone not in zones:
        raise HTTPException(422, "Zona no disponible.")
    today = datetime.now(timezone.utc).date()
    if mode == "historical" and not start:
        raise HTTPException(422, "En modo histórico debes indicar la fecha de inicio (AAAA-MM-DD).")
    if mode == "recent" and start:
        raise HTTPException(422, "El modo reciente no admite fecha de inicio.")
    if start and start > today:
        raise HTTPException(422, "La fecha de inicio no puede estar en el futuro.")
    if start and start < date(2000, 11, 1):
        raise HTTPException(422, "No hay archivo satelital FIRMS anterior a noviembre de 2000.")
    key = svc.settings.firms_map_key
    if not key:
        raise HTTPException(503, {"code": "FIRMS_KEY_MISSING",
                                  "message": "Configura FIRMS_MAP_KEY en .env. Solicita una clave gratuita a NASA FIRMS."})
    notices: list[str] = []
    end = None
    query_start = start
    if mode == "recent":
        sources = svc.settings.firms_sources
        if days > firms.MAX_DAYS_PER_REQUEST:  # la API admite 5 días por solicitud: se consulta por tramos
            query_start, end = today - timedelta(days=days - 1), today
    else:
        end = min(start + timedelta(days=days - 1), today)
        if end < start + timedelta(days=days - 1):
            notices.append(f"La ventana se recortó a hoy ({end.isoformat()}).")
        if (today - start).days <= RECENT_ARCHIVE_DAYS:
            sources = svc.settings.firms_sources
            notices.append("Fecha reciente: se usan productos NRT (el archivo científico SP tarda meses en publicarse).")
        else:
            sources = tuple(s for s in ("VIIRS_NOAA20_SP", "VIIRS_SNPP_SP", "MODIS_SP")
                            if start.isoformat() >= firms.PRODUCTS[s]["min_date"])
    bbox = zones[zone]["bbox"]
    cache_key = f"explore:{zone}:{mode}:{days}:{start}:{','.join(sources)}"
    cached = svc.db.cache_get(cache_key)
    if cached:
        return cached
    try:
        points, provider_notices = await firms.fetch_hotspots(key, bbox, sources, days=min(days, firms.MAX_DAYS_PER_REQUEST),
                                                              start=query_start, end=end, client=svc.client)
    except firms.UpstreamError as exc:
        raise HTTPException(502, str(exc)) from None
    t = territory()
    for p in points:
        comuna = t.locate(p["lat"], p["lon"])
        p["comuna_code"], p["comuna"], p["region"] = (comuna.code, comuna.name, comuna.region) if comuna else (None, None, None)
    in_chile = sum(1 for p in points if p["comuna_code"] is not None)
    payload = {
        "type": "hotspots", "mode": mode, "zone": zone, "days": days, "start": start.isoformat() if start else None,
        "end": end.isoformat() if end else None, "sources": list(sources),
        "retrieved_at_utc": stamp(), "notices": notices + provider_notices,
        "in_chile": in_chile, "outside_chile": len(points) - in_chile,
        "explanation": "Detecciones térmicas satelitales, no incendios confirmados ni perímetros.",
        "points": points,
    }
    svc.db.cache_set(cache_key, payload, 900 if mode == "recent" else 86400 * 7)
    return payload


@router.get("/risk")
def risk_map(day: date | None = None, svc: Services = Depends(services)):
    day = day or datetime.now(CHILE_TZ).date()
    rows = svc.db.query("SELECT * FROM risk_daily WHERE date = ?", (day.isoformat(),))
    dates = [r["date"] for r in svc.db.query("SELECT DISTINCT date FROM risk_daily WHERE date >= ? ORDER BY date LIMIT 8",
                                             ((datetime.now(CHILE_TZ).date()).isoformat(),))]
    worst = svc.db.query(
        "SELECT date, SUM(level = 'extremo') AS extremo, SUM(level = 'alto') AS alto, SUM(level = 'moderado') AS moderado "
        "FROM risk_daily WHERE date >= ? GROUP BY date ORDER BY date LIMIT 8", (datetime.now(CHILE_TZ).date().isoformat(),))
    return {
        "date": day.isoformat(), "dates": dates, "summary": worst,
        "computed_at": svc.db.kv_get("risk_computed_at"),
        "method": "Regla 30-30-30 evaluada hora a hora: temperatura >30 °C, humedad <30 % y viento >30 km/h (Open-Meteo, centro de cada comuna).",
        "comunas": {str(r["comuna_code"]): {"level": r["level"], "score": r["score"], "h3": r["hours_3of3"], "h2": r["hours_2of3"],
                                             "tmax": r["tmax"], "rhmin": r["rhmin"], "windmax": r["windmax"], "gustmax": r["gustmax"]}
                    for r in rows},
    }


@router.get("/risk/{code}")
def risk_comuna(code: int, svc: Services = Depends(services)):
    comuna = territory().by_code.get(code)
    if not comuna:
        raise HTTPException(404, "Comuna no encontrada.")
    today = datetime.now(CHILE_TZ).date().isoformat()
    days = svc.db.query("SELECT * FROM risk_daily WHERE comuna_code = ? AND date >= ? ORDER BY date", (code, today))
    hourly = svc.db.one("SELECT computed_at, payload FROM risk_hourly WHERE comuna_code = ?", (code,))
    return {"comuna": comuna.as_dict(), "days": days,
            "hours": json.loads(hourly["payload"]) if hourly else [],
            "computed_at": hourly["computed_at"] if hourly else None}


@router.get("/weather")
async def current_weather(lat: float = Query(..., ge=-90, le=90), lon: float = Query(..., ge=-180, le=180),
                          svc: Services = Depends(services)):
    """Condiciones actuales MODELADAS (Open-Meteo) en un punto."""
    cache_key = f"weather:{lat:.2f}:{lon:.2f}"
    cached = svc.db.cache_get(cache_key)
    if cached:
        return cached
    try:
        data = await weather.current(svc.client, lat, lon)
    except weather.WeatherError as exc:
        raise HTTPException(502, "El proveedor meteorológico no respondió.") from exc
    payload = {"source": "Open-Meteo", "kind": "modelled_current_weather", "coordinates": [lon, lat], **data}
    svc.db.cache_set(cache_key, payload, 600)
    return payload


@router.get("/locate")
def locate(lat: float = Query(..., ge=-90, le=90), lon: float = Query(..., ge=-180, le=180), svc: Services = Depends(services)):
    comuna = territory().locate(lat, lon)
    if not comuna:
        return {"comuna": None}
    today = datetime.now(CHILE_TZ).date().isoformat()
    risk = svc.db.one("SELECT level, score, tmax, rhmin, windmax FROM risk_daily WHERE comuna_code = ? AND date = ?", (comuna.code, today))
    return {"comuna": comuna.as_dict(), "risk_today": risk}


@router.get("/priority-comunas")
def priority_comunas():
    from backend.settings import ROOT

    return json.loads((ROOT / "web" / "data" / "prioritarias.json").read_text(encoding="utf-8"))

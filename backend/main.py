"""Servidor y API del MVP BRASA Chile. No contiene datos inventados."""
from __future__ import annotations

import os
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Literal

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.providers import REGIONS, UpstreamError, fetch_hotspots

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
app = FastAPI(title="BRASA Chile API", version="0.1.0", description="Detecciones satelitales observadas, no alertas oficiales.")
app.mount("/web", StaticFiles(directory=str(ROOT / "web")), name="web")

CACHE: dict[tuple, tuple[float, dict]] = {}


@app.get("/")
def root():
    return FileResponse(ROOT / "web" / "index.html")


@app.get("/api/health")
def health():
    return {"status": "ok", "name": "BRASA Chile", "time_utc": datetime.now(timezone.utc).isoformat()}


@app.get("/api/config")
def config():
    # Cesium ion requiere un token PUBLICO restringido. La clave FIRMS jamas sale del servidor.
    return {
        "ion_public_token": os.getenv("CESIUM_ION_PUBLIC_TOKEN", "").strip(),
        "firms_configured": bool(os.getenv("FIRMS_MAP_KEY", "").strip()),
        "regions": REGIONS,
    }


@app.get("/api/hotspots")
async def hotspots(
    region: str = "maule",
    mode: Literal["recent", "historical"] = "recent",
    days: int = Query(3, ge=1, le=5),
    start: date | None = None,
):
    if region not in REGIONS:
        raise HTTPException(422, "Región no disponible")
    if mode == "historical" and not start:
        raise HTTPException(422, "En modo histórico debes enviar 'start' (AAAA-MM-DD).")
    if mode == "recent" and start:
        raise HTTPException(422, "El modo reciente no admite 'start'.")
    if start and start > datetime.now(timezone.utc).date():
        raise HTTPException(422, "La fecha histórica no puede estar en el futuro.")
    key = os.getenv("FIRMS_MAP_KEY", "").strip()
    if not key:
        raise HTTPException(status_code=503, detail={
            "code": "FIRMS_KEY_MISSING",
            "message": "Configura FIRMS_MAP_KEY en .env. Solicita una clave gratuita a NASA FIRMS.",
        })

    cache_key = (region, mode, days, str(start))
    now = time.monotonic()
    ttl_seconds = 900 if mode == "recent" else 86400
    saved = CACHE.get(cache_key)
    if saved and saved[0] > now:
        return saved[1]
    try:
        points, warnings = await fetch_hotspots(key, region, mode, days, start)
    except UpstreamError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    payload = {
        "type": "hotspots", "mode": mode, "region": region, "days": days,
        "start": start.isoformat() if start else None,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "bbox_is_approximate": True,
        "notices": warnings,
        "explanation": "Detecciones termicas satelitales, no incendios confirmados ni perimetros. El filtro geografico es aproximado.",
        "points": points,
    }
    # Limitar tamaño de memoria en una demo; producción usa BD y cache distribuido.
    if len(CACHE) >= 80:
        CACHE.clear()
    CACHE[cache_key] = (now + ttl_seconds, payload)
    return payload


@app.get("/api/weather")
async def weather(lat: float = Query(..., ge=-90, le=90), lon: float = Query(..., ge=-180, le=180)):
    """Meteo ACTUAL de un punto. No corresponde a un incendio histórico."""
    params = {
        "latitude": lat, "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,wind_direction_10m",
        "timezone": "America/Santiago",
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get("https://api.open-meteo.com/v1/forecast", params=params)
            response.raise_for_status()
            data = response.json()
    except (httpx.RequestError, httpx.HTTPStatusError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="El proveedor meteorológico no respondió.") from exc
    return {"source": "Open-Meteo", "kind": "modelled_current_weather", "coordinates": [lon, lat], "data": data.get("current", {}), "units": data.get("current_units", {})}

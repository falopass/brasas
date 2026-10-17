"""Proveedores externos: datos termicos FIRMS y meteo Open-Meteo.

BRASA no infiere incendios confirmados ni perimetros desde los focos FIRMS.
Las cajas geograficas son APROXIMADAS y pueden contener puntos de paises vecinos.
"""
from __future__ import annotations

import asyncio
import csv
from dataclasses import dataclass
from datetime import date, datetime, timezone
from io import StringIO
from typing import Any

import httpx

# west,south,east,north. No equivalen a limites administrativos oficiales.
REGIONS: dict[str, dict[str, Any]] = {
    "chile": {"label": "Chile continental (aproximado)", "bbox": [-76.8, -56.1, -66.0, -17.4], "camera": [-70.1, -35.4, 2450000]},
    "norte": {"label": "Norte (aproximado)", "bbox": [-71.9, -30.6, -66.0, -17.4], "camera": [-69.4, -24.4, 1160000]},
    "valparaiso": {"label": "Valparaíso", "bbox": [-72.2, -33.65, -70.0, -32.0], "camera": [-71.28, -33.02, 220000]},
    "metropolitana": {"label": "Metropolitana", "bbox": [-71.85, -34.35, -69.65, -32.85], "camera": [-70.65, -33.45, 235000]},
    "ohiggins": {"label": "O'Higgins", "bbox": [-72.2, -35.05, -70.1, -33.7], "camera": [-70.76, -34.55, 240000]},
    "maule": {"label": "Maule", "bbox": [-72.85, -36.25, -70.25, -34.65], "camera": [-71.66, -35.43, 270000]},
    "nuble": {"label": "Ñuble", "bbox": [-73.15, -37.22, -70.8, -35.82], "camera": [-72.1, -36.61, 255000]},
    "biobio": {"label": "Biobío", "bbox": [-73.9, -38.55, -71.0, -36.65], "camera": [-72.7, -37.55, 325000]},
    "araucania": {"label": "La Araucanía", "bbox": [-73.65, -39.7, -71.0, -37.52], "camera": [-72.48, -38.74, 325000]},
    "rios": {"label": "Los Ríos", "bbox": [-73.72, -40.75, -71.55, -39.15], "camera": [-72.66, -39.84, 260000]},
    "lagos": {"label": "Los Lagos", "bbox": [-74.95, -44.1, -71.6, -40.1], "camera": [-72.95, -41.75, 450000]},
    "aysen": {"label": "Aysén", "bbox": [-75.8, -49.2, -71.0, -43.75], "camera": [-72.75, -45.55, 630000]},
    "magallanes": {"label": "Magallanes", "bbox": [-75.8, -56.1, -66.0, -48.6], "camera": [-71.4, -52.2, 820000]},
    "rapanui": {"label": "Rapa Nui", "bbox": [-109.55, -27.3, -109.13, -26.98], "camera": [-109.35, -27.13, 125000]},
}

FIRMS_BASE = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"


class UpstreamError(Exception):
    pass


def csv_hotspots(body: str, source: str, bbox: list[float]) -> list[dict[str, Any]]:
    """Convertir un CSV de FIRMS a una estructura normalizada, descartando errores."""
    if body.lstrip().startswith(("<", "Error", "Invalid", "Wrong")):
        raise UpstreamError("FIRMS devolvió una respuesta no CSV; revisa la clave y los límites.")
    rows = csv.DictReader(StringIO(body))
    if not rows.fieldnames or not {"latitude", "longitude", "acq_date"}.issubset(rows.fieldnames):
        raise UpstreamError("La respuesta FIRMS no contiene las columnas esperadas.")
    result: list[dict[str, Any]] = []
    west, south, east, north = bbox
    for row in rows:
        try:
            lat = float(row["latitude"])
            lon = float(row["longitude"])
            if not (west <= lon <= east and south <= lat <= north):
                continue
            acquisition_date = date.fromisoformat(row["acq_date"])
            hhmm = str(row.get("acq_time") or "0000").strip().zfill(4)
            if not (len(hhmm) == 4 and hhmm.isdigit()):
                continue
            hour, minute = int(hhmm[:2]), int(hhmm[2:])
            if hour > 23 or minute > 59:
                continue
            at = datetime(acquisition_date.year, acquisition_date.month, acquisition_date.day, hour, minute, tzinfo=timezone.utc)
            raw_frp = row.get("frp")
            frp = float(raw_frp) if raw_frp not in (None, "", "null") else None
            raw_brightness = row.get("bright_ti4") or row.get("brightness")
            brightness = float(raw_brightness) if raw_brightness else None
            result.append({
                "id": f"{source}:{acquisition_date}:{hhmm}:{lat:.5f}:{lon:.5f}",
                "lat": lat, "lon": lon, "observed_at": at.isoformat().replace("+00:00", "Z"),
                "date": acquisition_date.isoformat(), "frp_mw": frp,
                "brightness_k": brightness, "confidence": row.get("confidence") or None,
                "source": source,
            })
        except (ValueError, TypeError, KeyError, OverflowError):
            continue
    return result


async def request_firms(client: httpx.AsyncClient, key: str, source: str, bbox: list[float], days: int, start: date | None) -> list[dict[str, Any]]:
    encoded_bbox = ",".join(str(x) for x in bbox)
    url = f"{FIRMS_BASE}/{key}/{source}/{encoded_bbox}/{days}"
    if start:
        url += f"/{start.isoformat()}"
    try:
        response = await client.get(url)
        response.raise_for_status()
    except (httpx.RequestError, httpx.HTTPStatusError) as exc:
        raise UpstreamError(f"No fue posible consultar FIRMS ({type(exc).__name__}).") from exc
    return csv_hotspots(response.text, source, bbox)


async def fetch_hotspots(key: str, region: str, mode: str, days: int, start: date | None) -> tuple[list[dict[str, Any]], list[str]]:
    bbox = REGIONS[region]["bbox"]
    # En reciente, NOAA-20 + NOAA-21. MODIS_SP permite consultar series mas antiguas.
    sources = ("VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT") if mode == "recent" else ("MODIS_SP",)
    async with httpx.AsyncClient(timeout=35.0, follow_redirects=False) as client:
        outcomes = await asyncio.gather(*(
            request_firms(client, key, source, bbox, days, start) for source in sources
        ), return_exceptions=True)
    points: list[dict[str, Any]] = []
    notices: list[str] = []
    for source, outcome in zip(sources, outcomes):
        if isinstance(outcome, BaseException):
            notices.append(f"No se pudo consultar {source}: {str(outcome)}")
        else:
            points.extend(outcome)
    if not points and len(notices) == len(sources):
        raise UpstreamError(" | ".join(notices))
    # Deduplicacion exacta por producto de deteccion, NO fusionar observaciones distintas.
    unique = {p["id"]: p for p in points}
    return sorted(unique.values(), key=lambda point: point["observed_at"]), notices

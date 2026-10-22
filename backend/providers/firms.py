"""NASA FIRMS: detecciones térmicas VIIRS y MODIS (API de áreas, CSV).

BRASA no infiere incendios confirmados ni perímetros desde estos focos.
La clave MAP_KEY va en la URL de FIRMS: nunca se registra, ni se devuelve en errores.

El área pedida a FIRMS es un rectángulo que incluye Argentina, Bolivia y Perú:
el recorte fino es territorial (comunas de Chile con tolerancia costera), no por bbox.
"""
from __future__ import annotations

import asyncio
import csv
from datetime import date, datetime, timedelta, timezone
from io import StringIO
from typing import Any

import httpx

from backend.geo import territory
from backend.providers import _retry

FIRMS_BASE = "https://firms.modaps.eosdis.nasa.gov/api"
MAX_DAYS_PER_REQUEST = 5

# El polígono comunal generaliza la costa: un píxel puede quedar fuera por poco.
# 0.03° ≈ 3,3 km en latitud (algo menos en longitud hacia el sur): cubre el error de
# un píxel de ~2 km y la costa simplificada sin admitir focos de Argentina, Bolivia o Perú.
# Medición de 60 días (2026-10-20): 46 detecciones en la franja 0,03–0,16°, 45 al este
# de la frontera y ninguna en la costa.
TERRITORY_TOLERANCE_DEG = 0.03

# Margen costero histórico (0,16° ≈ 18 km). Se conserva para los incendios oficiales de
# CONAF (OPS-45), que traen su propia coordenada y no deben perderse por la costa
# simplificada; el filtro de FIRMS usa `TERRITORY_TOLERANCE_DEG`.
COASTAL_TOLERANCE_DEG = 0.16

PRODUCTS: dict[str, dict[str, Any]] = {
    "VIIRS_NOAA20_NRT": {"sensor": "VIIRS", "satellite": "NOAA-20", "resolution_m": 375, "kind": "nrt"},
    "VIIRS_NOAA21_NRT": {"sensor": "VIIRS", "satellite": "NOAA-21", "resolution_m": 375, "kind": "nrt"},
    "VIIRS_SNPP_NRT": {"sensor": "VIIRS", "satellite": "Suomi NPP", "resolution_m": 375, "kind": "nrt"},
    "MODIS_NRT": {"sensor": "MODIS", "satellite": "Terra/Aqua", "resolution_m": 1000, "kind": "nrt"},
    "VIIRS_NOAA20_SP": {"sensor": "VIIRS", "satellite": "NOAA-20", "resolution_m": 375, "kind": "sp", "min_date": "2018-04-01"},
    # Suomi NPP deja de entregar VIIRS el 2026-11-02 (NOAA, INV-14).
    "VIIRS_SNPP_SP": {"sensor": "VIIRS", "satellite": "Suomi NPP", "resolution_m": 375, "kind": "sp",
                      "min_date": "2012-01-20", "max_date": "2026-11-02"},
    # max_date provisorio (retiro de Terra ~feb-2027): se ajusta cuando NASA fije la fecha.
    "MODIS_SP": {"sensor": "MODIS", "satellite": "Terra/Aqua", "resolution_m": 1000, "kind": "sp",
                 "min_date": "2000-11-01", "max_date": "2027-09-30"},
}


class UpstreamError(Exception):
    pass


def sources_for(candidates: tuple[str, ...], start: date, end: date) -> tuple[str, ...]:
    """Productos de `candidates` cuyo rango [min_date, max_date] se cruza con la ventana pedida.

    Un producto sin min_date ni max_date (p. ej. los NRT) siempre pasa.
    """
    if start is None or end is None or start > end:
        return ()
    result = []
    for name in candidates:
        info = PRODUCTS.get(name, {})
        if info.get("min_date") and end < date.fromisoformat(info["min_date"]):
            continue
        if info.get("max_date") and start > date.fromisoformat(info["max_date"]):
            continue
        result.append(name)
    return tuple(result)


def normalize_confidence(raw: str | None, sensor: str) -> str | None:
    """VIIRS usa l/n/h; MODIS usa 0-100. Se unifica en baja/nominal/alta."""
    if raw is None or str(raw).strip() == "":
        return None
    value = str(raw).strip().lower()
    if sensor == "VIIRS" or not value.replace(".", "", 1).isdigit():
        return {"l": "baja", "low": "baja", "n": "nominal", "nominal": "nominal", "h": "alta", "high": "alta"}.get(value)
    number = float(value)
    return "baja" if number < 30 else "nominal" if number < 80 else "alta"


def csv_hotspots(body: str, source: str, bbox: list[float]) -> list[dict[str, Any]]:
    """Convertir un CSV de FIRMS a una estructura normalizada, descartando filas inválidas."""
    if body.lstrip().startswith(("<", "Error", "Invalid", "Wrong")):
        raise UpstreamError("FIRMS devolvió una respuesta no CSV; revisa la clave y los límites.")
    rows = csv.DictReader(StringIO(body))
    if not rows.fieldnames or not {"latitude", "longitude", "acq_date"}.issubset(rows.fieldnames):
        raise UpstreamError("La respuesta FIRMS no contiene las columnas esperadas.")
    info = PRODUCTS.get(source, {"sensor": source.split("_")[0], "satellite": None, "resolution_m": None})
    result: list[dict[str, Any]] = []
    west, south, east, north = bbox
    terr = territory()  # memoizado: se construye una vez por proceso, no por fila
    for row in rows:
        try:
            lat = float(row["latitude"])
            lon = float(row["longitude"])
            if not (west <= lon <= east and south <= lat <= north):
                continue
            if terr.locate(lat, lon, tolerance_deg=TERRITORY_TOLERANCE_DEG) is None:
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
            raw_confidence = row.get("confidence") or None
            result.append({
                "id": f"{source}:{acquisition_date}:{hhmm}:{lat:.5f}:{lon:.5f}",
                "lat": lat, "lon": lon, "observed_at": at.isoformat().replace("+00:00", "Z"),
                "date": acquisition_date.isoformat(), "frp_mw": frp,
                "brightness_k": brightness,
                "confidence": normalize_confidence(raw_confidence, info["sensor"]),
                "confidence_raw": raw_confidence,
                "source": source, "sensor": info["sensor"], "satellite": info["satellite"],
                "resolution_m": info["resolution_m"],
                "daynight": row.get("daynight") or None,
            })
        except (ValueError, TypeError, KeyError, OverflowError):
            continue
    return result


async def request_firms(client: httpx.AsyncClient, key: str, source: str, bbox: list[float], days: int, start: date | None) -> list[dict[str, Any]]:
    encoded_bbox = ",".join(str(x) for x in bbox)
    url = f"{FIRMS_BASE}/area/csv/{key}/{source}/{encoded_bbox}/{days}"
    if start:
        url += f"/{start.isoformat()}"
    try:
        response = await _retry.get(client, url)
    except _retry.Failure as exc:
        # Solo el tipo de error: la URL contiene la clave.
        name = "RequestError" if isinstance(exc.cause, httpx.RequestError) else type(exc.cause).__name__
        raise UpstreamError(f"No fue posible consultar FIRMS ({name}).") from None
    return csv_hotspots(response.text, source, bbox)


async def data_availability(client: httpx.AsyncClient, key: str) -> dict[str, tuple[str, str]]:
    """Fechas mínima y máxima disponibles por producto, según FIRMS."""
    try:
        response = await client.get(f"{FIRMS_BASE}/data_availability/csv/{key}/all")
        response.raise_for_status()
    except (httpx.RequestError, httpx.HTTPStatusError):
        raise UpstreamError("No fue posible consultar la disponibilidad de FIRMS.") from None
    result = {}
    for row in csv.DictReader(StringIO(response.text)):
        product = (row.get("data_id") or "").strip()
        if product:
            result[product] = ((row.get("min_date") or "").strip(), (row.get("max_date") or "").strip())
    return result


MAPKEY_STATUS_URL = "https://firms.modaps.eosdis.nasa.gov/mapserver/mapkey_status/"


async def key_status(key: str, client: httpx.AsyncClient | None = None) -> dict[str, int]:
    """Transacciones de la clave en la ventana vigente de 10 min: {"limit", "used"}.

    Permite ver venir el 429. La clave viaja en la URL: nunca aparece en el error.
    """
    own_client = client is None
    client = client or httpx.AsyncClient(timeout=40.0, follow_redirects=False)
    try:
        try:
            response = await client.get(MAPKEY_STATUS_URL, params={"MAP_KEY": key})
            response.raise_for_status()
            data = response.json()
            return {"limit": int(data["transaction_limit"]), "used": int(data["current_transactions"])}
        except (httpx.RequestError, httpx.HTTPStatusError, ValueError, KeyError, TypeError):
            raise UpstreamError("No fue posible consultar el estado de la clave de FIRMS.") from None
    finally:
        if own_client:
            await client.aclose()


def split_window(start: date, end: date) -> list[tuple[date, int]]:
    """Divide [start, end] (inclusive) en tramos de hasta 5 días, el máximo de la API de áreas."""
    chunks = []
    cursor = start
    while cursor <= end:
        days = min(MAX_DAYS_PER_REQUEST, (end - cursor).days + 1)
        chunks.append((cursor, days))
        cursor += timedelta(days=days)
    return chunks


async def fetch_hotspots(key: str, bbox: list[float], sources: tuple[str, ...] | list[str], days: int = 1,
                         start: date | None = None, end: date | None = None,
                         client: httpx.AsyncClient | None = None) -> tuple[list[dict[str, Any]], list[str]]:
    """Consulta varias fuentes en paralelo. Sin `start`: últimos `days` días (NRT).

    Con `start` y `end`: ventana histórica arbitraria, en tramos de 5 días.
    Devuelve (puntos únicos ordenados por hora, avisos de fallas parciales).
    """
    if start and end:
        windows = split_window(start, end)
    else:
        windows = [(start, days)]
    jobs = [(source, s, d) for source in sources for s, d in windows]
    own_client = client is None
    client = client or httpx.AsyncClient(timeout=40.0, follow_redirects=False)
    try:
        outcomes = await asyncio.gather(*(request_firms(client, key, source, bbox, d, s) for source, s, d in jobs),
                                        return_exceptions=True)
    finally:
        if own_client:
            await client.aclose()
    points: list[dict[str, Any]] = []
    notices: list[str] = []
    failed_sources: set[str] = set()
    for (source, _s, _d), outcome in zip(jobs, outcomes):
        if isinstance(outcome, BaseException):
            failed_sources.add(source)
            message = f"No se pudo consultar {source}: {outcome}"
            if message not in notices:
                notices.append(message)
        else:
            points.extend(outcome)
    if not points and len(failed_sources) == len(set(sources)):
        raise UpstreamError(" | ".join(notices))
    # Deduplicación exacta por producto de detección; no se fusionan observaciones distintas.
    unique = {p["id"]: p for p in points}
    return sorted(unique.values(), key=lambda point: point["observed_at"]), notices

"""Emergencias viales de la Dirección de Vialidad (MOP): cortes y restricciones cerca de un incendio.

El servicio ArcGIS `Emergencias_Vialidad` publica la capa 0 con las emergencias vigentes como
puntos (las lineales van referenciales a punto) y sus atributos: camino, tramo en km, tránsito,
restricción, resumen, gravedad y fechas. La capa se actualiza alrededor de las 15 h —todos los
días en periodos de emergencia—, no es tiempo real y no calcula desvíos.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import httpx

from backend.geo import haversine_km
from backend.providers import _retry

BASE_URL = "https://rest-sit.mop.gob.cl/arcgis/rest/services/VIALIDAD/Emergencias_Vialidad/MapServer"
QUERY_URL = f"{BASE_URL}/0/query"
SOURCE = "Dirección de Vialidad (MOP) · Emergencias Vialidad"
SOURCE_URL = BASE_URL
FIELDS = (
    "OBJECTID,GlobalID,CORRELATIVO,NOMBRE_CAMINO,ROL,KM_INICIO_SEGMENTO,KM_FIN_SEGMENTO,"
    "RESUMEN_EMERGENCIA,DESCRIPCION_DETALLADA,TRANSITO,RESTRICCION,OPERATIVIDAD,"
    "NIVEL_DE_GRAVEDAD,REGION,FECHA_EMERGENCIA,FECHA_INGRESO,TIPO"
)
DEFAULT_RADIUS_KM = 30.0
DEFAULT_LIMIT = 8


class VialidadError(Exception):
    pass


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _iso_ms(value: Any) -> str | None:
    """Epoch milisegundos de ArcGIS → ISO UTC; ilegible → None."""
    if value is None or value == "":
        return None
    try:
        ms = int(float(value))
    except (TypeError, ValueError):
        return None
    if ms <= 0:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _detalle(value: Any) -> str | None:
    text = _text(value)
    if not text or text == "%":
        return None
    return text[:300]


def affects_transit(item: dict[str, Any]) -> bool:
    """Solo interesan las emergencias que afectan la circulación, no las observaciones."""
    if item.get("transito") in {"No Operativo", "Parcialmente Operativo"}:
        return True
    if item.get("operatividad") in {"No Operativo", "Parcialmente Operativo"}:
        return True
    return bool(item.get("restriccion"))


def _dedup_key(item: dict[str, Any]) -> tuple[Any, ...]:
    # La capa repite la misma emergencia con GlobalID distinto: mismo camino, km y punto.
    return (
        item.get("road") or "",
        item.get("rol") or "",
        item.get("km_inicio"),
        round(item["lat"], 3),
        round(item["lon"], 3),
    )


def _dedup(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best: dict[tuple[Any, ...], dict[str, Any]] = {}
    order: list[tuple[Any, ...]] = []
    for item in items:
        key = _dedup_key(item)
        prev = best.get(key)
        if prev is None:
            best[key] = item
            order.append(key)
            continue
        prev_at = prev.get("fecha_ingreso") or prev.get("fecha_emergencia") or ""
        item_at = item.get("fecha_ingreso") or item.get("fecha_emergencia") or ""
        if item_at > prev_at:
            best[key] = {
                **prev,
                "fecha_ingreso": max(prev.get("fecha_ingreso") or "", item.get("fecha_ingreso") or "") or None,
                "fecha_emergencia": max(prev.get("fecha_emergencia") or "", item.get("fecha_emergencia") or "") or None,
            }
    return [best[key] for key in order]


def parse(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Respuesta del MapServer → una fila por emergencia con geometría y fecha legibles."""
    out = []
    for feature in (payload or {}).get("features") or []:
        attrs = feature.get("attributes") or {}
        geom = feature.get("geometry") or {}
        lon, lat = _num(geom.get("x")), _num(geom.get("y"))
        if lon is None or lat is None:
            continue
        out.append(
            {
                "id": str(attrs.get("GlobalID") or attrs.get("OBJECTID") or ""),
                "correlativo": attrs.get("CORRELATIVO"),
                "road": _text(attrs.get("NOMBRE_CAMINO")),
                "rol": _text(attrs.get("ROL")),
                "km_inicio": _num(attrs.get("KM_INICIO_SEGMENTO")),
                "km_fin": _num(attrs.get("KM_FIN_SEGMENTO")),
                "resumen": _text(attrs.get("RESUMEN_EMERGENCIA")),
                "detalle": _detalle(attrs.get("DESCRIPCION_DETALLADA")),
                "transito": _text(attrs.get("TRANSITO")),
                "restriccion": _text(attrs.get("RESTRICCION")),
                "operatividad": _text(attrs.get("OPERATIVIDAD")),
                "gravedad": _text(attrs.get("NIVEL_DE_GRAVEDAD")),
                "region": _text(attrs.get("REGION")),
                "tipo": _text(attrs.get("TIPO")),
                "fecha_emergencia": _iso_ms(attrs.get("FECHA_EMERGENCIA")),
                "fecha_ingreso": _iso_ms(attrs.get("FECHA_INGRESO")),
                "lat": lat,
                "lon": lon,
            }
        )
    return _dedup(out)


def nearby(items: list[dict[str, Any]], lat: float, lon: float,
           radius_km: float = DEFAULT_RADIUS_KM, limit: int = DEFAULT_LIMIT) -> list[dict[str, Any]]:
    """Emergencias que afectan el tránsito dentro del radio, de la más cercana a la más lejana."""
    out = []
    for item in items:
        if not affects_transit(item):
            continue
        d = haversine_km(lat, lon, item["lat"], item["lon"])
        if d <= radius_km:
            out.append({**item, "distance_km": round(d, 1)})
    out.sort(key=lambda item: item["distance_km"])
    return out[:limit]


async def fetch_emergencies(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    """Baja la capa 0 completa de emergencias viales vigentes (una llamada, cacheada por la ruta)."""
    try:
        response = await _retry.get(
            client,
            QUERY_URL,
            params={
                "where": "1=1",
                "outFields": FIELDS,
                "returnGeometry": "true",
                "outSR": "4326",
                "resultRecordCount": "2000",
                "f": "json",
            },
            timeout=httpx.Timeout(30.0),
        )
    except _retry.Failure as exc:
        raise VialidadError(f"El servicio de Vialidad no respondió ({exc.detail}).") from exc.cause
    try:
        payload = response.json()
    except json.JSONDecodeError as exc:
        raise VialidadError("La respuesta de Vialidad no es JSON.") from exc
    if not isinstance(payload, dict):
        raise VialidadError("La respuesta de Vialidad no tiene el formato esperado.")
    if payload.get("error"):
        raise VialidadError(f"Vialidad devolvió un error: {payload['error']}.")
    return parse(payload)

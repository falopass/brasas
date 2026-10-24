"""Estaciones SINCA (Ministerio del Medio Ambiente): el MP2,5 medido más cercano a un punto.

El portal público <https://sinca.mma.gob.cl/> publica `listadomapa2k19`, un JSON sin clave con
las ~119 estaciones de la red (públicas y privadas), su posición y el resumen vigente de cada
parámetro (`tableRow`: valor, ICAP, estado y hora). Una sola descarga cacheada sirve a todos
los lugares, igual que la red EMA de la DMC.

La hora de `tableRow.datetime` es hora de Chile («2026-10-23 22:00»), no UTC: se interpreta
en `America/Santiago`, que resuelve solo el UTC-3/UTC-4 del día. Los valores son **preliminares**
hasta la validación del MMA, como declara el propio portal: por eso `status`/el aviso viajan
con el dato. Si la fuente falla o no hay estación cerca, sale null: jamás un valor inventado
(OFI-10, decisión del dueño de integrar con atribución y enlace).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from backend.geo import haversine_km
from backend.providers import _retry

RED_URL = "https://sinca.mma.gob.cl/index.php/json/listadomapa2k19/"
SOURCE = "SINCA · Ministerio del Medio Ambiente (medición preliminar)"
SOURCE_URL = "https://sinca.mma.gob.cl/"
CHILE_TZ = ZoneInfo("America/Santiago")

MAX_KM = 60.0          # el MP2,5 es regional: una estación a esa distancia ya describe el aire
MAX_AGE_S = 6 * 3600   # el resumen se actualiza cada hora con ~2 h de latencia


class SincaError(Exception):
    pass


def _momento_local(text: Any) -> datetime | None:
    """«2026-10-23 22:00» en hora de Chile → datetime consciente; ilegible → None."""
    if not isinstance(text, str):
        return None
    try:
        return datetime.strptime(text.strip(), "%Y-%m-%d %H:%M").replace(tzinfo=CHILE_TZ)
    except (TypeError, ValueError):
        return None


def latest_network(payload: Any) -> list[dict[str, Any]]:
    """listadomapa2k19 → una fila por estación con su MP2,5 vigente (media móvil 24 h).

    Solo cuentan las estaciones con `realtime` para `code == "PM25"` y `tableRow` con valor:
    una estación sin PM2,5 vigente no describe el humo del lugar. `regionindex`, `calificacion`
    y los demás parámetros (MP10, SO2…) no se usan.
    """
    if not isinstance(payload, list):
        return []
    out = []
    for st in payload:
        if not isinstance(st, dict):
            continue
        lat, lon = st.get("latitud"), st.get("longitud")
        if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
            continue
        fila = None
        for rt in st.get("realtime") or []:
            if isinstance(rt, dict) and rt.get("code") == "PM25":
                tr = rt.get("tableRow") or {}
                if isinstance(tr.get("value"), (int, float)):
                    fila = tr
        if fila is None:
            continue
        at = _momento_local(fila.get("datetime"))
        if at is None:
            continue
        out.append({
            "code": str(st.get("key") or ""),
            "name": (st.get("nombre") or "").strip(),
            "comuna": (st.get("comuna") or "").strip(),
            "lat": lat, "lon": lon,
            "observed_at": at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "pm25": round(float(fila["value"]), 1),
            "icap": fila.get("icap"),
            "status": (fila.get("status") or "").strip(),
        })
    return out


async def fetch_network(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    """Baja el listado completo de estaciones SINCA con su MP2,5 vigente (sin clave)."""
    try:
        r = await _retry.get(client, RED_URL, timeout=httpx.Timeout(30.0))
    except _retry.Failure as exc:
        raise SincaError(f"El portal SINCA no respondió ({exc.detail}).") from exc.cause
    try:
        payload = r.json()
    except json.JSONDecodeError as exc:
        raise SincaError("La respuesta de SINCA no es JSON.") from exc
    if not isinstance(payload, list):
        raise SincaError("La respuesta de SINCA no tiene el formato esperado.")
    return latest_network(payload)


def nearest(stations: list[dict[str, Any]], lat: float, lon: float,
            now: datetime | None = None) -> dict[str, Any] | None:
    """La estación con MP2,5 más cercana con lectura fresca (≤ MAX_AGE_S) y a ≤ MAX_KM, o None."""
    now = now or datetime.now(timezone.utc)
    best = None
    for st in stations:
        try:
            at = datetime.fromisoformat(str(st.get("observed_at") or "").replace("Z", "+00:00"))
        except ValueError:
            continue
        if (now - at).total_seconds() > MAX_AGE_S:
            continue
        d = haversine_km(lat, lon, st["lat"], st["lon"])
        if d <= MAX_KM and (best is None or d < best[0]):
            best = (d, st)
    if best is None:
        return None
    d, st = best
    return {"name": st["name"], "code": st["code"], "comuna": st["comuna"],
            "distance_km": round(d, 1), "lat": st["lat"], "lon": st["lon"],
            "observed_at": st["observed_at"], "pm25": st["pm25"],
            "icap": st["icap"], "status": st["status"]}

"""Estaciones automáticas de la DMC (MeteoChile): la más cercana a un punto, medida de verdad.

El portal de servicios climáticos de la DMC exige credenciales personales (correo + apiKey,
`DMC_USUARIO`/`DMC_TOKEN` en settings). `getDatosRecientesRedEma` devuelve en una sola llamada
la red completa con la última lectura de cada estación — sirve de catálogo (lat/lon, nombre)
y de observación a la vez, así que una descarga cacheada basta para todos los lugares.

Los valores llegan como texto con unidad («11.9 °C», «6.4 kt») o null. El viento se publica
en nudos: aquí se guarda ya convertido a km/h. «momento» viene en UTC según la propia
cabecera del servicio. Si la fuente falla o no hay estación cerca, sale null: jamás una
lectura inventada (OFI-33).
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any

import httpx

from backend.geo import haversine_km
from backend.providers import _retry

RED_URL = "https://climatologia.meteochile.gob.cl/application/servicios/getDatosRecientesRedEma"
SOURCE = "Dirección Meteorológica de Chile (DMC) · estación automática"
SOURCE_URL = "https://climatologia.meteochile.gob.cl/"
NUM = re.compile(r"-?\d+(?:[.,]\d+)?")
KT_TO_KMH = 1.852
MAX_KM = 25.0        # la observación solo describe el lugar si la estación está cerca
MAX_AGE_S = 3 * 3600  # una lectura más vieja ya no es «medido ahora»


class DmcStationsError(Exception):
    pass


def _num(text: Any) -> float | None:
    """«11.9 °C» → 11.9; None o sin número → None."""
    if not isinstance(text, str):
        return None
    m = NUM.search(text)
    return float(m.group(0).replace(",", ".")) if m else None


def _kmh(kt_text: Any) -> float | None:
    kt = _num(kt_text)
    return round(kt * KT_TO_KMH, 1) if kt is not None else None


def latest_network(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Red completa → una fila por estación con su última lectura parseada.

    `datos` viene del más reciente al más antiguo; se toma `datos[0]`. Una estación sin
    lectura o sin coordenadas legibles se omite: no puede describir a nadie.
    """
    out = []
    for item in (payload or {}).get("datosEstaciones") or []:
        est, datos = (item or {}).get("estacion") or {}, (item or {}).get("datos") or []
        if not isinstance(datos, list) or not datos:
            continue
        lat, lon = _num(str(est.get("latitud") or "")), _num(str(est.get("longitud") or ""))
        if lat is None or lon is None:
            continue
        u = datos[0]
        out.append({
            "code": str(est.get("codigoNacional") or ""),
            "name": (est.get("nombreEstacion") or "").strip(),
            "lat": lat, "lon": lon, "alt_m": est.get("altura"),
            "observed_at": u.get("momento"),  # UTC, se normaliza abajo
            "temp_c": _num(u.get("temperatura")),
            "humidity": _num(u.get("humedadRelativa")),
            "wind_kmh": _kmh(u.get("fuerzaDelVientoPromedio10Minutos") or u.get("fuerzaDelViento")),
            "wind_deg": _num(u.get("direccionDelVientoPromedio10Minutos") or u.get("direccionDelViento")),
        })
    return out


async def fetch_network(client: httpx.AsyncClient, usuario: str, token: str) -> list[dict[str, Any]]:
    """Baja la red EMA completa con la última lectura por estación (credenciales en params)."""
    try:
        r = await _retry.get(client, RED_URL, params={"usuario": usuario, "token": token},
                             timeout=httpx.Timeout(20.0))
    except _retry.Failure as exc:
        raise DmcStationsError(f"El portal de la DMC no respondió ({exc.detail}).") from exc.cause
    try:
        payload = r.json()
    except json.JSONDecodeError as exc:
        raise DmcStationsError("La respuesta de la DMC no es JSON.") from exc
    if not isinstance(payload, dict):
        raise DmcStationsError("La respuesta de la DMC no tiene el formato esperado.")
    if "mensaje" in payload and "datosEstaciones" not in payload:
        raise DmcStationsError(f"La DMC bloqueó la consulta: {payload['mensaje']}.")
    return latest_network(payload)


def _momento(text: str | None) -> datetime | None:
    """«2026-10-24 03:10:00» UTC → datetime consciente; ilegible → None."""
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def nearest(stations: list[dict[str, Any]], lat: float, lon: float,
            now: datetime | None = None) -> dict[str, Any] | None:
    """La estación más cercana con lectura fresca (≤ MAX_AGE_S) y a ≤ MAX_KM, o None."""
    now = now or datetime.now(timezone.utc)
    best = None
    for st in stations:
        at = _momento(st.get("observed_at"))
        if at is None or (now - at).total_seconds() > MAX_AGE_S:
            continue
        d = haversine_km(lat, lon, st["lat"], st["lon"])
        if d <= MAX_KM and (best is None or d < best[0]):
            best = (d, st, at)
    if best is None:
        return None
    d, st, at = best
    return {"name": st["name"], "code": st["code"], "distance_km": round(d, 1),
            "alt_m": st["alt_m"], "lat": st["lat"], "lon": st["lon"],
            "observed_at": at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "temperature_c": st["temp_c"], "humidity": st["humidity"],
            "wind_kmh": st["wind_kmh"], "wind_deg": st["wind_deg"]}

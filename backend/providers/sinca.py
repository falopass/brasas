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

Si `SINCA_PROXY_URL` está definida, se intenta antes que la URL directa. Si la
petición en vivo falla, se usa el snapshot de `SINCA_SNAPSHOT_PATH` solo cuando
su `fetched_at` tiene como máximo 12 h (`source_mode` «snapshot», con esa hora
real). Un respaldo más viejo o ausente no se presenta como dato reciente.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from backend.geo import haversine_km
from backend.providers import _retry

ROOT = Path(__file__).resolve().parents[2]
RED_URL = "https://sinca.mma.gob.cl/index.php/json/listadomapa2k19/"
SOURCE = "SINCA · Ministerio del Medio Ambiente (medición preliminar)"
SOURCE_URL = "https://sinca.mma.gob.cl/"
CHILE_TZ = ZoneInfo("America/Santiago")

DEFAULT_SNAPSHOT_PATH = ROOT / "backend" / "data" / "sinca_snapshot.json"
MAX_SNAPSHOT_AGE_HOURS = 12.0

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


def _momento_utc(text: Any) -> datetime | None:
    """Marca ISO UTC («2026-10-24T01:00:00Z») → datetime en UTC; ilegible → None."""
    if not isinstance(text, str) or not text.strip():
        return None
    try:
        dt = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _num(v: Any) -> float | None:
    """Número o texto numérico → float; el portal a veces serializa como string."""
    try:
        return float(v)
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
        lat, lon = _num(st.get("latitud")), _num(st.get("longitud"))
        if lat is None or lon is None:
            continue
        fila = None
        for rt in st.get("realtime") or []:
            if isinstance(rt, dict) and rt.get("code") == "PM25":
                tr = rt.get("tableRow") or {}
                if _num(tr.get("value")) is not None:
                    fila = tr
        if fila is None:
            continue
        at = _momento_local(fila.get("datetime"))
        if at is None:
            continue
        val = round(_num(fila["value"]), 1)
        region = (st.get("region") or st.get("region_name") or "").strip()
        row: dict[str, Any] = {
            "code": str(st.get("key") or ""),
            "name": (st.get("nombre") or "").strip(),
            "comuna": (st.get("comuna") or "").strip(),
            "lat": lat, "lon": lon,
            "observed_at": at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "pm25": val,
            "mp25": val,
            "icap": fila.get("icap"),
            "status": (fila.get("status") or "").strip(),
        }
        if region:
            row["region"] = region
        out.append(row)
    return out


# El JSON lo carga el propio mapa público del portal; desde datacenters el WAF del MMA
# rechaza agentes que no son navegador — el encabezado emula al visitante del sitio.
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://sinca.mma.gob.cl/"}


def _candidate_urls(proxy_url: str | None = None) -> list[str]:
    """URLs a intentar en orden: primero SINCA_PROXY_URL (si está definida) y luego RED_URL."""
    raw = proxy_url if proxy_url is not None else os.getenv("SINCA_PROXY_URL", "")
    clean = raw.strip()
    if clean and clean != RED_URL:
        return [clean, RED_URL]
    return [RED_URL]


def _resolve_snapshot_path(snapshot_path: str | Path | None = None) -> Path:
    if snapshot_path is not None:
        return Path(snapshot_path)
    env_path = os.getenv("SINCA_SNAPSHOT_PATH", "").strip()
    if env_path:
        return Path(env_path)
    alt_web = ROOT / "web" / "data" / "sinca-snapshot.json"
    if alt_web.is_file() and not DEFAULT_SNAPSHOT_PATH.is_file():
        return alt_web
    return DEFAULT_SNAPSHOT_PATH


def _normalizar_estacion_snapshot(st: Any, default_observed_at: str | None) -> dict[str, Any] | None:
    if not isinstance(st, dict):
        return None
    lat = _num(st.get("lat") if "lat" in st else st.get("latitud"))
    lon = _num(st.get("lon") if "lon" in st else st.get("longitud"))
    val = _num(st.get("pm25") if st.get("pm25") is not None else st.get("mp25"))
    if lat is None or lon is None or val is None:
        return None
    obs = str(st.get("observed_at") or default_observed_at or "").strip()
    if not obs:
        return None
    rounded = round(val, 1)
    row: dict[str, Any] = {
        "code": str(st.get("code") or st.get("key") or ""),
        "name": (st.get("name") or st.get("nombre") or "").strip(),
        "comuna": (st.get("comuna") or "").strip(),
        "lat": lat,
        "lon": lon,
        "observed_at": obs,
        "pm25": rounded,
        "mp25": rounded,
        "icap": st.get("icap"),
        "status": (st.get("status") or "").strip(),
    }
    if st.get("region"):
        row["region"] = str(st["region"]).strip()
    return row


def load_snapshot(
    snapshot_path: str | Path | None = None,
    *,
    max_snapshot_age_hours: float | None = None,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """Lee el snapshot precalculado si existe y su `fetched_at` no supera `max_snapshot_age_hours`."""
    path = _resolve_snapshot_path(snapshot_path)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    fetched_raw = data.get("fetched_at")
    fetched_dt = _momento_utc(fetched_raw)
    if fetched_dt is None:
        return None
    now_utc = now or datetime.now(timezone.utc)
    max_hours = max_snapshot_age_hours
    if max_hours is None:
        env_hours = _num(os.getenv("SINCA_MAX_SNAPSHOT_AGE_HOURS"))
        max_hours = env_hours if env_hours is not None and env_hours > 0 else MAX_SNAPSHOT_AGE_HOURS
    age_seconds = (now_utc - fetched_dt).total_seconds()
    if age_seconds < -900 or age_seconds > max_hours * 3600:
        return None
    raw_stations = data.get("stations")
    if not isinstance(raw_stations, list):
        return None
    fetched_iso = fetched_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    if raw_stations and isinstance(raw_stations[0], dict) and "realtime" in raw_stations[0]:
        stations = latest_network(raw_stations)
    else:
        stations = [
            norm for item in raw_stations
            if (norm := _normalizar_estacion_snapshot(item, fetched_iso)) is not None
        ]
    return {
        "stations": stations,
        "source_mode": "snapshot",
        "fetched_at": fetched_iso,
        "status": "ok" if stations else "unavailable",
    }


async def _fetch_from_url(client: httpx.AsyncClient, url: str) -> list[dict[str, Any]]:
    try:
        r = await _retry.get(client, url, headers=_HEADERS, timeout=httpx.Timeout(30.0))
    except _retry.Failure as exc:
        raise SincaError(f"El portal SINCA no respondió ({exc.detail}).") from exc.cause
    try:
        payload = r.json()
    except json.JSONDecodeError as exc:
        raise SincaError("La respuesta de SINCA no es JSON.") from exc
    if not isinstance(payload, list):
        raise SincaError("La respuesta de SINCA no tiene el formato esperado.")
    return latest_network(payload)


async def fetch_network_with_meta(
    client: httpx.AsyncClient,
    *,
    proxy_url: str | None = None,
    snapshot_path: str | Path | None = None,
    max_snapshot_age_hours: float | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Obtiene la red SINCA vía proxy opcional o URL directa, con respaldo en snapshot vigente."""
    now_utc = now or datetime.now(timezone.utc)
    last_err: SincaError | None = None
    for url in _candidate_urls(proxy_url):
        try:
            stations = await _fetch_from_url(client, url)
            return {
                "stations": stations,
                "source_mode": "live",
                "fetched_at": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "status": "ok",
            }
        except SincaError as exc:
            last_err = exc
    snap = load_snapshot(
        snapshot_path,
        max_snapshot_age_hours=max_snapshot_age_hours,
        now=now_utc,
    )
    if snap is not None:
        return snap
    assert last_err is not None
    raise last_err


async def fetch_network(
    client: httpx.AsyncClient,
    *,
    proxy_url: str | None = None,
    snapshot_path: str | Path | None = None,
    max_snapshot_age_hours: float | None = None,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Baja el listado completo de estaciones SINCA con su MP2,5 vigente (sin clave)."""
    meta = await fetch_network_with_meta(
        client,
        proxy_url=proxy_url,
        snapshot_path=snapshot_path,
        max_snapshot_age_hours=max_snapshot_age_hours,
        now=now,
    )
    return meta["stations"]


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
        edad = (now - at).total_seconds()
        if edad < -900 or edad > MAX_AGE_S:      # hora futura (reloj malo) o muy vieja
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

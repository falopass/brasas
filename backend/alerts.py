"""Alertas por lugar: detecciones nuevas cerca de los lugares que cada persona guardó.

Niveles:
- "aviso": detección confiable dentro del radio elegido.
- "urgente": además el viento sopla desde el foco hacia el lugar, o el foco está muy cerca
  (≤ 2 km), o está a ≤ 5 km en un día de riesgo alto/extremo.

Las alertas de BRASA no son alertas oficiales: siempre remiten a SENAPRED y a los números de emergencia.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable
from zoneinfo import ZoneInfo

from backend.db import Database
from backend.geo import bearing_deg, cardinal, haversine_km, is_upwind

CHILE_TZ = ZoneInfo("America/Santiago")
ALERTABLE_CONFIDENCE = {"alta", "nominal", "media"}
DEDUPE_HOURS = 12
DEDUPE_KM = 3.0
OFFICIAL_FOOTER = ("Esto no es una alerta oficial. Sigue las instrucciones de SENAPRED y de la autoridad local. "
                   "Emergencias: 130 CONAF · 132 Bomberos · 131 SAMU · 133 Carabineros.")
LEVEL_RANK = {"aviso": 1, "urgente": 2}

WindLookup = Callable[[float, float], Awaitable[dict[str, Any] | None]]


def is_alertable(obs: dict[str, Any]) -> bool:
    return (obs.get("confidence") or "") in ALERTABLE_CONFIDENCE


def classify(distance_km: float, upwind: bool, risk_level: str | None) -> str:
    if upwind or distance_km <= 2.0 or (distance_km <= 5.0 and risk_level in {"alto", "extremo"}):
        return "urgente"
    return "aviso"


def source_label(obs: dict[str, Any]) -> str:
    satellite = obs.get("satellite") or obs.get("source")
    sensor = obs.get("sensor") or ""
    return f"{sensor} {satellite}".strip()


def compose(place: dict[str, Any], obs: dict[str, Any], distance_km: float, bearing: float, upwind: bool,
            level: str, wind: dict[str, Any] | None, others: int) -> dict[str, Any]:
    observed = datetime.fromisoformat(obs["observed_at"].replace("Z", "+00:00")).astimezone(CHILE_TZ)
    direction = cardinal(bearing)
    title = ("URGENTE · " if level == "urgente" else "") + f"Foco de calor a {distance_km:.1f} km de {place['name']}"
    lines = [f"Detección satelital al {direction} de «{place['name']}», a {distance_km:.1f} km."]
    if upwind and wind:
        lines.append(f"El viento sopla desde esa dirección hacia tu lugar ({wind.get('speed', 0):.0f} km/h): el humo y las pavesas pueden avanzar hacia ti.")
    if others:
        lines.append(f"Hay {others} detección(es) adicional(es) dentro de tu radio.")
    lines.append(f"Fuente: {source_label(obs)} · {observed:%d-%m %H:%M} hora de Chile · confianza {obs.get('confidence') or 'no informada'}.")
    lines.append("Un foco de calor no confirma un incendio. Verifica con fuentes oficiales y prepárate para actuar.")
    return {
        "title": title, "body": " ".join(lines), "footer": OFFICIAL_FOOTER, "level": level,
        "place": {"id": place["id"], "name": place["name"], "lat": place["lat"], "lon": place["lon"]},
        "observation": {k: obs.get(k) for k in ("id", "lat", "lon", "observed_at", "source", "sensor", "satellite",
                                                "confidence", "frp_mw", "resolution_m")},
        "distance_km": round(distance_km, 2), "bearing_deg": round(bearing), "direction": direction,
        "upwind": upwind, "wind": wind, "others": others,
        "url": f"/#/mapa?lat={obs['lat']:.4f}&lon={obs['lon']:.4f}&z=12",
    }


def _recent_alerts(db: Database, place_id: str, now: datetime) -> list[dict[str, Any]]:
    since = (now - timedelta(hours=DEDUPE_HOURS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return db.query("SELECT lat, lon, level FROM alerts WHERE place_id = ? AND created_at >= ?", (place_id, since))


def _risk_today(db: Database, comuna_code: int | None, now: datetime) -> str | None:
    if comuna_code is None:
        return None
    today = now.astimezone(CHILE_TZ).date().isoformat()
    row = db.one("SELECT level FROM risk_daily WHERE comuna_code = ? AND date = ?", (comuna_code, today))
    return row["level"] if row else None


async def evaluate(db: Database, observations: list[dict[str, Any]], wind_lookup: WindLookup | None = None,
                   now: datetime | None = None) -> list[dict[str, Any]]:
    """Crea alertas para las observaciones nuevas. Devuelve las alertas insertadas (con su payload)."""
    now = now or datetime.now(timezone.utc)
    candidates = [o for o in observations if is_alertable(o)]
    if not candidates:
        return []
    created: list[dict[str, Any]] = []
    for place in db.query("SELECT * FROM places"):
        near = []
        for obs in candidates:
            d = haversine_km(place["lat"], place["lon"], obs["lat"], obs["lon"])
            if d <= place["radius_km"]:
                near.append((d, obs))
        if not near:
            continue
        near.sort(key=lambda item: item[0])
        distance, obs = near[0]
        bearing = bearing_deg(place["lat"], place["lon"], obs["lat"], obs["lon"])
        wind = await wind_lookup(place["lat"], place["lon"]) if wind_lookup else None
        upwind = is_upwind(bearing, (wind or {}).get("direction"), (wind or {}).get("speed"))
        level = classify(distance, upwind, _risk_today(db, place.get("comuna_code"), now))
        duplicate = any(
            haversine_km(prev["lat"], prev["lon"], obs["lat"], obs["lon"]) <= DEDUPE_KM
            and LEVEL_RANK[prev["level"]] >= LEVEL_RANK[level]
            for prev in _recent_alerts(db, place["id"], now)
        )
        if duplicate:
            continue
        payload = compose(place, obs, distance, bearing, upwind, level, wind, len(near) - 1)
        stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        alert_id = db.insert(
            "INSERT OR IGNORE INTO alerts(place_id, observation_id, level, distance_km, bearing_deg, upwind, lat, lon, "
            "observed_at, created_at, payload) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (place["id"], obs["id"], level, round(distance, 3), round(bearing, 1), int(upwind), obs["lat"], obs["lon"],
             obs["observed_at"], stamp, json.dumps(payload, ensure_ascii=False)),
        )
        if alert_id:
            created.append({"id": alert_id, "subscriber_id": place["subscriber_id"], "level": level,
                            "created_at": stamp, "payload": payload})
    return created

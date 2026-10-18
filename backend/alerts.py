"""Alertas por lugar: detecciones nuevas cerca de los lugares que cada persona guardó.

Niveles:
- "aviso": detección confiable dentro del radio elegido.
- "urgente": además el viento sopla desde el foco hacia el lugar, o el foco está muy cerca
  (≤ 2 km), o está a ≤ 5 km en un día de riesgo alto/extremo, o en el lugar vive una persona mayor
  o alguien que necesita ayuda para salir (necesita más tiempo: se avisa antes).

Las alertas de BRASA no son alertas oficiales: siempre remiten a SENAPRED y a los números de emergencia.
Cada detección pertenece a un incidente (backend/incidents.py): el aviso cuenta cuánta evidencia lo respalda,
y los incidentes cuya evidencia cae entera en una fuente de calor fija probable (volcán, industria) no avisan.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable
from zoneinfo import ZoneInfo

from backend import incidents as incidents_mod
from backend.db import Database
from backend.geo import bearing_deg, cardinal, haversine_km, is_upwind

CHILE_TZ = ZoneInfo("America/Santiago")
ALERTABLE_CONFIDENCE = {"alta", "nominal", "media"}
DEDUPE_HOURS = 12
DEDUPE_KM = 3.0
# Una detección más vieja que esto no despierta a nadie: el aviso diría «foco cerca» con el viento
# y el riesgo de ahora, cuando el fuego es de ayer. Con FIRMS pidiendo dos días, el primer ciclo
# tras una caída puede traer detecciones viejas: se guardan (sirven para el mapa y el incidente),
# pero no generan alerta. Se alinea con incidents.ACTIVE_HOURS.
MAX_AGE_H = 6
OFFICIAL_FOOTER = ("Esto no es una alerta oficial. Sigue las instrucciones de SENAPRED y de la autoridad local. "
                   "Emergencias: 130 CONAF · 132 Bomberos · 131 SAMU · 133 Carabineros.")
LEVEL_RANK = {"aviso": 1, "urgente": 2}
INCIDENT_PHRASE = {
    "anomalia": "una sola detección por ahora",
    "posible": "posible incendio",
    "reportado": "posible incendio, también reportado por vecinos (verificado)",
    "confirmado": "incendio informado por CONAF",
    "controlado": "incendio controlado según CONAF",
}

WindLookup = Callable[[float, float], Awaitable[dict[str, Any] | None]]


def is_alertable(obs: dict[str, Any]) -> bool:
    return (obs.get("confidence") or "") in ALERTABLE_CONFIDENCE


def is_recent(obs: dict[str, Any], now: datetime) -> bool:
    """¿La detección es lo bastante nueva como para despertar a alguien? (MAX_AGE_H)"""
    try:
        return _parse(obs["observed_at"]) >= now - timedelta(hours=MAX_AGE_H)
    except (KeyError, TypeError, ValueError):
        return False


def classify(distance_km: float, upwind: bool, risk_level: str | None, older_adult: bool = False) -> str:
    if older_adult or upwind or distance_km <= 2.0 or (distance_km <= 5.0 and risk_level in {"alto", "extremo"}):
        return "urgente"
    return "aviso"


def source_label(obs: dict[str, Any]) -> str:
    satellite = obs.get("satellite") or obs.get("source")
    sensor = obs.get("sensor") or ""
    return f"{sensor} {satellite}".strip()


def incident_line(inc: dict[str, Any]) -> str | None:
    """«Posible incendio: 5 detecciones de 2 sensores en 2 h.» Nada si es una detección suelta."""
    if not inc or inc.get("n_obs", 0) < 2:
        return None
    span_h = (_parse(inc["last_seen_at"]) - _parse(inc["first_seen_at"])).total_seconds() / 3600
    span = f"en {span_h:.0f} h" if span_h >= 1 else "en menos de una hora"
    sensors = len([s for s in (inc.get("sensors") or "").split(",") if s and s != "?"])
    by = f" de {sensors} sensores distintos" if sensors >= 2 else ""
    phrase = INCIDENT_PHRASE.get(inc["status"], "grupo de detecciones")
    return f"{phrase[0].upper()}{phrase[1:]}: {inc['n_obs']} detecciones{by} {span}."


def _parse(stamp: str) -> datetime:
    return datetime.fromisoformat(stamp.replace("Z", "+00:00"))


def compose(place: dict[str, Any], obs: dict[str, Any], distance_km: float, bearing: float, upwind: bool,
            level: str, wind: dict[str, Any] | None, others: int, incident: dict[str, Any] | None = None) -> dict[str, Any]:
    observed = datetime.fromisoformat(obs["observed_at"].replace("Z", "+00:00")).astimezone(CHILE_TZ)
    direction = cardinal(bearing)
    title = ("URGENTE · " if level == "urgente" else "") + f"Foco de calor a {distance_km:.1f} km de {place['name']}"
    lines = [f"Detección satelital al {direction} de «{place['name']}», a {distance_km:.1f} km."]
    if upwind and wind:
        lines.append(f"El viento sopla desde esa dirección hacia tu lugar ({wind.get('speed', 0):.0f} km/h): el humo y las pavesas pueden avanzar hacia ti.")
    summary = incident_line(incident) if incident else None
    if summary:
        lines.append(summary)
    if others:
        lines.append(f"Hay {others} detección(es) adicional(es) dentro de tu radio.")
    if place.get("older_adult"):
        lines.append("En este lugar vive una persona mayor o alguien que necesita ayuda para salir: "
                     "confirma con ella ahora y, si hay que salir, salgan temprano, sin esperar a ver el fuego.")
    lines.append(f"Fuente: {source_label(obs)} · {observed:%d-%m %H:%M} hora de Chile · confianza {obs.get('confidence') or 'no informada'}.")
    lines.append("Un foco de calor no confirma un incendio. Verifica con fuentes oficiales y prepárate para actuar.")
    return {
        "title": title, "body": " ".join(lines), "footer": OFFICIAL_FOOTER, "level": level,
        "place": {"id": place["id"], "name": place["name"], "lat": place["lat"], "lon": place["lon"]},
        "observation": {k: obs.get(k) for k in ("id", "lat", "lon", "observed_at", "source", "sensor", "satellite",
                                                "confidence", "frp_mw", "resolution_m")},
        "distance_km": round(distance_km, 2), "bearing_deg": round(bearing), "direction": direction,
        "upwind": upwind, "wind": wind, "others": others,
        "incident": {k: incident.get(k) for k in ("id", "status", "n_obs", "first_seen_at", "sensors")} if incident else None,
        "url": incident_url(incident, obs["lat"], obs["lon"]),
    }


def incident_url(incident: dict[str, Any] | None, lat: float, lon: float) -> str:
    """A la ficha del incidente si se conoce; si no, al mapa centrado en la detección.

    Abrir el mapa en un punto obliga a buscar el incendio entre todos los de la zona; la ficha
    cuenta qué se sabe de ese incidente y en qué estado está (FIX-04).
    """
    incident_id = (incident or {}).get("id")
    if incident_id:
        return f"/#/incendio/{incident_id}"
    return f"/#/mapa?lat={lat:.4f}&lon={lon:.4f}&z=12"


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
    """Crea alertas para las observaciones nuevas y recientes. Devuelve las alertas insertadas.

    Una detección vieja (más de MAX_AGE_H) no genera alerta aunque acabe de entrar: el aviso
    hablaría de un foco de ayer con el viento y el riesgo de ahora.
    """
    now = now or datetime.now(timezone.utc)
    incidents: dict[str, dict[str, Any] | None] = {}
    candidates = []
    for obs in observations:
        if not is_alertable(obs) or not is_recent(obs, now):
            continue
        incidents[obs["id"]] = inc = incidents_mod.incident_of(db, obs["id"])
        if inc and inc.get("fixed_source"):
            continue  # volcán o industria: se ve en el mapa, pero no despierta a nadie
        candidates.append(obs)
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
        recent = _recent_alerts(db, place["id"], now)
        wind = await wind_lookup(place["lat"], place["lon"]) if wind_lookup else None
        # La más cercana puede ser un duplicado o una fila ya escrita (una detección recuperada
        # sin marca tras migrar o tras un corte): saltar el lugar entero dejaría sin aviso al
        # foco nuevo que viene detrás. Se elige la más cercana que todavía pueda avisar.
        for distance, obs in near:
            bearing = bearing_deg(place["lat"], place["lon"], obs["lat"], obs["lon"])
            upwind = is_upwind(bearing, (wind or {}).get("direction"), (wind or {}).get("speed"))
            level = classify(distance, upwind, _risk_today(db, place.get("comuna_code"), now), bool(place.get("older_adult")))
            duplicate = any(
                haversine_km(prev["lat"], prev["lon"], obs["lat"], obs["lon"]) <= DEDUPE_KM
                and LEVEL_RANK[prev["level"]] >= LEVEL_RANK[level]
                for prev in recent
            )
            if duplicate:
                continue
            payload = compose(place, obs, distance, bearing, upwind, level, wind, len(near) - 1, incidents.get(obs["id"]))
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
                break
    return created


OFFICIAL_HOURS = 24          # solo incendios informados que empezaron hace menos de un día
OFFICIAL_URGENT_KM = 5.0


def compose_official(place: dict[str, Any], fire: dict[str, Any], distance_km: float, bearing: float, level: str,
                     incident_id: str | None = None) -> dict[str, Any]:
    started = datetime.fromisoformat(fire["started_at"].replace("Z", "+00:00")).astimezone(CHILE_TZ)
    direction = cardinal(bearing)
    title = ("URGENTE · " if level == "urgente" else "") + f"CONAF informa un incendio a {distance_km:.1f} km de {place['name']}"
    lines = [f"CONAF informa el incendio «{fire['name'] or 'sin nombre'}» al {direction} de «{place['name']}», a {distance_km:.1f} km.",
             f"Estado según CONAF: {fire['status_raw'] or 'informado'} · inicio {started:%d-%m %H:%M} hora de Chile"
             + (f" · {fire['area_ha']:.1f} ha".replace(".", ",") if fire.get("area_ha") else "") + "."]
    if place.get("older_adult"):
        lines.append("En este lugar vive una persona mayor o alguien que necesita ayuda para salir: confirma con ella ahora.")
    lines.append("Sigue las instrucciones de SENAPRED y de la autoridad local. Si te ordenan evacuar, hazlo de inmediato.")
    return {
        "title": title, "body": " ".join(lines), "footer": OFFICIAL_FOOTER, "level": level, "kind": "oficial",
        "place": {"id": place["id"], "name": place["name"], "lat": place["lat"], "lon": place["lon"]},
        "observation": {"id": f"conaf:{fire['id']}", "lat": fire["lat"], "lon": fire["lon"], "observed_at": fire["started_at"],
                        "source": "CONAF", "satellite": "CONAF"},
        "official": {k: fire.get(k) for k in ("id", "name", "status", "status_raw", "started_at", "area_ha", "comuna")},
        "distance_km": round(distance_km, 2), "bearing_deg": round(bearing), "direction": direction,
        "url": incident_url({"id": incident_id} if incident_id else None, fire["lat"], fire["lon"]),
    }


async def evaluate_official(db: Database, fires: list[dict[str, Any]], now: datetime | None = None) -> list[dict[str, Any]]:
    """Avisa a los lugares cercanos cuando CONAF informa un incendio nuevo y aún no extinguido."""
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(hours=OFFICIAL_HOURS)
    fresh = [f for f in fires if f["status"] != "extinguido"
             and datetime.fromisoformat(f["started_at"].replace("Z", "+00:00")) >= since]
    created: list[dict[str, Any]] = []
    if not fresh:
        return created
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    # Varios incidentes pueden compartir el mismo official_ref (rebrotes, fusiones): se queda el más
    # reciente, que es la ficha que sigue viva. Se recorre de viejo a nuevo y el último gana.
    linked: dict[str, str] = {}
    for row in db.query("SELECT id, official_ref FROM incidents WHERE official_ref IS NOT NULL "
                        "ORDER BY last_seen_at ASC"):
        linked[row["official_ref"]] = row["id"]
    for place in db.query("SELECT * FROM places"):
        near = sorted(((haversine_km(place["lat"], place["lon"], f["lat"], f["lon"]), f) for f in fresh), key=lambda x: x[0])
        near = [(d, f) for d, f in near if d <= place["radius_km"]]
        if not near:
            continue
        distance, fire = near[0]
        bearing = bearing_deg(place["lat"], place["lon"], fire["lat"], fire["lon"])
        level = "urgente" if distance <= OFFICIAL_URGENT_KM or place.get("older_adult") else "aviso"
        payload = compose_official(place, fire, distance, bearing, level, incident_id=linked.get(fire["id"]))
        alert_id = db.insert(
            "INSERT OR IGNORE INTO alerts(place_id, observation_id, level, distance_km, bearing_deg, upwind, lat, lon, "
            "observed_at, created_at, payload) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (place["id"], f"conaf:{fire['id']}", level, round(distance, 3), round(bearing, 1), 0, fire["lat"], fire["lon"],
             fire["started_at"], stamp, json.dumps(payload, ensure_ascii=False)))
        if alert_id:
            created.append({"id": alert_id, "subscriber_id": place["subscriber_id"], "level": level, "created_at": stamp, "payload": payload})
    return created

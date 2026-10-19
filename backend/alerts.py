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
from backend import reports as reports_mod
from backend.db import Database
from backend.geo import bearing_deg, cardinal, haversine_km, is_upwind, territory
from backend.providers import dmc

CHILE_TZ = ZoneInfo("America/Santiago")
ALERTABLE_CONFIDENCE = {"alta", "nominal", "media"}
DEDUPE_HOURS = 12
DEDUPE_KM = 3.0
# Una detección más vieja que esto no despierta a nadie: el aviso diría «foco cerca» con el viento
# y el riesgo de ahora, cuando el fuego es de ayer. Con FIRMS pidiendo dos días, el primer ciclo
# tras una caída puede traer detecciones viejas: se guardan (sirven para el mapa y el incidente),
# pero no generan alerta. Se alinea con incidents.ACTIVE_HOURS.
MAX_AGE_H = 6
# ALR-10: un aviso urgente que sigue siendo el último del lugar se reenvía una sola vez
# pasada esta espera; los demás niveles jamás se repiten.
ESCALATE_AFTER_MIN = 10
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


def escalation_due(alert: dict[str, Any], has_newer: bool, now: datetime) -> bool:
    """¿Corresponde reenviar este aviso? (ALR-10)

    En una emergencia un aviso urgente no leído es un aviso perdido: si ya se entregó,
    pasaron ESCALATE_AFTER_MIN minutos desde su creación y sigue siendo el más reciente
    del lugar, se reenvía una sola vez (`reminded_at` lo veda para siempre: nunca más
    de dos envíos por aviso). Los no urgentes jamás se repiten, y si ya salió otro
    aviso más nuevo para el mismo lugar, ese fue el que despertó a la persona:
    repetir el viejo sería ruido.
    """
    if alert.get("level") != "urgente" or not alert.get("delivered_at") or alert.get("reminded_at"):
        return False
    if has_newer:
        return False
    try:
        return _parse(alert["created_at"]) <= now - timedelta(minutes=ESCALATE_AFTER_MIN)
    except (KeyError, TypeError, ValueError):
        return False


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
    # El cierre `conaf:<id>:estado` queda fuera de la deduplicación: su mensaje es «deja de
    # avisar por este incendio», no «no hay fuego» — una reactivación a su lado debe avisar igual.
    # Los avisos `dmc:` también quedan fuera: su lat/lon es el centro de la comuna, no un foco,
    # y si contaran silenciarían detecciones reales dentro de DEDUPE_KM de ese centro.
    return db.query("SELECT lat, lon, level FROM alerts WHERE place_id = ? AND created_at >= ? "
                    "AND observation_id NOT LIKE 'conaf:%:estado' AND observation_id NOT LIKE 'dmc:%'",
                    (place_id, since))


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


REPORT_RADIUS_KM = 5.0   # un reporte vecinal solo avisa en la cercanía inmediata, aunque el radio del lugar sea mayor
REPORT_DEDUPE_MIN = 30   # reportes verificados en esta ventana comparten el mismo aviso por lugar


def compose_report(place: dict[str, Any], report: dict[str, Any], distance_km: float, bearing: float) -> dict[str, Any]:
    """Aviso vecinal: un reporte ciudadano recién verificado cerca del lugar (ALR-03).

    Del vecino no sale nada: ni foto, ni descripción, ni nota del moderador, ni identidad.
    Solo la ubicación ya redondeada (~100 m, como la muestra el mapa público) y el tipo de reporte.
    """
    direction = cardinal(bearing)
    created = _parse(report["created_at"]).astimezone(CHILE_TZ)
    lat, lon = round(report["lat"], 3), round(report["lon"], 3)
    kind_label = reports_mod.KINDS.get(report.get("kind") or "", "un hecho").lower()
    title = f"Un vecino informó {kind_label} a {distance_km:.1f} km de {place['name']}"
    lines = [f"Un vecino informó {kind_label} al {direction} de «{place['name']}», a {distance_km:.1f} km "
             f"({created:%d-%m %H:%M} hora de Chile), revisado por BRASA.",
             "Un reporte vecinal no confirma un incendio. Si ves fuego o humo, llama primero a CONAF (130) "
             "o a Bomberos (132) y sigue las fuentes oficiales."]
    if place.get("older_adult"):
        lines.append("En este lugar vive una persona mayor o alguien que necesita ayuda para salir: confirma con ella ahora.")
    return {
        "title": title, "body": " ".join(lines), "footer": OFFICIAL_FOOTER, "level": "aviso", "kind": "reporte",
        "place": {"id": place["id"], "name": place["name"], "lat": place["lat"], "lon": place["lon"]},
        "observation": {"id": f"report:{report['id']}", "lat": lat, "lon": lon,
                        "observed_at": report["created_at"], "source": "reporte ciudadano"},
        "report": {"id": report["id"], "kind": report.get("kind"), "created_at": report["created_at"]},
        "distance_km": round(distance_km, 2), "bearing_deg": round(bearing), "direction": direction,
        "url": incident_url(None, lat, lon),
    }


def evaluate_report(db: Database, report: dict[str, Any], now: datetime | None = None) -> list[dict[str, Any]]:
    """Avisa a los lugares cercanos cuando un reporte ciudadano pasa a «verificado» (ALR-03).

    Siempre «aviso», nunca «urgente»: la verificación humana no reemplaza la evidencia
    satelital ni a CONAF. El UNIQUE(place_id, observation_id) lo hace idempotente si el
    mismo reporte se modera dos veces, y un lugar que ya recibió un aviso de reporte en los
    últimos REPORT_DEDUPE_MIN minutos no recibe otro: aprobar en lote varios reportes del
    mismo incendio no encola N «un vecino informó» iguales (REV-03). La entrega la hace
    Services.deliver en el ciclo siguiente.
    """
    now = now or datetime.now(timezone.utc)
    if report.get("status") != "verificado":
        return []
    # Cada tipo tiene su propia ventana de vigencia (la misma con que caduca en la cola):
    # un humo se disipa en horas, pero unas llamas o una quema verificadas al día siguiente
    # siguen describiendo un hecho vigente y deben avisar igual.
    hours = reports_mod.EXPIRE_HOURS_BY_KIND.get(report.get("kind") or "", reports_mod.EXPIRE_HOURS)
    try:
        if _parse(report["created_at"]) < now - timedelta(hours=hours):
            return []   # un reporte caducado avisaría «un vecino informó» algo que ya pasó
    except (KeyError, TypeError, ValueError):
        return []
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    lat, lon = round(report["lat"], 3), round(report["lon"], 3)
    # Lugares que ya oyeron «un vecino informó» recién: un segundo aviso en media hora diría
    # lo mismo del mismo hecho. shortcut: sin filtro de distancia — dos fuegos distintos en la
    # misma ventana comparten el silencio; si eso duele, comparar también `alerts.lat/lon`.
    since = (now - timedelta(minutes=REPORT_DEDUPE_MIN)).strftime("%Y-%m-%dT%H:%M:%SZ")
    already = {row["place_id"] for row in db.query(
        "SELECT DISTINCT place_id FROM alerts WHERE observation_id LIKE 'report:%' AND created_at >= ?",
        (since,))}
    created: list[dict[str, Any]] = []
    for place in db.query("SELECT * FROM places"):
        if place["id"] in already:
            continue
        distance = haversine_km(place["lat"], place["lon"], report["lat"], report["lon"])
        if distance > min(place["radius_km"], REPORT_RADIUS_KM):
            continue
        bearing = bearing_deg(place["lat"], place["lon"], report["lat"], report["lon"])
        payload = compose_report(place, report, distance, bearing)
        # `observed_at` guarda el momento del aviso, no el del reporte: es lo que cuenta para
        # la ventana de reintento de entrega (mismo criterio que el cierre CONAF, ALR-02).
        # Sin esto, un reporte verificado cerca de su límite de edad nacería ya «viejo» y
        # quedaría fuera de la recuperación de pendientes sin llegar jamás a entregarse.
        alert_id = db.insert(
            "INSERT OR IGNORE INTO alerts(place_id, observation_id, level, distance_km, bearing_deg, upwind, lat, lon, "
            "observed_at, created_at, payload) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (place["id"], f"report:{report['id']}", "aviso", round(distance, 3), round(bearing, 1), 0,
             lat, lon, stamp, stamp, json.dumps(payload, ensure_ascii=False)))
        if alert_id:
            created.append({"id": alert_id, "subscriber_id": place["subscriber_id"], "level": "aviso",
                            "created_at": stamp, "payload": payload})
    return created


def compose_status_change(place: dict[str, Any], fire: dict[str, Any], distance_km: float, bearing: float,
                          incident_id: str | None = None) -> dict[str, Any]:
    """El aviso de cierre: CONAF dio el incendio por controlado o extinguido (ALR-02)."""
    direction = cardinal(bearing)
    closed = "extinguido" if fire["status"] == "extinguido" else "controlado"
    name = fire["name"] or "sin nombre"
    title = f"Incendio {closed} según CONAF · «{name}» a {distance_km:.1f} km de {place['name']}"
    lines = [f"El incendio «{name}» quedó {closed} según CONAF. BRASA dejará de avisar por este incendio.",
             f"Estaba al {direction} de «{place['name']}», a {distance_km:.1f} km."]
    if closed == "controlado":
        lines.append("Un incendio controlado puede reactivarse: sigue atento a SENAPRED y a la autoridad local.")
    return {
        "title": title, "body": " ".join(lines), "footer": OFFICIAL_FOOTER, "level": "aviso", "kind": "oficial",
        "place": {"id": place["id"], "name": place["name"], "lat": place["lat"], "lon": place["lon"]},
        "observation": {"id": f"conaf:{fire['id']}:estado", "lat": fire["lat"], "lon": fire["lon"],
                        "observed_at": fire.get("extinguished_at") or fire.get("controlled_at") or fire["started_at"],
                        "source": "CONAF", "satellite": "CONAF"},
        "official": {k: fire.get(k) for k in ("id", "name", "status", "status_raw", "started_at", "area_ha", "comuna")},
        "distance_km": round(distance_km, 2), "bearing_deg": round(bearing), "direction": direction,
        "url": incident_url({"id": incident_id} if incident_id else None, fire["lat"], fire["lon"]),
    }


async def evaluate_status_change(db: Database, fires_changed: list[dict[str, Any]],
                                 now: datetime | None = None) -> list[dict[str, Any]]:
    """Avisa una sola vez a los lugares ya alertados cuando CONAF cierra el incendio (ALR-02).

    Solo escribe a quien recibió el aviso `conaf:<id>` del incendio: cerrar a quien nunca oyó
    hablar de él es ruido. El `observation_id` `conaf:<id>:estado` con el UNIQUE(place_id,
    observation_id) de `alerts` hace el aviso idempotente vía INSERT OR IGNORE.
    """
    now = now or datetime.now(timezone.utc)
    if not fires_changed:
        return []
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    # Mismo criterio que evaluate_official: con varias fichas bajo un mismo official_ref,
    # el enlace lleva a la más reciente.
    linked: dict[str, str] = {}
    for row in db.query("SELECT id, official_ref FROM incidents WHERE official_ref IS NOT NULL "
                        "ORDER BY last_seen_at ASC"):
        linked[row["official_ref"]] = row["id"]
    created: list[dict[str, Any]] = []
    for fire in fires_changed:
        for row in db.query("SELECT DISTINCT place_id FROM alerts WHERE observation_id = ?",
                            (f"conaf:{fire['id']}",)):
            place = db.one("SELECT * FROM places WHERE id = ?", (row["place_id"],))
            if not place:  # el lugar se borró entre el aviso original y el cierre
                continue
            distance = haversine_km(place["lat"], place["lon"], fire["lat"], fire["lon"])
            bearing = bearing_deg(place["lat"], place["lon"], fire["lat"], fire["lon"])
            payload = compose_status_change(place, fire, distance, bearing, incident_id=linked.get(fire["id"]))
            # `observed_at` es el momento del cierre, no el inicio del incendio: es lo que
            # cuenta para la ventana de reintento de entrega.
            alert_id = db.insert(
                "INSERT OR IGNORE INTO alerts(place_id, observation_id, level, distance_km, bearing_deg, upwind, lat, lon, "
                "observed_at, created_at, payload) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (place["id"], f"conaf:{fire['id']}:estado", "aviso", round(distance, 3), round(bearing, 1), 0,
                 fire["lat"], fire["lon"], stamp, stamp, json.dumps(payload, ensure_ascii=False)))
            if alert_id:
                created.append({"id": alert_id, "subscriber_id": place["subscriber_id"], "level": "aviso",
                                "created_at": stamp, "payload": payload})
    return created


DMC_KIND_ADVICE = {
    "viento": "El viento aviva un incendio y arrastra pavesas: con este aviso, un foco cerca puede acelerar o cambiar de dirección.",
    "calor": "El calor extremo seca la vegetación y agota a quien trabaja afuera: un foco nuevo puede crecer rápido.",
}


def _cap_time(value: Any) -> datetime | None:
    """Un instante ISO-8601 del CAP; None si falta, no se puede leer o viene sin zona.

    Mismo criterio que en routes/common.py: ante la duda el aviso se trata como vigente.
    """
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else None


def compose_dmc(place: dict[str, Any], alert: dict[str, Any], now: datetime) -> dict[str, Any]:
    """Aviso de la DMC (viento o calor extremo) que toca la comuna de un lugar guardado (ALR-14).

    `url` lleva a «Mi zona», donde la interfaz muestra el aviso; el enlace oficial (`web`)
    va en el texto, porque format_alert de Telegram arma su enlace como base_url + url.
    """
    comuna = territory().by_code.get(place.get("comuna_code") or 0)
    zone = f"la comuna de {comuna.name}" if comuna else "tu zona"
    label = dmc.KIND_LABELS.get(alert.get("kind") or "", alert.get("kind") or "tiempo").lower()
    onset, expires = _cap_time(alert.get("onset")), _cap_time(alert.get("expires"))
    # `observed_at` es el inicio del aviso (o ahora si falta): en UTC para que la ventana de
    # reintento de deliver lo compare bien contra sus cotas en «…Z».
    observed = (onset or now).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    title = f"Aviso de {label} de la DMC para {zone}"
    lines = [f"La Dirección Meteorológica de Chile emitió un aviso de {label} que incluye {zone}, "
             f"donde está «{place['name']}».",
             f"Dice la DMC: «{alert.get('headline') or alert.get('event') or 'aviso meteorológico'}»."]
    if onset and expires:
        lines.append(f"{'Rige' if onset <= now else 'Regirá'} desde el {onset.astimezone(CHILE_TZ):%d-%m %H:%M} "
                     f"hasta el {expires.astimezone(CHILE_TZ):%d-%m %H:%M} hora de Chile.")
    elif expires:
        lines.append(f"Vigente hasta el {expires.astimezone(CHILE_TZ):%d-%m %H:%M} hora de Chile.")
    if advice := DMC_KIND_ADVICE.get(alert.get("kind") or ""):
        lines.append(advice)
    if alert.get("web"):
        lines.append(f"Aviso completo de la DMC: {alert['web']}")
    return {
        "title": title, "body": " ".join(lines), "footer": OFFICIAL_FOOTER, "level": "aviso", "kind": "dmc",
        "place": {"id": place["id"], "name": place["name"], "lat": place["lat"], "lon": place["lon"]},
        "observation": {"id": f"dmc:{alert['id']}", "observed_at": observed, "source": dmc.SOURCE},
        "dmc": {k: alert.get(k) for k in ("id", "kind", "event", "headline", "severity", "urgency",
                                          "onset", "expires", "web")},
        "url": "/#/mi-zona",
    }


async def evaluate_dmc(db: Database, alerts: list[dict[str, Any]],
                       now: datetime | None = None) -> list[dict[str, Any]]:
    """Avisa una vez por aviso y lugar cuando un aviso de la DMC toca la comuna del lugar (ALR-14).

    `alerts` son las filas de `dmc_alerts` que deja `ingest_dmc` (la lista vigente completa):
    el cruce es por comuna, no por distancia ni radio. El `observation_id` `dmc:<id CAP>` con el
    UNIQUE(place_id, observation_id) lo hace idempotente aunque la tabla se reescriba en cada
    ingesta, y un lugar agregado después recibe los avisos que sigan vigentes. Siempre «aviso»,
    nunca «urgente»: es un pronóstico de zona, no un foco medido contra el viento del lugar.
    """
    now = now or datetime.now(timezone.utc)
    vigentes = []
    for alert in alerts:
        if not alert.get("id"):
            continue
        expires = _cap_time(alert.get("expires"))
        if expires is not None and expires <= now:
            continue  # un aviso ya vencido no despierta a nadie
        comunas = set(json.loads(alert.get("comunas") or "[]"))
        if comunas:
            vigentes.append((alert, comunas))
    created: list[dict[str, Any]] = []
    if not vigentes:
        return created
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    for place in db.query("SELECT * FROM places"):
        if not place.get("comuna_code"):
            continue  # un lugar fuera de una comuna conocida no tiene avisos DMC que cruzar
        comuna = territory().by_code.get(place["comuna_code"])
        # El aviso es de zona: el punto guardado es el centro de la comuna (o el lugar si falta).
        lat, lon = (comuna.center[1], comuna.center[0]) if comuna else (place["lat"], place["lon"])
        distance = haversine_km(place["lat"], place["lon"], lat, lon)
        bearing = bearing_deg(place["lat"], place["lon"], lat, lon)
        for alert, alert_comunas in vigentes:
            if place["comuna_code"] not in alert_comunas:
                continue
            payload = compose_dmc(place, alert, now)
            alert_id = db.insert(
                "INSERT OR IGNORE INTO alerts(place_id, observation_id, level, distance_km, bearing_deg, upwind, lat, lon, "
                "observed_at, created_at, payload) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (place["id"], f"dmc:{alert['id']}", "aviso", round(distance, 3), round(bearing, 1), 0,
                 lat, lon, payload["observation"]["observed_at"], stamp, json.dumps(payload, ensure_ascii=False)))
            if alert_id:
                created.append({"id": alert_id, "subscriber_id": place["subscriber_id"], "level": "aviso",
                                "created_at": stamp, "payload": payload})
    return created

"""Alertas por lugar: detecciones nuevas cerca de los lugares que cada persona guardó.

Niveles:
- "aviso": detección confiable dentro del radio elegido.
- "urgente": además el viento sopla desde el foco hacia el lugar, o el foco está muy cerca
  (≤ 2 km), o está a ≤ 5 km en un día de riesgo alto/extremo. Si en el lugar vive una persona
  mayor o alguien que necesita ayuda para salir, «urgente» también cuando el foco está a ≤ 5 km
  o su incidente ya es «posible» o más (necesita más tiempo: se avisa antes); una detección
  suelta y lejana, que puede ser una quema, queda en «aviso» con el texto reforzado (FIX-08).

Las alertas de BRASA no son alertas oficiales: siempre remiten a SENAPRED y a los números de emergencia.
Cada detección pertenece a un incidente (backend/incidents.py): el aviso cuenta cuánta evidencia lo respalda,
y los incidentes cuya evidencia cae entera en una fuente de calor fija probable (volcán, industria) no avisan.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable
from zoneinfo import ZoneInfo

from backend import incidents as incidents_mod
from backend import lluvia as lluvia_mod
from backend import reports as reports_mod
from backend import scars as scars_mod
from backend import spread as spread_mod
from backend.db import Database
from backend.geo import bearing_deg, cardinal, haversine_km, is_upwind, territory
from backend.providers import dmc
from backend.providers import senapred

CHILE_TZ = ZoneInfo("America/Santiago")
# MAGALLANES-01: una sola zona para todo el país (America/Santiago) y los textos dicen
# «hora de Chile continental». Magallanes usa UTC-3 todo el año; rotular la zona evita
# que una hora convertida a Santiago se lea como la hora local.
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

# ALR-24/ALR-26: la edad del foco en palabras y el paso siguiente, una sola vez por cuerpo.
# Los textos son los que ya dice la app (ramas de Qué hacer y la guía de este archivo):
# nada de «va a llegar» ni «predicción» — el avance es siempre un escenario estimado.
ACTION_LINE = "Si ves fuego o humo, llama al 130 (CONAF) o al 132 (Bomberos); no te acerques."
ACTION_BY_LEVEL = {
    "urgente": ("Aleja a tu familia de pastizales, techos y acopios, ten agua y documentos a mano "
                "y cierra las ventanas si llega humo; no esperes a ver el fuego para salir. "
                "Sigue a SENAPRED y a Bomberos."),
}


def age_phrase(observed_at: str, now: datetime | None = None) -> str:
    """«hace menos de 5 minutos», «hace N minutos», «hace N hora(s)» (ALR-24)."""
    minutos = max(0, int(((now or datetime.now(timezone.utc)) - _parse(observed_at)).total_seconds() // 60))
    if minutos < 5:
        return "hace menos de 5 minutos"
    if minutos < 60:
        return f"hace {minutos} minutos"
    horas = round(minutos / 60)
    return f"hace {horas} hora" + ("" if horas == 1 else "s")


# ALR-19: silencio nocturno 23:00–07:00 de Chile (America/Santiago, nunca offset fijo) para los
# avisos que no son urgentes. Sin columna ni migración por diseño: la fila aplazada queda con
# delivered='["silencio"]' y delivered_at nulo, así la bandeja la conserva y la entrega la retoma
# a las 07:00 sin perder su observation_id.
QUIET_FROM = 23  # hora local desde la que se aplaza
QUIET_TO = 7     # hora local desde la que se entrega lo aplazado


def en_silencio(now: datetime) -> bool:
    """True si `now` cae entre 23:00 y 07:00 en America/Santiago."""
    h = now.astimezone(CHILE_TZ).hour
    return h >= QUIET_FROM or h < QUIET_TO


def aplazable(payload: dict[str, Any]) -> bool:
    """Solo el nivel «aviso» se aplaza; un urgente nunca espera."""
    return payload.get("level") == "aviso"


def refresh_age_line(body: str, observed_at: str, now: datetime | None = None) -> str:
    """Al entregar una aplazada, «Detectado hace X» se recompone con la hora real de entrega."""
    return re.sub(r"Detectado hace[^.]*\.", f"Detectado {age_phrase(observed_at, now)}.", body)


def vencida(payload: dict[str, Any], now: datetime | None = None) -> bool:
    """Un aviso aplazado con `expires` (DMC) vencido ya no se entrega."""
    exp = payload.get("expires")
    if not exp:
        return False
    try:
        return _parse(exp) < (now or datetime.now(timezone.utc))
    except (TypeError, ValueError):
        return False


def silencio_nota(created_at: str) -> str:
    """Coletilla para el aviso que salió a las 07:00 tras la noche de silencio."""
    hhmm = _parse(created_at).astimezone(CHILE_TZ).strftime("%H:%M")
    return f"Te lo enviamos ahora porque anoche no quisimos despertarte (aviso de las {hhmm} hora de Chile)."


# ALR-20: topes anti-fatiga de INV-09, encendidos por omisión. `AVISO_TOPES=0` los apaga sin
# desplegar. La excepción es la escalada de estado (observation_id «…:estado»), que siempre sale.
CAP_URGENTE_INCIDENTE = 1   # 1 urgente por incidente y lugar
CAP_URGENTE_24H = 1         # 1 urgente por lugar cada 24 h
CAP_AVISOS_7D = 3           # 3 avisos entregados por lugar cada 7 días


def aviso_topes_activos() -> bool:
    return os.environ.get("AVISO_TOPES", "1") != "0"


def caps_exceeded(db: Database, alert: dict[str, Any], now: datetime | None = None) -> str | None:
    """Motivo del freno («urgente_incidente», «urgente_24h», «aviso_7d») o None si el aviso sale.

    `alert` trae id, place_id, level, observation_id e incident_id (este último si lo hay).
    Cuentan las entregadas de verdad: las filas aplazadas por silencio no entregaron nada.
    """
    if not aviso_topes_activos():
        return None
    if str(alert.get("observation_id") or "").endswith(":estado"):
        return None  # escalada de estado: siempre sale
    if str(alert.get("observation_id") or "").startswith("senapred:"):
        return None  # alerta oficial de la autoridad: el freno anti-fatiga no la silencia
    now = now or datetime.now(timezone.utc)
    place_id, alert_id = alert.get("place_id"), alert.get("id") or -1
    # Solo cuentan entregas reales por canal: filas frenadas («tope:…»), vacías («[]») o
    # aplazadas («silencio») no alimentan el tope; los cierres «…:estado» tampoco, ni los
    # avisos «senapred:» — una alerta de zona no es un foco y no consume el cupo de nadie.
    entregada = ("delivered_at IS NOT NULL AND (delivered LIKE '%push%' OR delivered LIKE '%telegram%') "
                 "AND observation_id NOT LIKE '%:estado' AND observation_id NOT LIKE 'senapred:%'")
    if alert.get("level") == "urgente":
        inc = alert.get("incident_id")
        if inc:
            n = db.one("SELECT COUNT(*) AS n FROM alerts WHERE place_id = ? AND level = 'urgente' AND id != ? "
                       f"AND {entregada} AND json_extract(payload, '$.incident.id') = ?",
                       (place_id, alert_id, inc))["n"]
            if n >= CAP_URGENTE_INCIDENTE:
                return "urgente_incidente"
        since = (now - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
        n = db.one("SELECT COUNT(*) AS n FROM alerts WHERE place_id = ? AND level = 'urgente' AND id != ? "
                   f"AND {entregada} AND delivered_at >= ?", (place_id, alert_id, since))["n"]
        if n >= CAP_URGENTE_24H:
            return "urgente_24h"
        return None  # a un urgente solo lo frenan sus dos topes, nunca el de 3 por semana
    since7 = (now - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    n = db.one(f"SELECT COUNT(*) AS n FROM alerts WHERE place_id = ? AND id != ? AND {entregada} "
               "AND delivered_at >= ?", (place_id, alert_id, since7))["n"]
    if n >= CAP_AVISOS_7D:
        return "aviso_7d"
    return None
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


# FIX-08: con una persona mayor en el lugar, «urgente» pide evidencia de fuego real (un incidente
# ya «posible» o más), cercanía (≤ 5 km) o viento hacia el lugar. Una anomalía suelta dentro del
# radio (una quema agrícola la gatillaba igual) queda en «aviso».
OLDER_ADULT_URGENT = {"posible", "reportado", "confirmado", "controlado"}


def classify(distance_km: float, upwind: bool, risk_level: str | None, older_adult: bool = False,
             incident_status: str | None = None) -> str:
    if upwind or distance_km <= 2.0 or (distance_km <= 5.0 and risk_level in {"alto", "extremo"}):
        return "urgente"
    if older_adult and (distance_km <= 5.0 or incident_status in OLDER_ADULT_URGENT):
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


# Cómo se nombra cada región en palabras: «región del Maule», «región de Valparaíso»,
# «región Metropolitana». El nombre corto de `comunas.geojson` no trae el artículo.
_REGION_ARTICULO = {"Maule": "del", "Ñuble": "del", "Biobío": "del", "Metropolitana": ""}


def _region_en_palabras(region: str) -> str:
    """«región del Maule», «región de Valparaíso», «región Metropolitana»; si ya dice «región…» va tal cual."""
    r = region.strip()
    if r.lower().startswith(("región", "region")):
        return r
    articulo = _REGION_ARTICULO.get(r, "de")
    return f"región {articulo} {r}".replace("  ", " ")


def _donde_comuna(place: dict[str, Any], *, comuna: Any = None, region: Any = None,
                  lat: float | None = None, lon: float | None = None) -> str:
    """En qué comuna cayó el foco, para la primera frase del aviso (ALR-41).

    «en tu misma comuna» cuando coincide con la del lugar; «en la comuna de Pencahue
    (región del Maule)» con el dato declarado o el que resuelve `locate` sobre el punto;
    "" cuando no se sabe: la frase queda como antes, sin inventar nombres ni dejar huecos.
    """
    terr = territory()
    nombre, region_name, code = comuna, region, None
    if nombre:
        encontradas = terr.comunas_named(str(nombre))
        if len(encontradas) == 1:
            code = encontradas[0].code
            region_name = region_name or encontradas[0].region
        else:
            # El texto nombró una región o una comuna ambigua: no se publica la palabra
            # tal cual, la comuna la decide el punto si lo hay.
            nombre = None
    if code is None and lat is not None and lon is not None:
        encontrada = terr.locate(lat, lon)
        if encontrada:
            nombre = nombre or encontrada.name
            region_name = region_name or encontrada.region
            code = encontrada.code
    if not nombre:
        return ""
    propia = terr.by_code.get(place.get("comuna_code") or 0)
    if propia and code == propia.code:
        return "en tu misma comuna"
    texto = f"en la comuna de {nombre}"
    if region_name:
        texto += f" ({_region_en_palabras(str(region_name))})"
    return texto


def spread_line(spread: dict[str, Any] | None, satellite_seen: bool) -> str | None:
    """El rumbo del escenario estimado en palabras, para el texto del aviso (FUEGO-24).

    Nunca lleva números de avance (km/h, ISI, hora): un push que dice «2 km/h hacia el sur»
    se lee como pronóstico oficial. Aquí solo va el rumbo probable y la remisión a la ficha,
    donde el escenario está con sus supuestos y su nota de estimación. Sin rumbo conocido
    no se inventa uno: devuelve None.
    """
    if not spread or spread.get("direction_deg") is None:
        return None
    clause = f"el viento de ahora lo empujaría hacia el {cardinal(spread['direction_deg'])}"
    lead = f"Los satélites lo siguen viendo activo y {clause}" if satellite_seen else clause[0].upper() + clause[1:]
    return f"{lead}; el escenario estimado está en la ficha del incidente."


def compose(place: dict[str, Any], obs: dict[str, Any], distance_km: float, bearing: float, upwind: bool,
            level: str, wind: dict[str, Any] | None, others: int, incident: dict[str, Any] | None = None,
            spread: dict[str, Any] | None = None) -> dict[str, Any]:
    observed = datetime.fromisoformat(obs["observed_at"].replace("Z", "+00:00")).astimezone(CHILE_TZ)
    direction = cardinal(bearing)
    donde = _donde_comuna(place, comuna=obs.get("comuna"), region=obs.get("region"), lat=obs["lat"], lon=obs["lon"])
    title = ("URGENTE · " if level == "urgente" else "") + f"Foco de calor a {distance_km:.1f} km de {place['name']}"
    lines = [f"Detección satelital {donde + ', ' if donde else ''}al {direction} de «{place['name']}», a {distance_km:.1f} km."]
    if upwind and wind:
        lines.append(f"El viento sopla desde esa dirección hacia tu lugar ({wind.get('speed', 0):.0f} km/h): el humo y las pavesas pueden avanzar hacia ti.")
    summary = incident_line(incident) if incident else None
    if summary:
        lines.append(summary)
    if others:
        lines.append(f"Hay {others} detección adicional dentro de tu radio." if others == 1
                     else f"Hay {others} detecciones adicionales dentro de tu radio.")
    if phrase := spread_line(spread, satellite_seen=bool(incident and incident.get("n_obs", 0) >= 2)):
        lines.append(phrase)
    lines.append(f"Detectado {age_phrase(obs['observed_at'])}.")
    if action := ACTION_BY_LEVEL.get(level):
        lines.append(action)
    if place.get("older_adult"):
        lines.append("En este lugar vive una persona mayor o alguien que necesita ayuda para salir: "
                     "confirma con ella ahora"
                     + ("." if level == "urgente" else
                        " y, si hay que salir, salgan temprano, sin esperar a ver el fuego."))
    lines.append(f"Fuente: {source_label(obs)} · {observed:%d-%m %H:%M} hora de Chile continental · confianza {obs.get('confidence') or 'no informada'}.")
    lines.append("Un foco de calor no confirma un incendio. Verifica con fuentes oficiales y prepárate para actuar.")
    lines.append(ACTION_LINE)
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
    # Los avisos `dmc:`, `daily:` y `senapred:` también quedan fuera: su lat/lon es el centro
    # de la comuna, no un foco, y si contaran silenciarían detecciones reales dentro de
    # DEDUPE_KM de ese centro.
    return db.query("SELECT lat, lon, level FROM alerts WHERE place_id = ? AND created_at >= ? "
                    "AND observation_id NOT LIKE 'conaf:%:estado' AND observation_id NOT LIKE 'dmc:%' "
                    "AND observation_id NOT LIKE 'daily:%' AND observation_id NOT LIKE 'senapred:%'",
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
    spreads: dict[str, dict[str, Any] | None] = {}  # el escenario se calcula una vez por incidente
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
            level = classify(distance, upwind, _risk_today(db, place.get("comuna_code"), now),
                             bool(place.get("older_adult")), (incidents.get(obs["id"]) or {}).get("status"))
            duplicate = any(
                haversine_km(prev["lat"], prev["lon"], obs["lat"], obs["lon"]) <= DEDUPE_KM
                and LEVEL_RANK[prev["level"]] >= LEVEL_RANK[level]
                for prev in recent
            )
            if duplicate:
                continue
            incident = incidents.get(obs["id"])
            spread = None
            if incident:
                if incident["id"] not in spreads:
                    spreads[incident["id"]] = spread_mod.estimate(db, incident, now)
                spread = spreads[incident["id"]]
            payload = compose(place, obs, distance, bearing, upwind, level, wind, len(near) - 1, incident, spread)
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
                     incident_id: str | None = None, spread: dict[str, Any] | None = None) -> dict[str, Any]:
    started = datetime.fromisoformat(fire["started_at"].replace("Z", "+00:00")).astimezone(CHILE_TZ)
    direction = cardinal(bearing)
    donde = _donde_comuna(place, comuna=fire.get("comuna"), region=fire.get("region"),
                          lat=fire.get("lat"), lon=fire.get("lon"))
    title = ("URGENTE · " if level == "urgente" else "") + f"CONAF informa un incendio a {distance_km:.1f} km de {place['name']}"
    lines = [f"CONAF informa el incendio «{fire['name'] or 'sin nombre'}» {donde + ', ' if donde else ''}al {direction} de «{place['name']}», a {distance_km:.1f} km.",
             f"Estado según CONAF: {fire['status_raw'] or 'informado'} · inicio {started:%d-%m %H:%M} hora de Chile continental"
             f" ({age_phrase(fire['started_at'])})"
             + (f" · {fire['area_ha']:.1f} ha".replace(".", ",") if fire.get("area_ha") else "") + "."]
    if phrase := spread_line(spread, satellite_seen=False):
        lines.append(phrase)
    if place.get("older_adult"):
        lines.append("En este lugar vive una persona mayor o alguien que necesita ayuda para salir: confirma con ella ahora.")
    lines.append("Sigue las instrucciones de SENAPRED y de la autoridad local. Si te ordenan evacuar, hazlo de inmediato.")
    lines.append(ACTION_LINE)
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
    linked: dict[str, dict[str, Any]] = {}
    for row in db.query("SELECT * FROM incidents WHERE official_ref IS NOT NULL ORDER BY last_seen_at ASC"):
        linked[row["official_ref"]] = row
    spreads: dict[str, dict[str, Any] | None] = {}
    for place in db.query("SELECT * FROM places"):
        near = sorted(((haversine_km(place["lat"], place["lon"], f["lat"], f["lon"]), f) for f in fresh), key=lambda x: x[0])
        near = [(d, f) for d, f in near if d <= place["radius_km"]]
        if not near:
            continue
        distance, fire = near[0]
        bearing = bearing_deg(place["lat"], place["lon"], fire["lat"], fire["lon"])
        level = "urgente" if distance <= OFFICIAL_URGENT_KM or place.get("older_adult") else "aviso"
        incident = linked.get(fire["id"])
        if incident and incident["id"] not in spreads:
            spreads[incident["id"]] = spread_mod.estimate(db, incident, now)
        payload = compose_official(place, fire, distance, bearing, level,
                                   incident_id=incident["id"] if incident else None,
                                   spread=spreads.get(incident["id"]) if incident else None)
        alert_id = db.insert(
            "INSERT OR IGNORE INTO alerts(place_id, observation_id, level, distance_km, bearing_deg, upwind, lat, lon, "
            "observed_at, created_at, payload) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (place["id"], f"conaf:{fire['id']}", level, round(distance, 3), round(bearing, 1), 0, fire["lat"], fire["lon"],
             fire["started_at"], stamp, json.dumps(payload, ensure_ascii=False)))
        if alert_id:
            created.append({"id": alert_id, "subscriber_id": place["subscriber_id"], "level": level, "created_at": stamp, "payload": payload})
    return created


REPORT_RADIUS_KM = 5.0   # un reporte vecinal solo avisa en la cercanía inmediata, aunque el radio del lugar sea mayor
REPORT_DEDUPE_MIN = 30   # reportes verificados en esta ventana comparten el mismo aviso por lugar…
REPORT_DEDUPE_KM = 2.0   # …solo si apuntan al mismo incendio: más lejos es un fuego distinto y avisa igual


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
             f"({created:%d-%m %H:%M} hora de Chile continental), revisado por BRASA {age_phrase(report['created_at'])}.",
             "Un reporte vecinal no confirma un incendio. Si ves fuego o humo, llama primero a CONAF (130) "
             "o a Bomberos (132) y sigue las fuentes oficiales."]
    if place.get("older_adult"):
        lines.append("En este lugar vive una persona mayor o alguien que necesita ayuda para salir: confirma con ella ahora.")
    lines.append(ACTION_LINE)
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
    mismo reporte se modera dos veces, y un lugar que ya recibió un aviso de reporte a
    menos de REPORT_DEDUPE_KM del nuevo en los últimos REPORT_DEDUPE_MIN minutos no recibe
    otro: aprobar en lote varios reportes del mismo incendio no encola N «un vecino informó»
    iguales (REV-03), pero un incendio distinto más lejos sí avisa (REV-10). La entrega la
    hace Services.deliver en el ciclo siguiente.
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
    # Lugares que ya oyeron «un vecino informó» recién por este mismo punto: un segundo aviso
    # en media hora diría lo mismo del mismo hecho. La comparación es por lugar y por ubicación
    # del aviso previo (`alerts.lat/lon`, la del reporte que lo generó): un fuego distinto a
    # más de REPORT_DEDUPE_KM no comparte el silencio (REV-10).
    since = (now - timedelta(minutes=REPORT_DEDUPE_MIN)).strftime("%Y-%m-%dT%H:%M:%SZ")
    recent: dict[str, list[tuple[float, float]]] = {}
    for row in db.query("SELECT place_id, lat, lon FROM alerts "
                        "WHERE observation_id LIKE 'report:%' AND created_at >= ?", (since,)):
        recent.setdefault(row["place_id"], []).append((row["lat"], row["lon"]))
    created: list[dict[str, Any]] = []
    for place in db.query("SELECT * FROM places"):
        if any(haversine_km(prev_lat, prev_lon, lat, lon) <= REPORT_DEDUPE_KM
               for prev_lat, prev_lon in recent.get(place["id"], ())):
            continue
        distance = haversine_km(place["lat"], place["lon"], report["lat"], report["lon"])
        if distance > min(place["radius_km"], REPORT_RADIUS_KM):
            continue
        bearing = bearing_deg(place["lat"], place["lon"], report["lat"], report["lon"])
        payload = compose_report(place, report, distance, bearing)
        # `observed_at` guarda el momento del aviso, no el del reporte: es lo que se muestra
        # (mismo criterio que el cierre CONAF, ALR-02).
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
            # `observed_at` es el momento del cierre, no el inicio del incendio: es lo que se muestra.
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
    # AGUA-07: lluvia y tormenta solo avisan donde hay cicatriz (ver evaluate_dmc). El consejo
    # son frases oficiales de SENAPRED, citadas con su página como hace el de calor (ALR-22).
    "lluvia": ("«No te ubiques en quebradas o desembocaduras por donde podrían pasar aluviones, ni en obras "
               "como puentes o badenes. Si debes evacuar, hazlo hacia lugares que la autoridad haya definido "
               "como Puntos de Encuentro» (SENAPRED, aluviones: https://www.senapred.cl/aluviones/)."),
    "tormenta": ("«Permanece al interior del inmueble. No salgas a menos que sea absolutamente necesario. "
                 "No utilices objetos metálicos como tendederos, herramientas agrícolas o de construcción» "
                 "(SENAPRED, tormentas eléctricas: https://www.senapred.cl/tormentas-electricas/)."),
}
# ALR-22: la acción de salud que lleva el aviso de calor al teléfono, redactada desde las dos
# primeras fuentes de web/js/calor.js (MINSAL «alerta de calor» y SENAPRED «calor extremo»).
DMC_CALOR_ACTION = ("Con calor extremo, toma agua a cada rato aunque no sientas sed, evita el sol y el esfuerzo "
                    "entre las 11 y las 17 h, y revisa a las personas mayores, a los niños y a quien tenga una "
                    "enfermedad crónica (MINSAL, alerta de calor: https://www.minsal.cl/alerta-de-calor/ · "
                    "SENAPRED, calor extremo).")

# AGUA-07: la lluvia intensa o la tormenta sobre suelo quemado sí cambian qué hacer (aluvión
# post-incendio, docs/ALUVIONES.md). Solo avisan en comunas con cicatriz de la temporada;
# en el resto son el ruido que el filtro de la DMC descarta a propósito.
DMC_LLUVIA_KINDS = {"lluvia", "tormenta"}
DMC_LLUVIA_LABELS = {"lluvia": "lluvia intensa", "tormenta": "tormenta"}
SCAR_DAYS = 90      # la cicatriz de la temporada se mide sobre los últimos 90 días
SCAR_MIN_HA = 10.0  # menos superficie quemada no justifica avisar a la comuna


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
    """Aviso de la DMC (viento, calor, lluvia o tormenta) que toca la comuna de un lugar guardado (ALR-14).

    `url` lleva a «Mi zona», donde la interfaz muestra el aviso; el enlace oficial (`web`)
    va en el texto, porque format_alert de Telegram arma su enlace como base_url + url.
    """
    comuna = territory().by_code.get(place.get("comuna_code") or 0)
    zone = f"la comuna de {comuna.name}" if comuna else "tu zona"
    label = dmc.KIND_LABELS.get(alert.get("kind") or "", alert.get("kind") or "tiempo").lower()
    onset, expires = _cap_time(alert.get("onset")), _cap_time(alert.get("expires"))
    # `observed_at` es el inicio del aviso (o ahora si falta): es lo que se muestra; la ventana
    # de reintento de `deliver` se mide sobre `created_at`, que aquí es «ahora».
    observed = (onset or now).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    title = f"Aviso de {label} de la DMC para {zone}"
    lines = [f"La Dirección Meteorológica de Chile emitió un aviso de {label} que incluye {zone}, "
             f"donde está «{place['name']}».",
             f"Dice la DMC: «{alert.get('headline') or alert.get('event') or 'aviso meteorológico'}»."]
    if onset and expires:
        lines.append(f"{'Rige' if onset <= now else 'Regirá'} desde el {onset.astimezone(CHILE_TZ):%d-%m %H:%M} "
                     f"hasta el {expires.astimezone(CHILE_TZ):%d-%m %H:%M} hora de Chile continental.")
    elif expires:
        lines.append(f"Vigente hasta el {expires.astimezone(CHILE_TZ):%d-%m %H:%M} hora de Chile continental.")
    if advice := DMC_KIND_ADVICE.get(alert.get("kind") or ""):
        lines.append(advice)
    if alert.get("kind") == "calor":
        lines.append(DMC_CALOR_ACTION)
    if alert.get("web"):
        lines.append(f"Aviso completo de la DMC: {alert['web']}")
    return {
        "title": title, "body": " ".join(lines), "footer": OFFICIAL_FOOTER, "level": "aviso", "kind": "dmc",
        "place": {"id": place["id"], "name": place["name"], "lat": place["lat"], "lon": place["lon"]},
        "observation": {"id": f"dmc:{alert['id']}", "observed_at": observed, "source": dmc.SOURCE},
        "dmc": {k: alert.get(k) for k in ("id", "kind", "event", "headline", "severity", "urgency",
                                          "onset", "expires", "web")},
        # `vencida` lee `expires` del nivel superior al entregar una pendiente (deliver);
        # dentro de `dmc` quedaba invisible y un aviso aplazado se entregaba vencido.
        "expires": alert.get("expires"),
        "url": "/#/mi-zona",
    }


def compose_dmc_scar(place: dict[str, Any], alert: dict[str, Any], comuna: Any, now: datetime) -> dict[str, Any]:
    """Aviso de lluvia o tormenta de la DMC sobre una comuna con cicatriz de la temporada (AGUA-07).

    Solo existe para este par aviso + suelo quemado: la remisión a SENAPRED va en el cuerpo
    y en el pie, porque no es una alerta oficial de evacuación. El `expires` de nivel raíz
    deja que `vencida` no entregue de mañana un aviso meteorológico que ya no rige.
    """
    zone = f"la comuna de {comuna.name}" if comuna else "tu zona"
    label = DMC_LLUVIA_LABELS.get(alert.get("kind") or "", alert.get("kind") or "lluvia")
    onset, expires = _cap_time(alert.get("onset")), _cap_time(alert.get("expires"))
    observed = (onset or now).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = ["Aviso de lluvia de la DMC sobre una zona quemada: aléjate de quebradas y laderas quemadas.",
             f"La Dirección Meteorológica de Chile emitió un aviso de {label} que incluye {zone}, "
             f"donde está «{place['name']}», y esa comuna tiene suelo quemado esta temporada.",
             f"Dice la DMC: «{alert.get('headline') or alert.get('event') or 'aviso meteorológico'}»."]
    if onset and expires:
        lines.append(f"{'Rige' if onset <= now else 'Regirá'} desde el {onset.astimezone(CHILE_TZ):%d-%m %H:%M} "
                     f"hasta el {expires.astimezone(CHILE_TZ):%d-%m %H:%M} hora de Chile continental.")
    elif expires:
        lines.append(f"Vigente hasta el {expires.astimezone(CHILE_TZ):%d-%m %H:%M} hora de Chile continental.")
    if advice := DMC_KIND_ADVICE.get(alert.get("kind") or ""):
        lines.append(advice)
    if alert.get("web"):
        lines.append(f"Aviso completo de la DMC: {alert['web']}")
    lines.append(lluvia_mod.SENAPRED)
    return {
        "title": "Aviso de lluvia de la DMC sobre una zona quemada", "body": " ".join(lines),
        "footer": OFFICIAL_FOOTER, "level": "aviso", "kind": "dmc",
        "expires": alert.get("expires") or "",
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

    AGUA-07: un aviso de lluvia intensa o tormenta solo avisa cuando la comuna del lugar
    tiene cicatriz de la temporada (≥ SCAR_MIN_HA en SCAR_DAYS días, `season_scars`); sin
    suelo quemado es ruido y no avisa. Como es «aviso», la entrega pasa por los topes
    `caps_exceeded` y por el silencio nocturno como cualquier otro.
    """
    now = now or datetime.now(timezone.utc)
    # La cicatriz se consulta una vez por comuna, solo si hay avisos de lluvia vigentes.
    cicatriz: dict[int, bool] = {}

    def con_cicatriz(code: int) -> bool:
        if code not in cicatriz:
            scars = scars_mod.season_scars(db, SCAR_DAYS, comuna_code=code)
            cicatriz[code] = any((f.get("properties") or {}).get("ha", 0) >= SCAR_MIN_HA
                                 for f in scars.get("features") or [])
        return cicatriz[code]

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
            if (alert.get("kind") or "") in DMC_LLUVIA_KINDS:
                if not con_cicatriz(place["comuna_code"]):
                    continue  # lluvia sin suelo quemado: no cambia qué hacer, sería ruido
                payload = compose_dmc_scar(place, alert, comuna, now)
            else:
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


def compose_daily(place: dict[str, Any], dato: dict[str, Any]) -> dict[str, Any]:
    """El aviso preventivo de la mañana (ALR-04): «hoy hay condiciones», siempre «aviso».

    `dato` resume por qué se avisa: «date» y «stamp» (día local y momento UTC del aviso),
    «comuna», «boton_rojo_hours» (horas en Botón Rojo hoy según CONAF) y «level» (30-30-30
    de BRASA). Es una prevención de zona, no un foco medido contra el viento del lugar:
    nunca llega a «urgente». `url` lleva a «Mi zona», donde se ve el riesgo del día.
    """
    zone = f"la comuna de {dato['comuna']}" if dato.get("comuna") else "tu zona"
    if dato.get("boton_rojo_hours"):
        reason = f"CONAF pronosticó Botón Rojo hoy para {zone}: condiciones extremas para que un incendio se propague."
    else:
        reason = f"El pronóstico de BRASA marca riesgo {dato.get('level') or 'alto'} hoy en {zone}."
    lines = [reason,
             "Hoy no hagas fuego: nada de quemas, asado al aire libre ni trabajos que suelten chispas.",
             "Deja el teléfono cargado y ten agua y documentos a mano por si hay que salir."]
    if place.get("older_adult"):
        lines.append("En este lugar vive una persona mayor o alguien que necesita ayuda para salir: "
                     "confirma con ella ahora.")
    return {
        "title": f"Hoy hay condiciones para incendios cerca de {place['name']}",
        "body": " ".join(lines), "footer": OFFICIAL_FOOTER, "level": "aviso", "kind": "diario",
        "place": {"id": place["id"], "name": place["name"], "lat": place["lat"], "lon": place["lon"]},
        "observation": {"id": f"daily:{dato['date']}", "observed_at": dato["stamp"], "source": "BRASA"},
        "daily": {k: dato.get(k) for k in ("date", "comuna", "boton_rojo_hours", "level")},
        "url": "/#/mi-zona",
    }


async def evaluate_daily(db: Database, now: datetime | None = None) -> list[dict[str, Any]]:
    """Crea el aviso preventivo del día para los lugares que lo pidieron (ALR-04).

    El horario lo decide quien la llama (Services.daily_brief, desde las 08:00 de Chile);
    aquí solo se mira el día local. Elegible = lugar con `daily_brief` en una comuna con
    Botón Rojo hoy (tabla `boton_rojo`, pronóstico oficial de CONAF) o riesgo 30-30-30
    «alto»/«extremo» en `risk_daily`. Una por lugar y día: el `observation_id`
    `daily:<fecha>` deduplica las pasadas siguientes, y el UNIQUE(place_id,
    observation_id) lo hace idempotente aunque dos corridas coincidan. Sin riesgo no se
    avisa nada: el mensaje solo existe si el día lo justifica.
    """
    now = now or datetime.now(timezone.utc)
    today = now.astimezone(CHILE_TZ).date().isoformat()
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    already = {row["place_id"] for row in db.query("SELECT place_id FROM alerts WHERE observation_id = ?",
                                                  (f"daily:{today}",))}
    risk_today = {row["comuna_code"]: row["level"] for row in db.query(
        "SELECT comuna_code, level FROM risk_daily WHERE date = ?", (today,))}
    br_today = {row["comuna_code"]: row["hours"] for row in db.query(
        "SELECT comuna_code, hours FROM boton_rojo WHERE date = ?", (today,))}
    created: list[dict[str, Any]] = []
    for place in db.query("SELECT * FROM places WHERE daily_brief = 1"):
        if place["id"] in already or not place.get("comuna_code"):
            continue
        hours = br_today.get(place["comuna_code"])
        level = risk_today.get(place["comuna_code"])
        if not hours and level not in {"alto", "extremo"}:
            continue
        comuna = territory().by_code.get(place["comuna_code"])
        dato = {"date": today, "stamp": stamp, "comuna": comuna.name if comuna else None,
                "boton_rojo_hours": hours, "level": level}
        payload = compose_daily(place, dato)
        # El aviso es de zona: el punto guardado es el centro de la comuna (o el lugar si falta).
        lat, lon = (comuna.center[1], comuna.center[0]) if comuna else (place["lat"], place["lon"])
        alert_id = db.insert(
            "INSERT OR IGNORE INTO alerts(place_id, observation_id, level, distance_km, bearing_deg, upwind, lat, lon, "
            "observed_at, created_at, payload) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (place["id"], f"daily:{today}", "aviso",
             round(haversine_km(place["lat"], place["lon"], lat, lon), 3),
             round(bearing_deg(place["lat"], place["lon"], lat, lon), 1), 0,
             lat, lon, stamp, stamp, json.dumps(payload, ensure_ascii=False)))
        if alert_id:
            created.append({"id": alert_id, "subscriber_id": place["subscriber_id"], "level": "aviso",
                            "created_at": stamp, "payload": payload})
    return created


# ALR-42: una alerta oficial de SENAPRED que nombra la comuna (o la región) de un lugar
# guardado genera un aviso con su texto exacto. El pie es distinto al de los avisos propios:
# aquí el mensaje SÍ es la alerta oficial, reenviada sin cambios.
SENAPRED_FOOTER = ("Es el texto oficial de SENAPRED, reenviado sin cambios: BRASA no emite alertas. "
                   "Emergencias: 130 CONAF · 132 Bomberos · 131 SAMU · 133 Carabineros.")


def compose_senapred(place: dict[str, Any], alerta: dict[str, Any], comuna: Any, now: datetime) -> dict[str, Any]:
    """Aviso de una alerta oficial de SENAPRED que nombra la comuna o la región del lugar (ALR-42).

    El título oficial va íntegro, sin reescritura, con su fecha y su enlace en el cuerpo;
    `url` lleva a «Mi zona», donde la interfaz muestra también las vigentes.
    """
    zone = (f"la comuna de {comuna.name}" if alerta.get("scope") == "comuna"
            else f"la {_region_en_palabras(comuna.region)}")
    level = senapred.nivel(alerta.get("title") or "")
    issued = _cap_time(alerta.get("issued_at"))
    observed = (issued or now).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    title = ("URGENTE · " if level == "urgente" else "") + f"Alerta oficial de SENAPRED para {zone}"
    lines = [f"SENAPRED declaró una alerta que nombra a {zone}, donde está «{place['name']}».",
             f"Dice SENAPRED: «{alerta['title']}»."]
    if issued:
        lines.append(f"Emitida el {issued.astimezone(CHILE_TZ):%d-%m %H:%M} hora de Chile continental.")
    if action := ACTION_BY_LEVEL.get(level):
        lines.append(action)
    if place.get("older_adult"):
        lines.append("En este lugar vive una persona mayor o alguien que necesita ayuda para salir: "
                     "confirma con ella ahora.")
    lines.append("BRASA no emite alertas: es el texto oficial de SENAPRED.")
    if alerta.get("url"):
        lines.append(f"Alerta oficial completa: {alerta['url']}")
    return {
        "title": title, "body": " ".join(lines), "footer": SENAPRED_FOOTER, "level": level,
        "kind": "senapred",
        "place": {"id": place["id"], "name": place["name"], "lat": place["lat"], "lon": place["lon"]},
        "observation": {"id": f"senapred:{alerta['id']}", "observed_at": observed, "source": senapred.SOURCE},
        "senapred": {k: alerta.get(k) for k in ("id", "title", "issued_at", "url", "scope")},
        "url": "/#/mi-zona",
    }


async def evaluate_senapred(db: Database, alertas: list[dict[str, Any]],
                            now: datetime | None = None) -> list[dict[str, Any]]:
    """Avisa cuando una alerta oficial de SENAPRED nombra la comuna o la región del lugar (ALR-42).

    `alertas` son las vigentes que deja `senapred.fetch_alerts` (o la caché `senapred:alertas`);
    el cruce es por el título formulaico con `senapred.para_lugar`, no por distancia ni radio.
    El nivel sale del propio título (`senapred.nivel`): Alerta Roja u orden de evacuación
    → «urgente»; Alerta Amarilla, Temprana Preventiva y lo que no calce → «aviso». Las
    alertas de la autoridad no compiten con el freno anti-fatiga (`caps_exceeded` las
    exime como a los cierres «…:estado»: una orden de evacuación no puede quedar
    silenciada por el tope de urgentes); el «aviso» sí se aplaza en el silencio
    nocturno como cualquier otro. La deduplicación es por base, no por un `if`:
    `observation_id` `senapred:<id>` con el UNIQUE(place_id, observation_id) hace que la
    misma alerta en dos ciclos genere un solo aviso por lugar.

    No hay cota de edad: `isActive` de la fuente es la vigencia (si SENAPRED mantiene
    activa una alerta de hace semanas, sigue siendo una orden vigente), el aviso es único
    por lugar y el cuerpo muestra «Emitida el…» en hora de Chile — decisión registrada
    tras la revisión geo, no un descuido.
    """
    now = now or datetime.now(timezone.utc)
    alertas = [a for a in alertas if a.get("id") and a.get("title")]
    if not alertas:
        return []
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    terr = territory()
    created: list[dict[str, Any]] = []
    for place in db.query("SELECT * FROM places"):
        comuna = terr.by_code.get(place.get("comuna_code") or 0)
        if comuna is None:
            continue  # fuera de una comuna conocida no hay título que cruzar
        # El aviso es de zona: el punto guardado es el centro de la comuna.
        lat, lon = comuna.center[1], comuna.center[0]
        distance = haversine_km(place["lat"], place["lon"], lat, lon)
        bearing = bearing_deg(place["lat"], place["lon"], lat, lon)
        for alerta in senapred.para_lugar(alertas, comuna.name, comuna.region):
            payload = compose_senapred(place, alerta, comuna, now)
            alert_id = db.insert(
                "INSERT OR IGNORE INTO alerts(place_id, observation_id, level, distance_km, bearing_deg, upwind, lat, lon, "
                "observed_at, created_at, payload) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (place["id"], payload["observation"]["id"], payload["level"], round(distance, 3),
                 round(bearing, 1), 0, lat, lon, payload["observation"]["observed_at"], stamp,
                 json.dumps(payload, ensure_ascii=False)))
            if alert_id:
                created.append({"id": alert_id, "subscriber_id": place["subscriber_id"],
                                "level": payload["level"], "created_at": stamp, "payload": payload})
    return created

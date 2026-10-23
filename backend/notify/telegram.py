"""Bot de Telegram: alertas por lugar sin instalar nada más que Telegram.

Flujo:
- En la web, "Recibir en Telegram" genera un enlace t.me/<bot>?start=<código> que vincula el chat.
- O directamente en el bot: compartir una ubicación crea un lugar con radio de 10 km.
Comandos: /start, /lugares, /diario, /radio, /borrar, /riesgo, /focos, /ayuda.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from math import cos, radians
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from backend import alerts as alerts_mod
from backend.db import Database
from backend.geo import bearing_deg, cardinal, haversine_km, territory

log = logging.getLogger("brasa.telegram")
API = "https://api.telegram.org"
CHILE_TZ = ZoneInfo("America/Santiago")

HELP = (
    "BRASA Chile te avisa cuando aparece un foco de calor satelital cerca de tus lugares.\n\n"
    "• Comparte una ubicación (📎 → Ubicación) para agregar un lugar con radio de 10 km.\n"
    "• /lugares — ver tus lugares\n"
    "• /diario — aviso preventivo de la mañana (on para encender, off para apagar)\n"
    "• /radio <km> — radio de aviso de tus lugares, de 5 a 100 km\n"
    "• /riesgo — índice 30-30-30 de hoy en tus comunas\n"
    "• /focos — incendios y focos vigentes cerca de tus lugares en las últimas 24 h (/focos 48h para más)\n"
    "• /borrar — eliminar todos tus lugares (te pide confirmar)\n\n"
    "BRASA no reemplaza las alertas oficiales de SENAPRED. Emergencias: 130 CONAF · 132 Bomberos · 133 Carabineros."
)
LEVEL_EMOJI = {"aviso": "🟠", "urgente": "🔴"}
RISK_EMOJI = {"bajo": "🟢", "moderado": "🟡", "alto": "🟠", "extremo": "🔴"}
FOCOS_DEFAULT_H = 24
FOCOS_MAX_H = 72
FOCOS_PER_PLACE = 3
FOCOS_LINES = 5
ALERT_MAX_CHARS = 4096  # sendMessage de Telegram rechaza textos más largos
# Cierre obligatorio del listado (ALR-30): el foco no es un incendio confirmado y
# BRASA no es la vía oficial de emergencia.
FOCOS_FOOTER = ("Un foco de calor no confirma un incendio. BRASA no reemplaza las alertas de SENAPRED. "
                "Emergencias: 130 CONAF · 132 Bomberos.")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def format_alert(payload: dict[str, Any], base_url: str) -> str:
    emoji = LEVEL_EMOJI.get(payload.get("level"), "🟠")
    target = payload.get("url", "/")
    # El enlace puede llevar a la ficha del incidente o al mapa: la etiqueta dice a dónde va.
    label = "Ver el incidente" if target.startswith("/#/incendio/") else "Ver en el mapa"
    head = f"{emoji} {payload['title']}\n\n"
    # Título, enlace y pie no se recortan: el enlace es lo que el vecino abre.
    tail = f"\n\n{label}: {base_url}{target}\n\n{payload['footer']}"
    body = payload["body"]
    room = ALERT_MAX_CHARS - len(head) - len(tail) - 1  # 1 por la elipsis
    if len(body) > room:
        body = body[: max(room, 0)] + "…"
    return f"{head}{body}{tail}"


class TelegramRateLimited(RuntimeError):
    """Telegram respondió 429; `retry_after` son los segundos que pide esperar."""

    def __init__(self, retry_after: float):
        super().__init__(f"Telegram pidió esperar {retry_after:g} s (límite de tasa).")
        self.retry_after = retry_after


async def call(client: httpx.AsyncClient, token: str, method: str, **params: Any) -> Any:
    try:
        response = await client.post(f"{API}/bot{token}/{method}", json=params)
        data = response.json()
    except (httpx.RequestError, ValueError) as exc:
        raise RuntimeError(f"Telegram no respondió ({type(exc).__name__}).") from None
    if not data.get("ok"):
        if data.get("error_code") == 429:
            try:
                retry_after = float((data.get("parameters") or {}).get("retry_after", 1))
            except (TypeError, ValueError):
                retry_after = 1
            raise TelegramRateLimited(retry_after if retry_after > 0 else 1)
        raise RuntimeError(f"Telegram rechazó {method}: {data.get('description', 'sin detalle')}")
    return data.get("result")


async def send_message(
    client: httpx.AsyncClient, token: str, chat_id: str, text: str, sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
) -> bool:
    try:
        await call(client, token, "sendMessage", chat_id=chat_id, text=text, disable_web_page_preview=True)
        return True
    except TelegramRateLimited as exc:
        # Un solo reintento y la espera se acota a 10 s: un aviso viejo ya no sirve.
        await sleep(min(exc.retry_after, 10))
    except RuntimeError as exc:
        log.warning("%s", exc)
        return False
    try:
        await call(client, token, "sendMessage", chat_id=chat_id, text=text, disable_web_page_preview=True)
        return True
    except RuntimeError as exc:  # un segundo 429 también cae aquí: no hay bucle
        log.warning("%s", exc)
        return False


def subscriber_for_chat(db: Database, chat_id: str) -> dict[str, Any]:
    row = db.one("SELECT * FROM subscribers WHERE telegram_chat_id = ?", (chat_id,))
    if row:
        return row
    sid = secrets.token_urlsafe(24)
    db.execute("INSERT INTO subscribers(id, created_at, telegram_chat_id) VALUES (?, ?, ?)", (sid, _now(), chat_id))
    return db.one("SELECT * FROM subscribers WHERE id = ?", (sid,))


def _focos_hours(text: str) -> int | None:
    """Ventana de /focos: 6 h por omisión; el número va de 1 a 72 y admite la h («24h»)."""
    parts = text.split(maxsplit=1)
    if len(parts) == 1:
        return FOCOS_DEFAULT_H
    arg = parts[1].strip().lower().removesuffix("h").strip()
    try:
        hours = int(arg)
    except ValueError:
        return None
    return hours if 1 <= hours <= FOCOS_MAX_H else None


def _box_half_deg(place: dict[str, Any]) -> tuple[float, float]:
    """Medios lados de la caja del radio en grados; un grado de longitud se acorta con la latitud."""
    lon_km = 111.32 * max(cos(radians(place["lat"])), 0.2)
    return place["radius_km"] / 110.57, place["radius_km"] / lon_km


def _km_text(km: float) -> str:
    return (f"{km:.1f}" if km < 10 else f"{km:.0f}").replace(".", ",")


def _age_text(stamp: str, now: datetime) -> str:
    """«hace 25 min» / «hace 3 h» / «hace 4 días» sobre una marca UTC."""
    try:
        minutes = (now - datetime.fromisoformat(stamp.replace("Z", "+00:00"))).total_seconds() / 60
    except (AttributeError, ValueError):
        return "fecha n/d"
    if minutes < 90:
        return f"hace {max(int(minutes), 1)} min"
    if minutes < 48 * 60:
        return f"hace {int(minutes / 60 + 0.5)} h"
    return f"hace {int(minutes / 1440)} días"


def _foco_line(place: dict[str, Any], inc: dict[str, Any], distance: float, now: datetime) -> str:
    """Una línea por foco: lugar, distancia y rumbo, estado en palabras y antigüedad del dato."""
    head = f"«{place['name']}»: a {_km_text(distance)} km al {cardinal(bearing_deg(place['lat'], place['lon'], inc['lat'], inc['lon']))}"
    seen = _age_text(inc["last_seen_at"], now)
    if inc.get("fixed_source"):
        # No es un incendio: se marca con la razón por la que la evidencia cayó
        # entera en una fuente de calor fija (volcán o industria), nunca como fuego.
        return f"⚪ {head} · fuente de calor fija: {inc.get('fixed_reason') or 'volcán o industria'} · visto {seen}"
    frase = alerts_mod.INCIDENT_PHRASE.get(inc["status"], "grupo de detecciones")
    if inc.get("n_obs", 0) < 2:
        return f"🟠 {head} · {frase} · visto {seen}"
    try:
        span_h = (
            datetime.fromisoformat(inc["last_seen_at"].replace("Z", "+00:00"))
            - datetime.fromisoformat(inc["first_seen_at"].replace("Z", "+00:00"))
        ).total_seconds() / 3600
    except (AttributeError, ValueError):
        span_h = 0
    span = f"en {span_h:.0f} h" if span_h >= 1 else "en menos de una hora"
    return f"🟠 {head} · {frase}, {inc['n_obs']} detecciones {span} · visto {seen}"


def focos_reply(db: Database, chat_id: str, text: str) -> str:
    """«¿Qué se está quemando cerca?»: incidentes vigentes dentro del radio de cada lugar guardado."""
    hours = _focos_hours(text)
    if hours is None:
        return f"Uso: /focos para las últimas {FOCOS_DEFAULT_H} h, o /focos 48h para mirar de 1 a {FOCOS_MAX_H} h atrás."
    try:
        sub = subscriber_for_chat(db, chat_id)
        places = db.query("SELECT * FROM places WHERE subscriber_id = ? ORDER BY created_at", (sub["id"],))
        if not places:
            return "Agrega un lugar primero (comparte una ubicación)."
        now = datetime.now(timezone.utc)
        since = (now - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
        found: dict[str, tuple[float, dict[str, Any], dict[str, Any]]] = {}
        last_seen: str | None = None
        for place in places:
            half_lat, half_lon = _box_half_deg(place)
            rows = db.query(
                "SELECT id, status, lat, lon, n_obs, first_seen_at, last_seen_at, fixed_source, fixed_reason "
                "FROM incidents WHERE status != 'descartado' "
                "AND lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?",
                (place["lat"] - half_lat, place["lat"] + half_lat, place["lon"] - half_lon, place["lon"] + half_lon),
            )
            near = []
            for inc in rows:
                distance = haversine_km(place["lat"], place["lon"], inc["lat"], inc["lon"])
                if distance > place["radius_km"]:
                    continue
                if last_seen is None or inc["last_seen_at"] > last_seen:
                    last_seen = inc["last_seen_at"]
                if inc["status"] != "extinguido" and inc["last_seen_at"] >= since:
                    near.append((distance, inc))
            # De cada lugar a lo sumo sus tres focos más cercanos; el mismo incidente en
            # dos lugares se cuenta una vez, en el lugar desde el que se ve más cerca.
            for distance, inc in sorted(near, key=lambda item: item[0])[:FOCOS_PER_PLACE]:
                if inc["id"] not in found or distance < found[inc["id"]][0]:
                    found[inc["id"]] = (distance, place, inc)
    except Exception:
        log.exception("No se pudo consultar los focos del chat %s", chat_id)
        return (
            "No pude consultar los focos ahora mismo: la base de datos no respondió. "
            f"Intenta de nuevo en unos minutos.\n\n{FOCOS_FOOTER}"
        )
    items = sorted(found.values(), key=lambda item: item[0])
    if not items:
        radii = {place["radius_km"] for place in places}
        where = f"a menos de {next(iter(radii)):g} km" if len(radii) == 1 else "dentro del radio de aviso de tus lugares"
        reply = f"No hay focos de calor vigentes {where} en las últimas {hours} h."
        reply += (
            f" La última detección de la zona es de {_age_text(last_seen, now)}."
            if last_seen
            else " Todavía no se ha visto calor cerca de tus lugares."
        )
        return f"{reply}\n\n{FOCOS_FOOTER}"
    lines = [_foco_line(place, inc, distance, now) for distance, place, inc in items[:FOCOS_LINES]]
    if len(items) > FOCOS_LINES:
        n = len(items) - FOCOS_LINES
        lines.append(f"…y {n} {'foco' if n == 1 else 'focos'} más.")
    return (
        f"Focos e incendios vigentes en las últimas {hours} h cerca de tus lugares:\n"
        + "\n".join(lines)
        + f"\n\n{FOCOS_FOOTER}"
    )


def handle_update(db: Database, update: dict[str, Any]) -> str | None:
    """Procesa un mensaje entrante. Devuelve el texto de respuesta (o None)."""
    message = update.get("message") or {}
    chat_id = str((message.get("chat") or {}).get("id") or "")
    if not chat_id:
        return None
    text = (message.get("text") or "").strip()
    location = message.get("location")
    if text.startswith("/start"):
        parts = text.split(maxsplit=1)
        if len(parts) == 2:
            linked = db.one("SELECT * FROM subscribers WHERE link_code = ?", (parts[1].strip(),))
            if linked:
                db.execute("UPDATE subscribers SET telegram_chat_id = NULL WHERE telegram_chat_id = ? AND id != ?", (chat_id, linked["id"]))
                db.execute("UPDATE subscribers SET telegram_chat_id = ?, link_code = NULL WHERE id = ?", (chat_id, linked["id"]))
                n = db.one("SELECT COUNT(*) AS n FROM places WHERE subscriber_id = ?", (linked["id"],))["n"]
                return f"✅ Listo. Recibirás aquí las alertas de tus {n} lugar(es) guardados en BRASA.\n\n{HELP}"
        subscriber_for_chat(db, chat_id)
        return f"👋 Bienvenido a BRASA Chile.\n\n{HELP}"
    if location:
        sub = subscriber_for_chat(db, chat_id)
        lat, lon = float(location["latitude"]), float(location["longitude"])
        comuna = territory().locate(lat, lon)
        name = f"Ubicación en {comuna.name}" if comuna else "Ubicación compartida"
        db.execute(
            "INSERT INTO places(id, subscriber_id, name, kind, lat, lon, radius_km, comuna_code, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), sub["id"], name, "otro", lat, lon, 10, comuna.code if comuna else None, _now()),
        )
        where = f" ({comuna.name}, {comuna.region})" if comuna else ""
        return f"📍 Lugar guardado{where}. Te avisaré si aparece un foco de calor a menos de 10 km."
    if text.startswith("/lugares"):
        sub = subscriber_for_chat(db, chat_id)
        places = db.query("SELECT name, radius_km, daily_brief FROM places WHERE subscriber_id = ? ORDER BY created_at", (sub["id"],))
        if not places:
            return "Aún no tienes lugares. Comparte una ubicación para agregar uno."
        return "Tus lugares:\n" + "\n".join(
            f"• {p['name']} — radio {p['radius_km']:g} km{' · ☀️ aviso diario' if p['daily_brief'] else ''}" for p in places
        )
    if text.startswith("/diario"):
        sub = subscriber_for_chat(db, chat_id)
        parts = text.split(maxsplit=1)
        if len(parts) == 1:
            n = db.one("SELECT COUNT(*) AS n FROM places WHERE subscriber_id = ?", (sub["id"],))["n"]
            if not n:
                return "Aún no tienes lugares. Comparte una ubicación para agregar uno."
            on = db.one("SELECT COUNT(*) AS n FROM places WHERE subscriber_id = ? AND daily_brief = 1", (sub["id"],))["n"]
            return (
                f"☀️ El aviso de la mañana está encendido en {on} de {n} lugar(es).\n/diario on lo enciende en todos · /diario off lo apaga."
            )
        arg = parts[1].strip().lower()
        if arg not in ("on", "off"):
            return "Uso: /diario on para encender el aviso de la mañana o /diario off para apagarlo."
        n = db.execute("UPDATE places SET daily_brief = ? WHERE subscriber_id = ?", (1 if arg == "on" else 0, sub["id"]))
        if not n:
            return "Aún no tienes lugares. Comparte una ubicación para agregar uno."
        on = n if arg == "on" else 0
        return f"☀️ Aviso diario {'encendido' if arg == 'on' else 'apagado'}: {on} de {n} lugar(es) lo recibirán."
    if text.startswith("/radio"):
        sub = subscriber_for_chat(db, chat_id)
        parts = text.split(maxsplit=1)
        if len(parts) == 2:
            try:
                km = float(parts[1].strip().replace(",", "."))
            except ValueError:
                km = 0
            if not 5 <= km <= 100:
                return "Uso: /radio <km> con un número de 5 a 100 (por ejemplo /radio 25)."
            n = db.execute("UPDATE places SET radius_km = ? WHERE subscriber_id = ?", (km, sub["id"]))
            if not n:
                return "Aún no tienes lugares. Comparte una ubicación para agregar uno."
            return f"📏 Radio de aviso: {km:g} km en tus {n} lugar(es)."
        places = db.query("SELECT name, radius_km FROM places WHERE subscriber_id = ? ORDER BY created_at", (sub["id"],))
        if not places:
            return "Aún no tienes lugares. Comparte una ubicación para agregar uno."
        if len({p["radius_km"] for p in places}) == 1:
            return (
                f"📏 Radio de aviso: {places[0]['radius_km']:g} km en tus {len(places)} lugar(es).\nPara cambiarlo: /radio <km> (5 a 100)."
            )
        return (
            "Tus radios de aviso:\n"
            + "\n".join(f"• {p['name']} — {p['radius_km']:g} km" for p in places)
            + "\nCámbialos con /radio <km> (5 a 100)."
        )
    if text.startswith("/borrar"):
        sub = subscriber_for_chat(db, chat_id)
        n = db.one("SELECT COUNT(*) AS n FROM places WHERE subscriber_id = ?", (sub["id"],))["n"]
        if not n:
            return "No tienes lugares guardados. Nada que borrar."
        parts = text.split(maxsplit=1)
        if len(parts) == 2 and parts[1].strip().lower() == "confirmar":
            db.execute("DELETE FROM places WHERE subscriber_id = ?", (sub["id"],))
            return "🗑️ Eliminé tus lugares. Ya no recibirás alertas hasta que agregues uno nuevo."
        if len(parts) == 1:
            return f"⚠️ Para borrar tus {n} lugar(es), manda /borrar confirmar. Cualquier otro texto cancela."
        return "No borré nada. Para eliminar tus lugares manda /borrar y después /borrar confirmar."
    if text.startswith("/riesgo"):
        sub = subscriber_for_chat(db, chat_id)
        rows = db.query("SELECT DISTINCT p.comuna_code FROM places p WHERE p.subscriber_id = ? AND p.comuna_code IS NOT NULL", (sub["id"],))
        if not rows:
            return "Agrega un lugar primero (comparte una ubicación)."
        lines = []
        today = datetime.now(CHILE_TZ).date().isoformat()
        for r in rows:
            comuna = territory().by_code.get(r["comuna_code"])
            risk = db.one(
                "SELECT level, tmax, rhmin, windmax FROM risk_daily WHERE comuna_code = ? AND date >= ? ORDER BY date LIMIT 1",
                (r["comuna_code"], today),
            )
            if comuna and risk:
                emoji = RISK_EMOJI.get(risk["level"], "⚪")
                lines.append(
                    f"{emoji} {comuna.name}: {risk['level'].upper()} · máx {risk['tmax']:.0f} °C, "
                    f"HR mín {risk['rhmin']:.0f} %, viento {risk['windmax']:.0f} km/h"
                )
            elif comuna:
                lines.append(f"⚪ {comuna.name}: sin pronóstico calculado todavía")
        return "Índice 30-30-30 de hoy:\n" + "\n".join(lines)
    if text.startswith("/focos"):
        return focos_reply(db, chat_id, text)
    if text.startswith("/ayuda") or text.startswith("/help") or text:
        return HELP
    return None


async def set_webhook(client: httpx.AsyncClient, token: str, url: str, secret: str) -> None:
    """Modo webhook (Cloudflare): Telegram envía cada mensaje a la URL pública, con un secreto en cabecera."""
    await call(client, token, "setWebhook", url=url, secret_token=secret, allowed_updates=["message"], drop_pending_updates=False)


async def poll_once(db: Database, client: httpx.AsyncClient, token: str, timeout: int = 25) -> int:
    offset = int(db.kv_get("telegram_offset") or 0)
    updates = await call(client, token, "getUpdates", offset=offset, timeout=timeout, allowed_updates=["message"])
    for update in updates or []:
        db.kv_set("telegram_offset", str(int(update["update_id"]) + 1))
        reply = handle_update(db, update)
        chat_id = str(((update.get("message") or {}).get("chat") or {}).get("id") or "")
        if reply and chat_id:
            await send_message(client, token, chat_id, reply)
    return len(updates or [])

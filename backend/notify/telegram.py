"""Bot de Telegram: alertas por lugar sin instalar nada más que Telegram.

Flujo:
- En la web, "Recibir en Telegram" genera un enlace t.me/<bot>?start=<código> que vincula el chat.
- O directamente en el bot: compartir una ubicación crea un lugar con radio de 10 km.
Comandos: /start, /lugares, /borrar, /riesgo, /ayuda.
"""
from __future__ import annotations

import asyncio
import logging
import secrets
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from backend.db import Database
from backend.geo import territory

log = logging.getLogger("brasa.telegram")
API = "https://api.telegram.org"
CHILE_TZ = ZoneInfo("America/Santiago")

HELP = (
    "BRASA Chile te avisa cuando aparece un foco de calor satelital cerca de tus lugares.\n\n"
    "• Comparte una ubicación (📎 → Ubicación) para agregar un lugar con radio de 10 km.\n"
    "• /lugares — ver tus lugares\n• /borrar — eliminar todos tus lugares\n"
    "• /riesgo — índice 30-30-30 de hoy en tus comunas\n\n"
    "BRASA no reemplaza las alertas oficiales de SENAPRED. Emergencias: 130 CONAF · 132 Bomberos · 133 Carabineros."
)
LEVEL_EMOJI = {"aviso": "🟠", "urgente": "🔴"}
RISK_EMOJI = {"bajo": "🟢", "moderado": "🟡", "alto": "🟠", "extremo": "🔴"}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def format_alert(payload: dict[str, Any], base_url: str) -> str:
    emoji = LEVEL_EMOJI.get(payload.get("level"), "🟠")
    target = payload.get("url", "/")
    # El enlace puede llevar a la ficha del incidente o al mapa: la etiqueta dice a dónde va.
    label = "Ver el incidente" if target.startswith("/#/incendio/") else "Ver en el mapa"
    return f"{emoji} {payload['title']}\n\n{payload['body']}\n\n{label}: {base_url}{target}\n\n{payload['footer']}"


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


async def send_message(client: httpx.AsyncClient, token: str, chat_id: str, text: str,
                       sleep: Callable[[float], Awaitable[None]] = asyncio.sleep) -> bool:
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
        db.execute("INSERT INTO places(id, subscriber_id, name, kind, lat, lon, radius_km, comuna_code, created_at) "
                   "VALUES (?,?,?,?,?,?,?,?,?)",
                   (str(uuid.uuid4()), sub["id"], name, "otro", lat, lon, 10, comuna.code if comuna else None, _now()))
        where = f" ({comuna.name}, {comuna.region})" if comuna else ""
        return f"📍 Lugar guardado{where}. Te avisaré si aparece un foco de calor a menos de 10 km."
    if text.startswith("/lugares"):
        sub = subscriber_for_chat(db, chat_id)
        places = db.query("SELECT name, radius_km FROM places WHERE subscriber_id = ? ORDER BY created_at", (sub["id"],))
        if not places:
            return "Aún no tienes lugares. Comparte una ubicación para agregar uno."
        return "Tus lugares:\n" + "\n".join(f"• {p['name']} — radio {p['radius_km']:.0f} km" for p in places)
    if text.startswith("/borrar"):
        sub = subscriber_for_chat(db, chat_id)
        db.execute("DELETE FROM places WHERE subscriber_id = ?", (sub["id"],))
        return "🗑️ Eliminé tus lugares. Ya no recibirás alertas hasta que agregues uno nuevo."
    if text.startswith("/riesgo"):
        sub = subscriber_for_chat(db, chat_id)
        rows = db.query(
            "SELECT DISTINCT p.comuna_code FROM places p WHERE p.subscriber_id = ? AND p.comuna_code IS NOT NULL", (sub["id"],))
        if not rows:
            return "Agrega un lugar primero (comparte una ubicación)."
        lines = []
        today = datetime.now(CHILE_TZ).date().isoformat()
        for r in rows:
            comuna = territory().by_code.get(r["comuna_code"])
            risk = db.one("SELECT level, tmax, rhmin, windmax FROM risk_daily WHERE comuna_code = ? AND date >= ? ORDER BY date LIMIT 1",
                          (r["comuna_code"], today))
            if comuna and risk:
                lines.append(f"{RISK_EMOJI[risk['level']]} {comuna.name}: {risk['level'].upper()} · máx {risk['tmax']:.0f} °C, "
                             f"HR mín {risk['rhmin']:.0f} %, viento {risk['windmax']:.0f} km/h")
            elif comuna:
                lines.append(f"⚪ {comuna.name}: sin pronóstico calculado todavía")
        return "Índice 30-30-30 de hoy:\n" + "\n".join(lines)
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

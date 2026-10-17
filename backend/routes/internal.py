"""Rutas de operación: ciclo disparado por cron, respaldo y webhook de Telegram.

/api/internal/* exige INTERNAL_TOKEN (si no está definido, no existe). En Cloudflare, además,
el Worker las bloquea para el público y solo las usa su Cron Trigger.
"""
from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response

from backend.notify import telegram
from backend.routes.common import services
from backend.services import Services

router = APIRouter(prefix="/api")


def internal_auth(request: Request, x_internal_token: str = Header(default="", alias="X-Internal-Token")) -> None:
    expected = services(request).settings.internal_token
    if not expected or not hmac.compare_digest(x_internal_token, expected):
        raise HTTPException(404, "No encontrado.")


@router.post("/internal/tick", dependencies=[Depends(internal_auth)], include_in_schema=False)
async def tick(response: Response, wait: bool = False, svc: Services = Depends(services)):
    """Por defecto responde de inmediato y corre el ciclo en segundo plano: el Cron Trigger de Cloudflare
    corta a los ~30 s, y despertar el contenedor + relleno GOES + FIRMS puede tardar más. `?wait=1` espera."""
    if wait:
        return await svc.tick_and_backup()
    response.status_code = 202
    return {"started": svc.start_tick(), "last_cycle": svc.last_cycle}


@router.post("/internal/backup", dependencies=[Depends(internal_auth)], include_in_schema=False)
async def backup(svc: Services = Depends(services)):
    if not svc.persistence.enabled:
        raise HTTPException(409, "Sin almacenamiento remoto configurado (BRASA_STORAGE_URL).")
    await svc.persistence.flush()
    return {"ok": True}


@router.post("/telegram/webhook", include_in_schema=False)
async def telegram_webhook(request: Request, svc: Services = Depends(services),
                           x_secret: str = Header(default="", alias="X-Telegram-Bot-Api-Secret-Token")):
    secret = svc.settings.telegram_webhook_secret
    if not secret or not hmac.compare_digest(x_secret, secret):
        raise HTTPException(403, "Secreto inválido.")
    update = await request.json()
    reply = telegram.handle_update(svc.db, update)
    chat_id = str(((update.get("message") or {}).get("chat") or {}).get("id") or "")
    if reply and chat_id:
        await telegram.send_message(svc.client, svc.settings.telegram_bot_token, chat_id, reply)
    return {"ok": True}

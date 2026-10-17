"""Rutas de operación: ciclo disparado por cron, respaldo y webhook de Telegram.

/api/internal/* exige INTERNAL_TOKEN (si no está definido, no existe). En Cloudflare, además,
el Worker las bloquea para el público y solo las usa su Cron Trigger.
"""
from __future__ import annotations

import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from backend.notify import telegram
from backend.routes.common import services
from backend.services import Services

router = APIRouter(prefix="/api")


def internal_auth(request: Request, x_internal_token: str = Header(default="", alias="X-Internal-Token")) -> None:
    expected = services(request).settings.internal_token
    if not expected or not hmac.compare_digest(x_internal_token, expected):
        raise HTTPException(404, "No encontrado.")


@router.post("/internal/tick", dependencies=[Depends(internal_auth)], include_in_schema=False)
async def tick(svc: Services = Depends(services)):
    result = await svc.tick()
    if svc.persistence.enabled:
        try:
            result["backup"] = await svc.persistence.flush()
        except Exception as exc:
            result["backup"] = False
            result["backup_error"] = str(exc)
    return result


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

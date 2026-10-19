"""Notificaciones Web Push (estándar VAPID). Las claves se generan una vez y quedan en la base local."""
from __future__ import annotations

import base64
import json
import logging
from typing import Any

from backend.db import Database

log = logging.getLogger("brasa.webpush")


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def ensure_keys(db: Database) -> tuple[str, str]:
    """Devuelve (clave privada PEM, clave pública para el navegador en base64url)."""
    private_pem = db.kv_get("vapid_private_pem")
    public_b64 = db.kv_get("vapid_public_b64")
    if private_pem and public_b64:
        return private_pem, public_b64
    from cryptography.hazmat.primitives import serialization
    from py_vapid import Vapid

    vapid = Vapid()
    vapid.generate_keys()
    private_pem = vapid.private_pem().decode()
    public_raw = vapid.public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    public_b64 = _b64url(public_raw)
    db.kv_set("vapid_private_pem", private_pem)
    db.kv_set("vapid_public_b64", public_b64)
    return private_pem, public_b64


def send(db: Database, subscriber: dict[str, Any], payload: dict[str, Any], contact: str) -> bool:
    """Envía una notificación. Si el navegador revocó la suscripción (404/410) se elimina."""
    if not subscriber.get("push_endpoint"):
        return False
    from pywebpush import WebPushException, webpush

    private_pem, _ = ensure_keys(db)
    try:
        from py_vapid import Vapid

        urgent = payload.get("level") == "urgente"
        # Urgency: high despierta al teléfono del modo reposo, y el TTL de 6 h retiene el
        # aviso en la cola si el equipo está apagado o sin señal: un urgente importa horas.
        webpush(
            subscription_info={"endpoint": subscriber["push_endpoint"],
                               "keys": {"p256dh": subscriber["push_p256dh"], "auth": subscriber["push_auth"]}},
            data=json.dumps(payload, ensure_ascii=False),
            vapid_private_key=Vapid.from_pem(private_pem.encode()),
            vapid_claims={"sub": contact},
            headers={"Urgency": "high" if urgent else "normal"},
            ttl=21600 if urgent else 3600,
        )
        return True
    except WebPushException as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status in (404, 410):
            db.execute("UPDATE subscribers SET push_endpoint = NULL, push_p256dh = NULL, push_auth = NULL WHERE id = ?",
                       (subscriber["id"],))
        log.warning("Web push falló (%s)", status or type(exc).__name__)
        return False

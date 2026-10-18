"""Dependencias comunes de la API."""
from __future__ import annotations

import hmac
import json
import re
import time
from collections import defaultdict, deque
from typing import Any

from fastapi import Header, HTTPException, Request

from backend.providers import dmc
from backend.services import Services


def services(request: Request) -> Services:
    return request.app.state.services


def subscriber(request: Request, x_brasa_token: str = Header(default="", alias="X-Brasa-Token")) -> dict:
    """La identidad es un token secreto aleatorio guardado en el dispositivo (sin cuentas ni correos)."""
    token = x_brasa_token.strip()
    if len(token) < 20:
        raise HTTPException(401, "Falta el identificador del dispositivo.")
    row = services(request).db.one("SELECT * FROM subscribers WHERE id = ?", (token,))
    if not row:
        raise HTTPException(401, "Dispositivo no registrado.")
    return row


def admin(request: Request, x_admin_token: str = Header(default="", alias="X-Admin-Token")) -> None:
    expected = services(request).settings.admin_token
    if not expected:
        raise HTTPException(503, "La moderación no está disponible en este servidor.")
    if not hmac.compare_digest(x_admin_token.strip(), expected):
        raise HTTPException(403, "Token de moderación inválido.")


class RateLimiter:
    """Límite simple por IP en memoria (suficiente para un servidor único)."""

    def __init__(self):
        self.hits: dict[tuple[str, str], deque] = defaultdict(deque)

    def check(self, request: Request, bucket: str, limit: int, window_s: int) -> None:
        ip = request.client.host if request.client else "?"
        now = time.monotonic()
        queue = self.hits[(bucket, ip)]
        while queue and queue[0] < now - window_s:
            queue.popleft()
        if len(queue) >= limit:
            raise HTTPException(429, "Demasiadas solicitudes. Intenta nuevamente en unos minutos.")
        queue.append(now)


limiter = RateLimiter()

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f<>]")


def clean_text(value: str) -> str:
    """Texto libre de personas (nombres de lugares, descripciones): sin caracteres de control ni < >.
    El front ya escapa todo al mostrarlo; esto evita guardar marcado que otro cliente pudiera interpretar."""
    return re.sub(r"\s+", " ", _CONTROL.sub("", value)).strip()


def dmc_item(row: Any) -> dict[str, Any]:
    """Una fila de `dmc_alerts` en la forma que consume la interfaz."""
    return {"kind": row["kind"], "label": dmc.KIND_LABELS.get(row["kind"], row["kind"]),
            "event": row["event"], "headline": row["headline"], "severity": row["severity"],
            "urgency": row["urgency"], "onset": row["onset"], "expires": row["expires"], "web": row["web"]}


def dmc_by_comuna(svc: Services) -> dict[str, list[dict[str, Any]]]:
    """Avisos de viento y calor vigentes, indexados por código de comuna (como texto, igual que el resto del mapa)."""
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in svc.db.query("SELECT * FROM dmc_alerts ORDER BY expires"):
        item = dmc_item(row)
        for code in json.loads(row["comunas"] or "[]"):
            out[str(code)].append(item)
    return dict(out)


def dmc_for_comuna(svc: Services, code: int | None) -> list[dict[str, Any]]:
    """Avisos que tocan una comuna concreta. Sin comuna (lugar fuera de Chile) no hay avisos."""
    if not code:
        return []
    return dmc_by_comuna(svc).get(str(code), [])


def dmc_source(svc: Services) -> dict[str, Any]:
    return {"name": dmc.SOURCE, "url": dmc.SOURCE_URL, "fetched_at": svc.db.kv_get("dmc_at"),
            "note": ("Avisos, alertas y alarmas oficiales de la DMC en CAP 1.2 (dominio público). BRASA muestra "
                     "solo los de viento y calor extremo, con las comunas que toca el polígono de cada zona.")}

"""Dispositivos, lugares, canales de alerta y bandeja de alertas. Sin cuentas: un token por dispositivo."""
from __future__ import annotations

import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from backend import alerts as alerts_mod
from backend.geo import bearing_deg, cardinal, haversine_km, is_upwind, territory
from backend.notify import telegram, webpush
from backend.providers import overpass
from backend.routes.common import limiter, services, subscriber
from backend.services import Services, stamp

router = APIRouter(prefix="/api")
CHILE_TZ = ZoneInfo("America/Santiago")
MAX_PLACES = 10
PLACE_KINDS = {"casa", "parcela", "familia", "trabajo", "colegio", "otro"}


class PlaceIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=60)
    kind: str = "casa"
    lat: float = Field(..., ge=-60, le=-17)
    lon: float = Field(..., ge=-110, le=-66)
    radius_km: float = Field(10, ge=1, le=50)


class PushIn(BaseModel):
    endpoint: str = Field(..., min_length=10, max_length=1000)
    keys: dict[str, str]


@router.post("/subscribers", status_code=201)
def create_subscriber(request: Request, svc: Services = Depends(services)):
    limiter.check(request, "subscribers", 20, 3600)
    token = secrets.token_urlsafe(24)
    svc.db.execute("INSERT INTO subscribers(id, created_at) VALUES (?, ?)", (token, stamp()))
    return {"token": token}


@router.get("/me")
def me(sub: dict = Depends(subscriber), svc: Services = Depends(services)):
    places = svc.db.query("SELECT COUNT(*) AS n FROM places WHERE subscriber_id = ?", (sub["id"],))[0]["n"]
    return {"push": bool(sub.get("push_endpoint")), "telegram": bool(sub.get("telegram_chat_id")), "places": places}


@router.get("/places")
def list_places(sub: dict = Depends(subscriber), svc: Services = Depends(services)):
    rows = svc.db.query("SELECT id, name, kind, lat, lon, radius_km, comuna_code, created_at FROM places WHERE subscriber_id = ? "
                        "ORDER BY created_at", (sub["id"],))
    by_code = territory().by_code
    for row in rows:
        comuna = by_code.get(row["comuna_code"])
        row["comuna"] = comuna.as_dict() if comuna else None
    return {"places": rows}


@router.post("/places", status_code=201)
def add_place(place: PlaceIn, sub: dict = Depends(subscriber), svc: Services = Depends(services)):
    count = svc.db.one("SELECT COUNT(*) AS n FROM places WHERE subscriber_id = ?", (sub["id"],))["n"]
    if count >= MAX_PLACES:
        raise HTTPException(422, f"Puedes guardar hasta {MAX_PLACES} lugares.")
    comuna = territory().locate(place.lat, place.lon)
    place_id = str(uuid.uuid4())
    svc.db.execute("INSERT INTO places(id, subscriber_id, name, kind, lat, lon, radius_km, comuna_code, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                   (place_id, sub["id"], place.name.strip(), place.kind if place.kind in PLACE_KINDS else "otro",
                    place.lat, place.lon, place.radius_km, comuna.code if comuna else None, stamp()))
    return {"id": place_id, "comuna": comuna.as_dict() if comuna else None}


@router.patch("/places/{place_id}")
def update_place(place_id: str, place: PlaceIn, sub: dict = Depends(subscriber), svc: Services = Depends(services)):
    comuna = territory().locate(place.lat, place.lon)
    changed = svc.db.execute("UPDATE places SET name = ?, kind = ?, lat = ?, lon = ?, radius_km = ?, comuna_code = ? "
                             "WHERE id = ? AND subscriber_id = ?",
                             (place.name.strip(), place.kind if place.kind in PLACE_KINDS else "otro", place.lat, place.lon,
                              place.radius_km, comuna.code if comuna else None, place_id, sub["id"]))
    if not changed:
        raise HTTPException(404, "Lugar no encontrado.")
    return {"ok": True}


@router.delete("/places/{place_id}")
def delete_place(place_id: str, sub: dict = Depends(subscriber), svc: Services = Depends(services)):
    if not svc.db.execute("DELETE FROM places WHERE id = ? AND subscriber_id = ?", (place_id, sub["id"])):
        raise HTTPException(404, "Lugar no encontrado.")
    return {"ok": True}


@router.get("/places/{place_id}/summary")
async def place_summary(place_id: str, sub: dict = Depends(subscriber), svc: Services = Depends(services)):
    """Todo lo que importa para un lugar: focos cercanos, viento, riesgo de hoy y de la semana, y dónde ir."""
    place = svc.db.one("SELECT * FROM places WHERE id = ? AND subscriber_id = ?", (place_id, sub["id"]))
    if not place:
        raise HTTPException(404, "Lugar no encontrado.")
    since = (datetime.now(timezone.utc) - timedelta(hours=48)).strftime("%Y-%m-%dT%H:%M:%SZ")
    span = place["radius_km"] * 2 / 111.0
    candidates = svc.db.query(
        "SELECT * FROM observations WHERE observed_at >= ? AND lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?",
        (since, place["lat"] - span, place["lat"] + span, place["lon"] - span * 1.4, place["lon"] + span * 1.4))
    wind = await svc.wind_at(place["lat"], place["lon"])
    nearby = []
    for obs in candidates:
        d = haversine_km(place["lat"], place["lon"], obs["lat"], obs["lon"])
        if d <= place["radius_km"] * 2:
            b = bearing_deg(place["lat"], place["lon"], obs["lat"], obs["lon"])
            nearby.append({**obs, "distance_km": round(d, 2), "bearing_deg": round(b), "direction": cardinal(b),
                           "inside_radius": d <= place["radius_km"], "reliable": alerts_mod.is_alertable(obs),
                           "upwind": is_upwind(b, (wind or {}).get("direction"), (wind or {}).get("speed"))})
    nearby.sort(key=lambda o: o["distance_km"])
    today = datetime.now(CHILE_TZ).date().isoformat()
    risk_days = svc.db.query("SELECT * FROM risk_daily WHERE comuna_code = ? AND date >= ? ORDER BY date LIMIT 7",
                             (place["comuna_code"], today)) if place["comuna_code"] else []
    inside = [o for o in nearby if o["inside_radius"] and o["reliable"]]
    if any(o["upwind"] for o in inside) or any(o["distance_km"] <= 2 for o in inside):
        status = "urgente"
    elif inside:
        status = "aviso"
    elif risk_days and risk_days[0]["level"] in {"alto", "extremo"}:
        status = "riesgo"
    else:
        status = "tranquilo"
    comuna = territory().by_code.get(place["comuna_code"]) if place["comuna_code"] else None
    return {"place": place, "comuna": comuna.as_dict() if comuna else None, "status": status, "wind": wind,
            "nearby": nearby[:50], "risk_days": risk_days, "data_as_of": svc.db.kv_get("last_ingest_at")}


@router.get("/nearby-services")
async def nearby_services(lat: float, lon: float, svc: Services = Depends(services)):
    """Puntos de encuentro, hospitales y cuarteles cercanos (OpenStreetMap)."""
    cache_key = f"overpass:{lat:.2f}:{lon:.2f}"
    cached = svc.db.cache_get(cache_key)
    if cached is None:
        try:
            cached = await overpass.nearby(svc.client, lat, lon)
        except overpass.OverpassError as exc:
            raise HTTPException(502, str(exc)) from None
        svc.db.cache_set(cache_key, cached, 86400)
    items = []
    for item in cached:
        d = haversine_km(lat, lon, item["lat"], item["lon"])
        b = bearing_deg(lat, lon, item["lat"], item["lon"])
        items.append({**item, "distance_km": round(d, 2), "direction": cardinal(b)})
    items.sort(key=lambda i: i["distance_km"])
    return {"source": "OpenStreetMap (Overpass)", "items": items,
            "note": "La cobertura de OSM es incompleta en zonas rurales. Los puntos de encuentro oficiales los define tu municipio."}


@router.post("/push/subscribe")
def push_subscribe(push: PushIn, sub: dict = Depends(subscriber), svc: Services = Depends(services)):
    if not push.endpoint.startswith("https://") or not push.keys.get("p256dh") or not push.keys.get("auth"):
        raise HTTPException(422, "Suscripción push inválida.")
    svc.db.execute("UPDATE subscribers SET push_endpoint = ?, push_p256dh = ?, push_auth = ? WHERE id = ?",
                   (push.endpoint, push.keys["p256dh"], push.keys["auth"], sub["id"]))
    return {"ok": True}


@router.delete("/push/subscribe")
def push_unsubscribe(sub: dict = Depends(subscriber), svc: Services = Depends(services)):
    svc.db.execute("UPDATE subscribers SET push_endpoint = NULL, push_p256dh = NULL, push_auth = NULL WHERE id = ?", (sub["id"],))
    return {"ok": True}


@router.post("/telegram/link")
def telegram_link(sub: dict = Depends(subscriber), svc: Services = Depends(services)):
    username = svc.settings.telegram_bot_username
    if not (svc.settings.telegram_bot_token and username):
        raise HTTPException(503, "Telegram no está configurado en este servidor.")
    code = secrets.token_urlsafe(12)
    svc.db.execute("UPDATE subscribers SET link_code = ? WHERE id = ?", (code, sub["id"]))
    return {"url": f"https://t.me/{username}?start={code}"}


@router.get("/alerts")
def inbox(sub: dict = Depends(subscriber), svc: Services = Depends(services)):
    rows = svc.db.query(
        "SELECT a.id, a.level, a.created_at, a.payload, a.delivered FROM alerts a JOIN places p ON p.id = a.place_id "
        "WHERE p.subscriber_id = ? ORDER BY a.created_at DESC LIMIT 100", (sub["id"],))
    return {"alerts": [{"id": r["id"], "level": r["level"], "created_at": r["created_at"],
                        "delivered": json.loads(r["delivered"]), **json.loads(r["payload"])} for r in rows]}


@router.post("/alerts/test")
async def test_alert(request: Request, sub: dict = Depends(subscriber), svc: Services = Depends(services)):
    """Envía una notificación de PRUEBA por los canales activos, para comprobar que llegan."""
    limiter.check(request, "test-alert", 5, 600)
    payload = {"title": "PRUEBA · BRASA Chile", "level": "prueba",
               "body": "Esta es una notificación de prueba. Si la ves, tus alertas por lugar funcionan en este canal.",
               "footer": alerts_mod.OFFICIAL_FOOTER, "url": "/#/mi-zona"}
    channels = []
    if sub.get("push_endpoint") and webpush.send(svc.db, sub, payload, svc.settings.vapid_contact):
        channels.append("push")
    if svc.settings.telegram_bot_token and sub.get("telegram_chat_id"):
        if await telegram.send_message(svc.client, svc.settings.telegram_bot_token, sub["telegram_chat_id"],
                                       f"🧪 {payload['title']}\n\n{payload['body']}"):
            channels.append("telegram")
    return {"channels": channels}

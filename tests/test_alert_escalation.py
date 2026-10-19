"""Escalamiento (ALR-10): un aviso urgente que sigue vigente se reenvía una sola vez.

Un aviso urgente no leído es un aviso perdido: pasados ~10 minutos, si sigue siendo el
más reciente del lugar se reenvía por los canales ya configurados (nunca más de dos
envíos por aviso). Los avisos no urgentes jamás se repiten, y un aviso más nuevo del
mismo lugar cancela el recordatorio: ese fue el que despertó a la persona.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest

from backend import alerts
from backend import services as services_mod
from backend.db import Database
from tests.conftest import json_response

NOW = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)


def place(db: Database) -> None:
    db.execute("INSERT INTO subscribers(id, created_at) VALUES ('s1','2026-01-01T00:00:00Z')")
    db.execute("INSERT INTO places(id, subscriber_id, name, kind, lat, lon, radius_km, created_at) "
               "VALUES ('p1','s1','Casa','casa',-33.05,-71.55,10,'2026-01-01T00:00:00Z')")


def insert_alert(svc, *, level: str = "urgente", minutes: int = 20, obs: str = "o1",
                 reminded: bool = False, place_id: str = "p1") -> None:
    """Deja una alerta ya entregada, como quedó tras su primer intento hace `minutes` minutos."""
    created = (NOW - timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = {"title": "Foco", "body": "cuerpo", "footer": "pie", "level": level, "url": "/#/mapa"}
    svc.db.execute("INSERT INTO alerts(place_id, observation_id, level, distance_km, bearing_deg, upwind, "
                   "lat, lon, observed_at, created_at, payload, delivered, delivered_at, reminded_at) "
                   "VALUES (?,?,?,1.0,0,0,-33.05,-71.55,?,?,?,'[\"telegram\"]',?,?)",
                   (place_id, obs, level, created, created, json.dumps(payload),
                    created, created if reminded else None))


def urgent_row(**fields) -> dict:
    """La fila que vería `escalation_due`: urgente, entregada hace 20 min, sin recordatorio."""
    stamp = (NOW - timedelta(minutes=20)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"level": "urgente", "created_at": stamp, "delivered_at": stamp,
            "reminded_at": None, **fields}


def test_a_recent_or_reminded_urgent_is_not_resent(make_client, web, monkeypatch):
    """(a) La espera de 10 min aún no cumple para una urgente de hace 5 min, y una
    urgente ya recordada jamás se repite: `reminded_at` es la vedada definitiva."""
    monkeypatch.setattr(services_mod, "utcnow", lambda: NOW)
    assert not alerts.escalation_due(
        urgent_row(created_at=(NOW - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")), False, NOW)
    assert not alerts.escalation_due(urgent_row(reminded_at=NOW.strftime("%Y-%m-%dT%H:%M:%SZ")), False, NOW)
    sent = []
    web.add(lambda r: "telegram" in r.url.host,
            lambda r: sent.append(r) or json_response({"ok": True, "result": {}}))
    with make_client(TELEGRAM_BOT_TOKEN="123:tok") as client:
        svc = client.app.state.services
        place(svc.db)
        svc.db.execute("UPDATE subscribers SET telegram_chat_id = '777' WHERE id = 's1'")
        insert_alert(svc, minutes=5)
        insert_alert(svc, minutes=60, obs="o2", reminded=True)
        asyncio.run(svc.deliver([]))
        assert sent == []


def test_a_newer_alert_for_the_place_cancels_the_reminder(make_client, web, monkeypatch):
    """(b) Si el lugar ya recibió otro aviso más nuevo, ese fue el que avisó:
    reenviar la urgente vieja sería ruido."""
    monkeypatch.setattr(services_mod, "utcnow", lambda: NOW)
    assert not alerts.escalation_due(urgent_row(), has_newer=True, now=NOW)
    sent = []
    web.add(lambda r: "telegram" in r.url.host,
            lambda r: sent.append(r) or json_response({"ok": True, "result": {}}))
    with make_client(TELEGRAM_BOT_TOKEN="123:tok") as client:
        svc = client.app.state.services
        place(svc.db)
        svc.db.execute("UPDATE subscribers SET telegram_chat_id = '777' WHERE id = 's1'")
        insert_alert(svc, minutes=20)                          # la urgente vieja
        insert_alert(svc, level="aviso", minutes=5, obs="o2")  # una más nueva del mismo lugar
        asyncio.run(svc.deliver([]))
        assert sent == []


def test_an_old_urgent_alert_is_resent_exactly_once(make_client, web, monkeypatch):
    """(c) Una urgente de hace 20 min sin sucesor se reenvía por los canales: una sola
    vez, con marca de recordatorio, y la segunda pasada no manda nada más."""
    monkeypatch.setattr(services_mod, "utcnow", lambda: NOW)
    assert alerts.escalation_due(urgent_row(), has_newer=False, now=NOW)
    sent = []
    web.add(lambda r: "telegram" in r.url.host,
            lambda r: sent.append(json.loads(r.content)) or json_response({"ok": True, "result": {}}))
    with make_client(TELEGRAM_BOT_TOKEN="123:tok") as client:
        svc = client.app.state.services
        place(svc.db)
        svc.db.execute("UPDATE subscribers SET telegram_chat_id = '777' WHERE id = 's1'")
        insert_alert(svc, minutes=20)
        asyncio.run(svc.deliver([]))
        assert len(sent) == 1 and "Recordatorio" in sent[0]["text"]
        assert svc.db.one("SELECT reminded_at FROM alerts")["reminded_at"]
        asyncio.run(svc.deliver([]))   # nunca un tercer envío
        assert len(sent) == 1


@pytest.mark.parametrize("level", ["aviso", "riesgo"])
def test_a_non_urgent_alert_never_escalates(make_client, web, monkeypatch, level):
    """(d) Un aviso que no es urgente, por viejo que sea y aunque nadie lo haya abierto,
    jamás se repite."""
    monkeypatch.setattr(services_mod, "utcnow", lambda: NOW)
    assert not alerts.escalation_due(urgent_row(level=level), has_newer=False, now=NOW)
    sent = []
    web.add(lambda r: "telegram" in r.url.host,
            lambda r: sent.append(r) or json_response({"ok": True, "result": {}}))
    with make_client(TELEGRAM_BOT_TOKEN="123:tok") as client:
        svc = client.app.state.services
        place(svc.db)
        svc.db.execute("UPDATE subscribers SET telegram_chat_id = '777' WHERE id = 's1'")
        insert_alert(svc, level=level, minutes=60)
        asyncio.run(svc.deliver([]))
        assert sent == []

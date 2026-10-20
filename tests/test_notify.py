"""Canales de aviso: Telegram y Web Push. Sin red real ni claves reales."""

from __future__ import annotations

import logging

import pytest
import requests

from backend.db import Database
from backend.notify import telegram, webpush


@pytest.fixture
def db(tmp_path) -> Database:
    return Database(tmp_path / "brasa.db")


def subscriber(db: Database, **fields) -> dict:
    db.execute("INSERT INTO subscribers(id, created_at) VALUES ('s1','2026-01-01T00:00:00Z')")
    for key, value in fields.items():
        db.execute(f"UPDATE subscribers SET {key} = ? WHERE id = 's1'", (value,))
    return db.one("SELECT * FROM subscribers WHERE id = 's1'")


# --- format_alert -----------------------------------------------------------

PAYLOAD = {
    "level": "urgente",
    "title": "Foco cerca de Casa",
    "body": "VIIRS detectó calor a 3 km.",
    "url": "/#/incendio/inc-1",
    "footer": "BRASA Chile",
}


def test_format_alert_incident_link_and_level():
    text = telegram.format_alert(PAYLOAD, "https://brasa.example")
    assert text.startswith("🔴 Foco cerca de Casa")
    assert "Ver el incidente: https://brasa.example/#/incendio/inc-1" in text
    assert text.endswith("BRASA Chile")


def test_format_alert_map_link_and_default_emoji():
    text = telegram.format_alert({**PAYLOAD, "level": "otro", "url": "/#mapa"}, "https://brasa.example")
    assert text.startswith("🟠 ")
    assert "Ver en el mapa: https://brasa.example/#mapa" in text


def test_format_alert_keeps_html_chars_verbatim():
    # sendMessage va sin parse_mode: el texto es plano y estos caracteres no son marcado.
    text = telegram.format_alert({**PAYLOAD, "title": "Foco <b>&amp;</b> raro"}, "https://brasa.example")
    assert "Foco <b>&amp;</b> raro" in text


@pytest.mark.xfail(reason="format_alert no recorta: Telegram rechaza textos de más de 4096 caracteres", strict=True)
def test_format_alert_truncates_at_4096():
    text = telegram.format_alert({**PAYLOAD, "body": "x" * 5000}, "https://brasa.example")
    assert len(text) <= 4096
    assert text.endswith("…")


# --- handle_update ----------------------------------------------------------


def test_update_without_message_or_text_returns_none(db):
    assert telegram.handle_update(db, {}) is None
    assert telegram.handle_update(db, {"message": {"chat": {"id": 7}, "photo": [{"file_id": "x"}]}}) is None


def test_start_with_unknown_code_falls_back_to_welcome(db):
    # Hoy no hay mensaje de «código inválido»: el enlace malo o vencido recibe la bienvenida.
    reply = telegram.handle_update(db, {"message": {"chat": {"id": 7}, "text": "/start no-existe"}})
    assert reply and "Bienvenido" in reply


def test_start_with_valid_code_links_chat_and_counts_places(db):
    subscriber(db, link_code="abc")
    db.execute(
        "INSERT INTO places(id, subscriber_id, name, kind, lat, lon, radius_km, created_at) "
        "VALUES ('p1','s1','Casa','casa',-35.43,-71.66,10,'2026-01-01T00:00:00Z')"
    )
    reply = telegram.handle_update(db, {"message": {"chat": {"id": 42}, "text": "/start abc"}})
    assert "1 lugar" in reply
    assert db.one("SELECT telegram_chat_id FROM subscribers WHERE id = 's1'")["telegram_chat_id"] == "42"


# --- webpush.send -----------------------------------------------------------


def push_subscriber(db: Database) -> dict:
    return subscriber(db, push_endpoint="https://push.example/sub/1", push_p256dh="pk", push_auth="auth")


def _webpush_error(status: int):
    from pywebpush import WebPushException

    response = requests.Response()
    response.status_code = status
    return WebPushException("rechazado", response=response)


@pytest.mark.parametrize("status", [404, 410])
def test_send_gone_subscription_returns_false_and_clears_endpoint(db, monkeypatch, status):
    sub = push_subscriber(db)
    monkeypatch.setattr("pywebpush.webpush", lambda **kw: (_ for _ in ()).throw(_webpush_error(status)))
    assert webpush.send(db, sub, {"title": "t"}, "mailto:a@b.c") is False
    row = db.one("SELECT push_endpoint, push_p256dh, push_auth FROM subscribers WHERE id = 's1'")
    assert row == {"push_endpoint": None, "push_p256dh": None, "push_auth": None}


@pytest.mark.parametrize(
    "level,urgency,ttl",
    [
        ("urgente", "high", 21600),
        ("aviso", "normal", 3600),
        (None, "normal", 3600),
    ],
)
def test_send_sets_urgency_header_and_ttl_by_level(db, monkeypatch, level, urgency, ttl):
    sub = push_subscriber(db)
    calls = []
    monkeypatch.setattr("pywebpush.webpush", lambda **kw: calls.append(kw))
    payload = {"title": "t"} | ({"level": level} if level else {})
    assert webpush.send(db, sub, payload, "mailto:a@b.c") is True
    assert calls[0]["headers"]["Urgency"] == urgency
    assert calls[0]["ttl"] == ttl


def test_send_returns_true_on_success(db, monkeypatch):
    sub = push_subscriber(db)
    calls = []
    monkeypatch.setattr("pywebpush.webpush", lambda **kw: calls.append(kw))
    assert webpush.send(db, sub, {"title": "t"}, "mailto:a@b.c") is True
    assert calls[0]["subscription_info"]["endpoint"] == "https://push.example/sub/1"


def test_send_without_endpoint_is_false(db, monkeypatch):
    sub = subscriber(db)
    monkeypatch.setattr("pywebpush.webpush", lambda **kw: pytest.fail("no debió intentar enviar"))
    assert webpush.send(db, sub, {}, "mailto:a@b.c") is False


def test_send_network_error_returns_false(db, monkeypatch):
    sub = push_subscriber(db)
    monkeypatch.setattr("pywebpush.webpush", lambda **kw: (_ for _ in ()).throw(requests.ConnectionError("sin red")))
    assert webpush.send(db, sub, {}, "mailto:a@b.c") is False


def test_send_corrupt_keys_returns_false(db, monkeypatch):
    sub = push_subscriber(db)
    monkeypatch.setattr("pywebpush.webpush", lambda **kw: (_ for _ in ()).throw(ValueError("clave corrupta")))
    assert webpush.send(db, sub, {}, "mailto:a@b.c") is False


# --- ensure_keys ------------------------------------------------------------


def test_ensure_keys_is_idempotent_and_private_stays_out_of_logs(db, caplog):
    with caplog.at_level(logging.DEBUG):
        private1, public1 = webpush.ensure_keys(db)
        private2, public2 = webpush.ensure_keys(db)
    assert (private1, public1) == (private2, public2)
    assert public1 and "PRIVATE KEY" in private1
    assert private1 not in caplog.text

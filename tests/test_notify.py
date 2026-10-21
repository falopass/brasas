"""Canal de aviso Telegram. Sin red real ni claves reales."""

from __future__ import annotations

import pytest

from backend.db import Database
from backend.notify import telegram


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

"""Web Push: envío y poda de suscripciones muertas. Sin red real ni claves reales."""

from __future__ import annotations

import logging
import sys

import pytest
import requests

from backend.db import Database
from backend.notify import webpush

COLUMNS = {"push_endpoint": "https://push.example/sub/1", "push_p256dh": "pk", "push_auth": "auth"}


@pytest.fixture
def db(tmp_path) -> Database:
    return Database(tmp_path / "brasa.db")


def subscriber(db: Database, **fields) -> dict:
    db.execute("INSERT INTO subscribers(id, created_at) VALUES ('s1','2026-01-01T00:00:00Z')")
    for key, value in fields.items():
        db.execute(f"UPDATE subscribers SET {key} = ? WHERE id = 's1'", (value,))
    return db.one("SELECT * FROM subscribers WHERE id = 's1'")


def push_subscriber(db: Database) -> dict:
    return subscriber(db, **COLUMNS)


def push_columns(db: Database) -> dict:
    return db.one("SELECT push_endpoint, push_p256dh, push_auth FROM subscribers WHERE id = 's1'")


def _webpush_exc(kind: str) -> Exception:
    from pywebpush import WebPushException

    if kind == "sin respuesta":
        return WebPushException("sin respuesta")
    if kind == "red":
        return requests.ConnectionError("sin red")
    if kind == "clave":
        return ValueError("clave corrupta")
    response = requests.Response()
    response.status_code = int(kind)
    return WebPushException("rechazado", response=response)


def _raise(exc: Exception):
    return lambda **kw: (_ for _ in ()).throw(exc)


@pytest.mark.parametrize("status", [404, 410])
def test_send_gone_subscription_returns_false_and_clears_columns(db, monkeypatch, status):
    sub = push_subscriber(db)
    monkeypatch.setattr("pywebpush.webpush", _raise(_webpush_exc(str(status))))
    assert webpush.send(db, sub, {"title": "t"}, "mailto:a@b.c") is False
    assert push_columns(db) == {"push_endpoint": None, "push_p256dh": None, "push_auth": None}


@pytest.mark.parametrize("kind", ["500", "429", "sin respuesta", "red", "clave"])
def test_send_error_returns_false_and_keeps_columns(db, monkeypatch, kind):
    sub = push_subscriber(db)
    monkeypatch.setattr("pywebpush.webpush", _raise(_webpush_exc(kind)))
    assert webpush.send(db, sub, {"title": "t"}, "mailto:a@b.c") is False
    assert push_columns(db) == COLUMNS


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


def test_send_returns_true_on_success_and_keeps_columns(db, monkeypatch):
    sub = push_subscriber(db)
    calls = []
    monkeypatch.setattr("pywebpush.webpush", lambda **kw: calls.append(kw))
    assert webpush.send(db, sub, {"title": "t"}, "mailto:a@b.c") is True
    assert calls[0]["subscription_info"] == {"endpoint": COLUMNS["push_endpoint"], "keys": {"p256dh": "pk", "auth": "auth"}}
    assert push_columns(db) == COLUMNS


def test_send_without_endpoint_is_false_and_does_not_touch_pywebpush(db, monkeypatch):
    # `None` en sys.modules hace que cualquier `import pywebpush` lance ImportError.
    sub = subscriber(db)
    monkeypatch.setitem(sys.modules, "pywebpush", None)
    assert webpush.send(db, sub, {}, "mailto:a@b.c") is False


def test_config_returns_503_when_push_dependency_missing(make_client, monkeypatch):
    monkeypatch.setitem(sys.modules, "py_vapid", None)
    with make_client() as client:
        response = client.get("/api/config")
    assert response.status_code == 503
    assert "push" in response.json()["detail"]


def test_ensure_keys_is_idempotent_and_private_stays_out_of_logs(db, caplog):
    with caplog.at_level(logging.DEBUG):
        private1, public1 = webpush.ensure_keys(db)
        private2, public2 = webpush.ensure_keys(db)
    assert (private1, public1) == (private2, public2)
    assert public1 and "PRIVATE KEY" in private1
    assert private1 not in caplog.text

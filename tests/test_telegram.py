"""Telegram 429: un solo reintento con espera acotada e inyectable. Sin red real."""

from __future__ import annotations

import asyncio
from datetime import datetime

import httpx
import pytest

from backend.db import Database
from backend.geo import territory
from backend.notify import telegram


@pytest.fixture
def db(tmp_path) -> Database:
    return Database(tmp_path / "brasa.db")


def client_returning(*payloads: dict) -> tuple[httpx.AsyncClient, list[httpx.Request]]:
    """Cliente sin red: responde los payloads en orden y registra cada llamada."""
    queue = list(payloads)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=queue.pop(0))

    return httpx.AsyncClient(transport=httpx.MockTransport(handler)), requests


class FakeSleep:
    def __init__(self) -> None:
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


def rate_limited(retry_after) -> dict:
    return {"ok": False, "error_code": 429, "description": "Too Many Requests: retry in N",
            "parameters": {"retry_after": retry_after}}


OK = {"ok": True, "result": {"message_id": 1}}


def test_429_sleeps_retry_after_and_second_attempt_delivers():
    client, requests = client_returning(rate_limited(3), OK)
    sleep = FakeSleep()
    assert asyncio.run(telegram.send_message(client, "tok", "42", "hola", sleep)) is True
    assert sleep.calls == [3] and len(requests) == 2


def test_429_twice_returns_false_after_a_single_retry():
    client, requests = client_returning(rate_limited(2), rate_limited(2))
    sleep = FakeSleep()
    assert asyncio.run(telegram.send_message(client, "tok", "42", "hola", sleep)) is False
    assert sleep.calls == [2] and len(requests) == 2


def test_400_neither_sleeps_nor_retries():
    client, requests = client_returning({"ok": False, "error_code": 400, "description": "chat not found"})
    sleep = FakeSleep()
    assert asyncio.run(telegram.send_message(client, "tok", "42", "hola", sleep)) is False
    assert sleep.calls == [] and len(requests) == 1


def test_429_sleeps_at_most_ten_seconds():
    client, requests = client_returning(rate_limited(600), OK)
    sleep = FakeSleep()
    assert asyncio.run(telegram.send_message(client, "tok", "42", "hola", sleep)) is True
    assert sleep.calls == [10] and len(requests) == 2


def test_429_without_retry_after_waits_one_second():
    client, _ = client_returning({"ok": False, "error_code": 429, "description": "Too Many Requests"}, OK)
    sleep = FakeSleep()
    assert asyncio.run(telegram.send_message(client, "tok", "42", "hola", sleep)) is True
    assert sleep.calls == [1]


# --- handle_update: /riesgo, /ayuda y el alta del suscriptor -----------------

TALCA = (-35.43, -71.66)  # el centro de Talca, igual que en test_firms


def chat_with_place(db: Database, lat: float = TALCA[0], lon: float = TALCA[1], chat_id: str = "7") -> str:
    """Da de alta al chat enviando una ubicación, igual que haría la persona en el bot."""
    reply = telegram.handle_update(db, {"message": {"chat": {"id": int(chat_id)}, "location": {"latitude": lat, "longitude": lon}}})
    assert reply
    return chat_id


def test_riesgo_sin_lugares_pide_agregar_uno(db):
    reply = telegram.handle_update(db, {"message": {"chat": {"id": 7}, "text": "/riesgo"}})
    assert reply and "Agrega un lugar" in reply


def test_riesgo_con_pronostico_nombra_comuna_nivel_y_valores(db):
    chat_with_place(db)
    comuna = territory().locate(*TALCA)
    assert comuna is not None
    today = datetime.now(telegram.CHILE_TZ).date().isoformat()
    db.execute(
        "INSERT INTO risk_daily(comuna_code, date, level, score, hours_3of3, hours_2of3, "
        "tmax, rhmin, windmax, computed_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (comuna.code, today, "alto", 90, 3, 5, 33.0, 22.0, 35.0, "2026-01-01T00:00:00Z"),
    )
    reply = telegram.handle_update(db, {"message": {"chat": {"id": 7}, "text": "/riesgo"}})
    assert comuna.name in reply and "ALTO" in reply
    assert "33" in reply and "22" in reply and "35" in reply


def test_riesgo_sin_pronostico_no_explota(db):
    chat_with_place(db)
    comuna = territory().locate(*TALCA)
    assert comuna is not None
    reply = telegram.handle_update(db, {"message": {"chat": {"id": 7}, "text": "/riesgo"}})
    assert comuna.name in reply and "sin pronóstico" in reply


@pytest.mark.parametrize("command", ["/ayuda", "/help"])
def test_ayuda_devuelve_el_texto_de_ayuda(db, command):
    reply = telegram.handle_update(db, {"message": {"chat": {"id": 7}, "text": command}})
    assert reply == telegram.HELP


def test_texto_cualquiera_devuelve_la_ayuda(db):
    # Comportamiento actual: cualquier texto que no es comando cae en la ayuda.
    assert telegram.handle_update(db, {"message": {"chat": {"id": 7}, "text": "hola"}}) == telegram.HELP


def test_subscriber_for_chat_es_idempotente(db):
    first = telegram.subscriber_for_chat(db, "99")
    second = telegram.subscriber_for_chat(db, "99")
    assert first["id"] == second["id"]
    assert db.one("SELECT COUNT(*) AS n FROM subscribers WHERE telegram_chat_id = '99'")["n"] == 1

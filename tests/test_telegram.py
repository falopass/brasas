"""Telegram 429: un solo reintento con espera acotada e inyectable. Sin red real."""
from __future__ import annotations

import asyncio

import httpx

from backend.notify import telegram


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

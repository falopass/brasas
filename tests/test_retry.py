"""Pruebas del reintento compartido de los proveedores (`providers/_retry`).

Sin red y sin esperas reales: `httpx.MockTransport` simula las respuestas y un
espía sobre `asyncio.sleep` registra las esperas en vez de dormir.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from backend.providers import _retry

URL = "https://ejemplo.cl/dato"


@pytest.fixture
def sleeps(monkeypatch):
    """Espía que reemplaza `asyncio.sleep` y anota cada espera pedida."""
    waits: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        waits.append(seconds)

    monkeypatch.setattr(_retry.asyncio, "sleep", fake_sleep)
    return waits


def run(coro):
    return asyncio.run(coro)


def client_for(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.parametrize("first", ["red", 500, 429], ids=["red", "500", "429"])
def test_reintenta_un_fallo_pasajero_y_devuelve_el_resultado(sleeps, first):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            if first == "red":
                raise httpx.ConnectError("se cayó la red", request=request)
            return httpx.Response(first)
        return httpx.Response(200, text="ok")

    async def go():
        async with client_for(handler) as client:
            return await _retry.get(client, URL)

    response = run(go())
    assert response.status_code == 200
    assert len(calls) == 2
    assert sleeps == [_retry.RETRY_DELAYS[0]]


def test_error_permanente_no_reintenta_y_propaga_con_contexto(sleeps):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(404, text="no existe")

    async def go():
        async with client_for(handler) as client:
            await _retry.get(client, URL)

    with pytest.raises(_retry.Failure) as excinfo:
        run(go())
    exc = excinfo.value
    assert exc.attempts == 1
    assert isinstance(exc.cause, httpx.HTTPStatusError)
    assert exc.cause.response.status_code == 404
    assert "1 intento" in exc.detail
    assert len(calls) == 1
    assert sleeps == []


@pytest.mark.parametrize("kind", ["503", "red", "custom"], ids=["503", "red", "delays"])
def test_agotar_los_intentos_propaga_failure(sleeps, kind):
    calls = []
    delays = (0.1,) if kind == "custom" else _retry.RETRY_DELAYS

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if kind == "red":
            raise httpx.ReadTimeout("timeout", request=request)
        return httpx.Response(503)

    async def go():
        async with client_for(handler) as client:
            if kind == "custom":
                await _retry.request(client, "GET", URL, delays=delays)
            else:
                await _retry.get(client, URL)

    with pytest.raises(_retry.Failure) as excinfo:
        run(go())
    total = len(delays) + 1
    assert excinfo.value.attempts == total
    assert len(calls) == total
    assert sleeps == list(delays)  # una espera por reintento, ninguna tras el último
    if kind == "red":
        assert isinstance(excinfo.value.cause, httpx.ReadTimeout)


@pytest.mark.parametrize(
    ("status", "headers", "wait"),
    [
        (429, {"Retry-After": "2"}, 2.0),
        (429, {"Retry-After": "120"}, _retry.MAX_RETRY_AFTER_S),
        (503, {"Retry-After": "1"}, 1.0),
        (429, {}, _retry.RETRY_DELAYS[0]),
        (429, {"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}, _retry.RETRY_DELAYS[0]),
    ],
    ids=["429-corta", "429-absurda", "503", "sin-cabecera", "fecha-http"],
)
def test_retry_after_se_respeta_y_se_acota(sleeps, status, headers, wait):
    """FIX-64: `Retry-After` gana sobre la espera fija, acotado al tope duro."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(status, headers=headers)
        return httpx.Response(200, text="ok")

    async def go():
        async with client_for(handler) as client:
            return await _retry.get(client, URL)

    assert run(go()).status_code == 200
    assert len(calls) == 2
    assert sleeps == [wait]

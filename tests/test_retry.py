"""Pruebas del reintento compartido de los proveedores (`providers/_retry`).

Sin red y sin esperas reales: `httpx.MockTransport` simula las respuestas y un
espía sobre `asyncio.sleep` registra las esperas en vez de dormir.
"""
from __future__ import annotations

import asyncio

import httpx
import pytest

from backend.providers import _retry


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


def test_reintenta_error_de_red_y_devuelve_el_resultado(sleeps):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            raise httpx.ConnectError("se cayó la red", request=request)
        return httpx.Response(200, text="ok")

    async def go():
        async with client_for(handler) as client:
            return await _retry.get(client, "https://ejemplo.cl/dato")

    response = run(go())
    assert response.status_code == 200
    assert len(calls) == 2
    assert sleeps == [_retry.RETRY_DELAYS[0]]


def test_reintenta_500_y_429(sleeps):
    for status in (500, 429):
        sleeps.clear()
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return httpx.Response(status if len(calls) == 1 else 200)

        async def go():
            async with client_for(handler) as client:
                return await _retry.get(client, "https://ejemplo.cl/dato")

        assert run(go()).status_code == 200
        assert len(calls) == 2
        assert sleeps == [_retry.RETRY_DELAYS[0]]


def test_error_permanente_no_reintenta_y_propaga_con_contexto(sleeps):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(404, text="no existe")

    async def go():
        async with client_for(handler) as client:
            await _retry.get(client, "https://ejemplo.cl/dato")

    with pytest.raises(_retry.Failure) as excinfo:
        run(go())
    exc = excinfo.value
    assert exc.attempts == 1
    assert isinstance(exc.cause, httpx.HTTPStatusError)
    assert exc.cause.response.status_code == 404
    assert "1 intento" in exc.detail
    assert len(calls) == 1
    assert sleeps == []


def test_respeta_el_maximo_de_intentos_y_las_esperas(sleeps):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(503)

    async def go():
        async with client_for(handler) as client:
            await _retry.get(client, "https://ejemplo.cl/dato")

    with pytest.raises(_retry.Failure) as excinfo:
        run(go())
    total = len(_retry.RETRY_DELAYS) + 1
    assert excinfo.value.attempts == total
    assert len(calls) == total
    # Una espera por reintento y ninguna después del último intento.
    assert sleeps == list(_retry.RETRY_DELAYS)


def test_error_de_red_agotado_propaga_failure(sleeps):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        raise httpx.ReadTimeout("timeout", request=request)

    async def go():
        async with client_for(handler) as client:
            await _retry.get(client, "https://ejemplo.cl/dato")

    with pytest.raises(_retry.Failure) as excinfo:
        run(go())
    assert excinfo.value.attempts == len(_retry.RETRY_DELAYS) + 1
    assert isinstance(excinfo.value.cause, httpx.ReadTimeout)
    assert sleeps == list(_retry.RETRY_DELAYS)


def test_esperas_personalizadas_se_respetan(sleeps):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(500)

    async def go():
        async with client_for(handler) as client:
            await _retry.request(client, "GET", "https://ejemplo.cl/dato", delays=(0.1,))

    with pytest.raises(_retry.Failure) as excinfo:
        run(go())
    assert excinfo.value.attempts == 2
    assert len(calls) == 2
    assert sleeps == [0.1]


def test_un_429_con_retry_after_espera_lo_que_pide_el_servidor(sleeps):
    """FIX-64: `Retry-After: 2` gana sobre la espera fija de 0,5 s."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "2"})
        return httpx.Response(200, text="ok")

    async def go():
        async with client_for(handler) as client:
            return await _retry.get(client, "https://ejemplo.cl/dato")

    assert run(go()).status_code == 200
    assert len(calls) == 2
    assert sleeps == [2.0]


def test_un_retry_after_absurdo_espera_el_tope_no_lo_pedido(sleeps):
    """FIX-64: `Retry-After: 120` se acota al tope duro (10 s), no congela el ciclo."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "120"})
        return httpx.Response(200, text="ok")

    async def go():
        async with client_for(handler) as client:
            return await _retry.get(client, "https://ejemplo.cl/dato")

    assert run(go()).status_code == 200
    assert sleeps == [_retry.MAX_RETRY_AFTER_S]


def test_un_503_con_retry_after_lo_respeta(sleeps):
    """FIX-64: el 503 también admite la cabecera."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(503, headers={"Retry-After": "1"})
        return httpx.Response(200, text="ok")

    async def go():
        async with client_for(handler) as client:
            return await _retry.get(client, "https://ejemplo.cl/dato")

    assert run(go()).status_code == 200
    assert sleeps == [1.0]


def test_un_429_sin_retry_after_espera_lo_de_siempre(sleeps):
    """Sin la cabecera (o con una fecha HTTP ilegible como número) manda la espera fija."""
    for headers in ({}, {"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}):
        sleeps.clear()
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            if len(calls) == 1:
                return httpx.Response(429, headers=headers)
            return httpx.Response(200, text="ok")

        async def go():
            async with client_for(handler) as client:
                return await _retry.get(client, "https://ejemplo.cl/dato")

        assert run(go()).status_code == 200
        assert sleeps == [_retry.RETRY_DELAYS[0]]

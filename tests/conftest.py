from __future__ import annotations

import json
from typing import Callable

import httpx
import pytest
from fastapi.testclient import TestClient

ENV_KEYS = [
    "FIRMS_MAP_KEY",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_BOT_USERNAME",
    "ADMIN_TOKEN",
    "CESIUM_ION_PUBLIC_TOKEN",
    "FIRMS_SOURCES",
    "TURNSTILE_SITE_KEY",
    "TURNSTILE_SECRET",
    "CONAF_PERIMETRO_ENABLED",
]


class FakeWeb:
    """Router de respuestas HTTP simuladas por host/ruta. Registra cada solicitud."""

    def __init__(self):
        self.routes: list[tuple[Callable[[httpx.Request], bool], Callable[[httpx.Request], httpx.Response]]] = []
        self.requests: list[httpx.Request] = []

    def add(self, match: Callable[[httpx.Request], bool], respond: Callable[[httpx.Request], httpx.Response]) -> None:
        self.routes.append((match, respond))

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        for match, respond in self.routes:
            if match(request):
                return respond(request)
        return httpx.Response(503, text="sin ruta simulada")


@pytest.fixture
def web() -> FakeWeb:
    return FakeWeb()


@pytest.fixture
def make_client(monkeypatch, tmp_path, web):
    """Crea un TestClient con base de datos temporal, sin tareas automáticas y con HTTP simulado."""
    from backend import main

    def factory(**env: str) -> TestClient:
        for key in ENV_KEYS:
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("BRASA_SCHEDULER", "0")
        monkeypatch.setenv("BRASA_DATA_DIR", str(tmp_path / "data"))
        # El limitador por IP y el cupo de Open-Meteo viven en memoria del proceso: cada
        # cliente es una app nueva y no debe heredar las llamadas de las pruebas anteriores.
        from backend.providers import weather
        from backend.routes.common import limiter

        limiter.hits.clear()
        weather._calls.update(since=None, day=None, calls=0, locations=0, by_endpoint={}, by_endpoint_locations={}, rate_limited=0)
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        monkeypatch.setattr(main, "HTTP_TRANSPORT", httpx.MockTransport(web.handler))
        return TestClient(main.app)

    return factory


def json_response(payload) -> httpx.Response:
    return httpx.Response(200, content=json.dumps(payload).encode(), headers={"content-type": "application/json"})


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "silencio_real: la prueba ejercita el silencio nocturno (ALR-19) a través de `deliver`; "
        "sin esta marca el fixture `silencio_nocturno_apagado` lo fija en «no».",
    )


@pytest.fixture(autouse=True)
def silencio_nocturno_apagado(request, monkeypatch):
    """ALR-19: `Services.deliver` consulta `en_silencio(utcnow())` con el reloj real, así que toda
    prueba que pasa por `deliver` (ingest_dmc, ingest_cycle, daily_brief, reintentos) dependía de
    la hora en que corrió la suite: entre 23:00 y 07:00 de Chile el «aviso» se aplazaba y
    `delivered_at` quedaba nulo. Aquí el silencio queda en «no» para que la hora no importe.
    Una prueba que sí ejercita el aplazo se marca `@pytest.mark.silencio_real` y fija su propio
    reloj (`services.utcnow`); las que importan `en_silencio` directo (test_alert_quiet_hours)
    conservan la función real porque este parche solo toca el atributo del módulo."""
    if request.node.get_closest_marker("silencio_real"):
        return
    from backend import alerts as alerts_mod

    monkeypatch.setattr(alerts_mod, "en_silencio", lambda now: False)


@pytest.fixture(autouse=True)
def reintentos_sin_espera(monkeypatch):
    """Los reintentos HTTP (backend/providers/_retry.py) cuentan intentos igual, pero sin dormir:
    con las esperas reales (0,5-4 s por reintento) la suite pasaba ~40 % de su tiempo esperando.
    Un test que necesite medir las esperas las vuelve a fijar con su propio monkeypatch."""
    from backend import storage
    from backend.providers import _retry, overpass
    monkeypatch.setattr(_retry, "RETRY_DELAYS", tuple(0 for _ in _retry.RETRY_DELAYS))
    monkeypatch.setattr(storage, "STORAGE_DELAYS", tuple(0 for _ in storage.STORAGE_DELAYS))
    monkeypatch.setattr(overpass, "WAITS_S", tuple(0 for _ in overpass.WAITS_S))

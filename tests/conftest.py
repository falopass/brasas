from __future__ import annotations

import json
from typing import Callable

import httpx
import pytest
from fastapi.testclient import TestClient

ENV_KEYS = ["FIRMS_MAP_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_BOT_USERNAME", "ADMIN_TOKEN", "CESIUM_ION_PUBLIC_TOKEN", "FIRMS_SOURCES"]


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
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        monkeypatch.setattr(main, "HTTP_TRANSPORT", httpx.MockTransport(web.handler))
        return TestClient(main.app)

    return factory


def json_response(payload) -> httpx.Response:
    return httpx.Response(200, content=json.dumps(payload).encode(), headers={"content-type": "application/json"})

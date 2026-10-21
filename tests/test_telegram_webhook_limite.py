"""Tope de cuerpo en POST /api/telegram/webhook (SEC-208).

La ruta es pública: solo la protege `X-Telegram-Bot-Api-Secret-Token`, y antes leía
`request.json()` sin mirar el tamaño. Ahora: el secreto se revisa primero (403), un
cuerpo de más de 1 MiB responde 413 sin procesarse y un JSON inválido responde 400.
"""

from __future__ import annotations

from backend.notify import telegram

SECRET = "hook-secret-xyz"
TG = {"X-Telegram-Bot-Api-Secret-Token": SECRET}
BIG = b"x" * (2 * 1024 * 1024)  # 2 MB, sobre TELEGRAM_MAX_BODY
UPDATE = {"message": {"chat": {"id": 99}, "text": "/ayuda"}}


def _client(make_client):
    return make_client(INTERNAL_TOKEN="", BRASA_STORAGE_URL="", TELEGRAM_WEBHOOK_SECRET=SECRET)


def _spy(client, monkeypatch) -> list:
    """Registra las llamadas a handle_update para probar que el cuerpo no se procesó."""
    calls: list = []
    monkeypatch.setattr(telegram, "handle_update", lambda db, update: calls.append(update) or None)
    return calls


def test_cuerpo_enorme_con_secreto_responde_413_sin_procesar(make_client, monkeypatch):
    with _client(make_client) as client:
        calls = _spy(client, monkeypatch)
        r = client.post("/api/telegram/webhook", content=BIG, headers=TG)
        assert r.status_code == 413
        assert r.json() == {"detail": "Cuerpo demasiado grande."}
        assert calls == []


def test_cuerpo_enorme_sin_secreto_responde_403(make_client):
    """El secreto se revisa antes que el tamaño: sin él ni siquiera se mira el cuerpo."""
    with _client(make_client) as client:
        assert client.post("/api/telegram/webhook", content=BIG).status_code == 403


def test_json_invalido_responde_400_no_500(make_client, monkeypatch):
    with _client(make_client) as client:
        calls = _spy(client, monkeypatch)
        r = client.post("/api/telegram/webhook", content=b"{no es json", headers=TG)
        assert r.status_code == 400
        assert r.json() == {"detail": "Cuerpo inválido."}
        assert calls == []


def test_update_valido_responde_ok(make_client):
    with _client(make_client) as client:
        r = client.post("/api/telegram/webhook", json=UPDATE, headers=TG)
        assert r.status_code == 200 and r.json() == {"ok": True}

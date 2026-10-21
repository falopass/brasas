"""Contrato de /api/internal/* y del webhook de Telegram.

Lo usan el Cron Trigger de Cloudflare y los respaldos. El contrato que se fija aquí:
sin el INTERNAL_TOKEN correcto las rutas responden 404 (nunca 401, para no delatar
que existen), y si INTERNAL_TOKEN no está definido la ruta se comporta como inexistente;
`tick` contesta 202 de inmediato y corre el ciclo en segundo plano (el cron corta a los
~30 s), mientras `?wait=1` espera y devuelve el resultado; `backup` responde 409 cuando
no hay almacenamiento remoto; y el webhook exige `X-Telegram-Bot-Api-Secret-Token`.
"""

TOKEN = "internal-secret-1234567890"
SECRET = "hook-secret-xyz"
AUTH = {"X-Internal-Token": TOKEN}
TG_SECRET = {"X-Telegram-Bot-Api-Secret-Token": SECRET}


def _client(make_client, **env):
    """TestClient con token interno definido y sin almacenamiento ni secreto de Telegram,
    salvo que la prueba los pida (así el entorno de la máquina no cambia el resultado)."""
    base = {"INTERNAL_TOKEN": TOKEN, "BRASA_STORAGE_URL": "", "TELEGRAM_WEBHOOK_SECRET": ""}
    return make_client(**{**base, **env})


def _stub_cycle(client):
    """Simula `start_tick` y `tick_and_backup`: las pruebas no corren el ciclo real."""
    svc = client.app.state.services
    calls = {"started": 0, "cycles": 0}

    def start():
        calls["started"] += 1
        return True

    async def cycle():
        calls["cycles"] += 1
        return {"firms_new": 3, "alerts": 0}

    svc.start_tick = start
    svc.tick_and_backup = cycle
    return calls


def test_sin_cabecera_el_tick_responde_404(make_client):
    with _client(make_client) as client:
        assert client.post("/api/internal/tick").status_code == 404


def test_con_token_equivocado_responde_404(make_client):
    with _client(make_client) as client:
        mal = {"X-Internal-Token": "casi-" + TOKEN}
        assert client.post("/api/internal/tick", headers=mal).status_code == 404
        assert client.post("/api/internal/backup", headers=mal).status_code == 404


def test_sin_internal_token_configurado_la_ruta_no_existe(make_client):
    """Con INTERNAL_TOKEN vacío ningún token sirve: la ruta se comporta como inexistente."""
    with _client(make_client, INTERNAL_TOKEN="") as client:
        assert client.post("/api/internal/tick", headers=AUTH).status_code == 404
        assert client.post("/api/internal/backup", headers=AUTH).status_code == 404


def test_tick_responde_202_y_arranca_el_ciclo_sin_esperar(make_client):
    with _client(make_client) as client:
        calls = _stub_cycle(client)
        r = client.post("/api/internal/tick", headers=AUTH)
        assert r.status_code == 202
        assert r.json() == {"started": True, "last_cycle": None}
        assert calls == {"started": 1, "cycles": 0}  # no esperó el ciclo


def test_tick_con_wait_devuelve_el_resultado_del_ciclo(make_client):
    with _client(make_client) as client:
        calls = _stub_cycle(client)
        r = client.post("/api/internal/tick?wait=1", headers=AUTH)
        assert r.status_code == 200
        assert r.json() == {"firms_new": 3, "alerts": 0}
        assert calls == {"started": 0, "cycles": 1}


def test_backup_sin_almacenamiento_responde_409(make_client):
    with _client(make_client) as client:
        r = client.post("/api/internal/backup", headers=AUTH)
        assert r.status_code == 409


def test_webhook_con_secreto_invalido_responde_403(make_client):
    with _client(make_client, TELEGRAM_WEBHOOK_SECRET=SECRET) as client:
        update = {"message": {"chat": {"id": 99}, "text": "/ayuda"}}
        assert client.post("/api/telegram/webhook", json=update).status_code == 403
        r = client.post("/api/telegram/webhook", json=update, headers={"X-Telegram-Bot-Api-Secret-Token": "otro"})
        assert r.status_code == 403


def test_webhook_sin_secreto_configurado_responde_403(make_client):
    with _client(make_client) as client:
        assert client.post("/api/telegram/webhook", json={}, headers=TG_SECRET).status_code == 403


def test_webhook_con_secreto_valido_responde_ok(make_client):
    with _client(make_client, TELEGRAM_WEBHOOK_SECRET=SECRET) as client:
        r = client.post("/api/telegram/webhook", json={}, headers=TG_SECRET)
        assert r.status_code == 200 and r.json() == {"ok": True}


def test_los_errores_no_revelan_el_token_ni_la_ruta(make_client):
    """Una respuesta de error no debe repetir el token esperado ni nombrar la ruta real."""
    with _client(make_client, TELEGRAM_WEBHOOK_SECRET=SECRET) as client:
        respuestas = [
            client.post("/api/internal/tick"),
            client.post("/api/internal/tick", headers={"X-Internal-Token": "casi-" + TOKEN}),
            client.post("/api/internal/backup"),
            client.post("/api/telegram/webhook", json={}),
        ]
    for r in respuestas:
        assert r.status_code in (403, 404)
        assert TOKEN not in r.text and SECRET not in r.text
        assert "internal" not in r.text.lower() and "telegram" not in r.text.lower()

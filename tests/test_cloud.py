"""Modo Cloudflare: respaldo en almacenamiento remoto, reinicio del contenedor, cron y webhook de Telegram."""
import io
import json
import time

import httpx
from fastapi.testclient import TestClient
from PIL import Image

from tests.conftest import json_response

STORAGE = "http://storage.brasa"


def fake_storage(web, bucket: dict):
    def handler(request: httpx.Request) -> httpx.Response:
        # Igual que el Worker: sin el INTERNAL_TOKEN correcto, 403 (nunca 404, que parecería «no hay respaldo»).
        if request.headers.get("X-Internal-Token") != "internal-secret-1234567890":
            return httpx.Response(403)
        key = request.url.path.lstrip("/")
        if request.method == "PUT":
            bucket[key] = request.content
            return httpx.Response(200)
        if key in bucket:
            return httpx.Response(200, content=bucket[key])
        return httpx.Response(404)
    web.add(lambda r: r.url.host == "storage.brasa", handler)


def cloud_client(monkeypatch, tmp_path, web, data_dir: str, **env) -> TestClient:
    from backend import main
    for key in ["FIRMS_MAP_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_BOT_USERNAME", "ADMIN_TOKEN", "TELEGRAM_WEBHOOK_SECRET"]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("BRASA_SCHEDULER", "0")
    monkeypatch.setenv("BRASA_DATA_DIR", str(tmp_path / data_dir))
    monkeypatch.setenv("BRASA_STORAGE_URL", STORAGE)
    monkeypatch.setenv("INTERNAL_TOKEN", "internal-secret-1234567890")
    monkeypatch.setenv("GOES_ENABLED", "0")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(main, "HTTP_TRANSPORT", httpx.MockTransport(web.handler))
    return TestClient(main.app)


def wait_for(predicate, timeout=8.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.1)
    return False


def test_user_data_survives_container_restart(monkeypatch, tmp_path, web):
    bucket: dict[str, bytes] = {}
    fake_storage(web, bucket)
    with cloud_client(monkeypatch, tmp_path, web, "disk1") as client:
        client.app.state.services.persistence.debounce_s = 0.05
        token = client.post("/api/subscribers").json()["token"]
        headers = {"X-Brasa-Token": token}
        client.post("/api/places", json={"name": "Casa", "lat": -33.03, "lon": -71.53}, headers=headers)
        public_key = client.get("/api/config").json()["push"]["public_key"]
        assert wait_for(lambda: "db/brasa.db" in bucket)
    # «Reinicio»: disco nuevo y vacío, mismo R2.
    with cloud_client(monkeypatch, tmp_path, web, "disk2") as client:
        places = client.get("/api/places", headers=headers).json()["places"]
        assert [p["name"] for p in places] == ["Casa"]
        assert client.get("/api/config").json()["push"]["public_key"] == public_key  # las suscripciones push siguen válidas
    assert bucket["db/brasa.db"].startswith(b"SQLite format 3")


def test_backup_contains_only_user_data(monkeypatch, tmp_path, web):
    bucket: dict[str, bytes] = {}
    fake_storage(web, bucket)
    with cloud_client(monkeypatch, tmp_path, web, "disk") as client:
        svc = client.app.state.services
        svc.db.execute("INSERT INTO cache(key, expires_at, payload) VALUES ('x', 9e12, '\"y\"')")
        snapshot = svc.db.snapshot()
    import sqlite3
    path = tmp_path / "snap.db"
    path.write_bytes(snapshot)
    tables = {r[0] for r in sqlite3.connect(path).execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"subscribers", "places", "alerts", "reports", "kv"} <= tables
    assert not tables & {"observations", "cache", "risk_daily", "ingest_runs"}


def test_report_photo_restored_from_storage(monkeypatch, tmp_path, web):
    bucket: dict[str, bytes] = {}
    fake_storage(web, bucket)
    buf = io.BytesIO()
    Image.new("RGB", (40, 30), (90, 90, 90)).save(buf, "JPEG")
    admin = {"X-Admin-Token": "admin-token-abcdefghij"}
    with cloud_client(monkeypatch, tmp_path, web, "d1", ADMIN_TOKEN="admin-token-abcdefghij") as client:
        client.app.state.services.persistence.debounce_s = 0.05
        rid = client.post("/api/reports", data={"lat": "-33.05", "lon": "-71.5", "kind": "humo"},
                          files={"photo": ("a.jpg", buf.getvalue(), "image/jpeg")}).json()["id"]
        assert f"photos/{rid}.jpg" in bucket
        assert wait_for(lambda: "db/brasa.db" in bucket)
    with cloud_client(monkeypatch, tmp_path, web, "d2", ADMIN_TOKEN="admin-token-abcdefghij") as client:
        photo = client.get(f"/api/reports/{rid}/photo", headers=admin)
        assert photo.status_code == 200 and photo.content.startswith(b"\xff\xd8")


def test_internal_tick_requires_token_and_backs_up(monkeypatch, tmp_path, web):
    bucket: dict[str, bytes] = {}
    fake_storage(web, bucket)
    web.add(lambda r: "open-meteo" in r.url.host, lambda r: httpx.Response(503))
    with cloud_client(monkeypatch, tmp_path, web, "disk") as client:
        assert client.post("/api/internal/tick").status_code == 404
        assert client.post("/api/internal/tick", headers={"X-Internal-Token": "nope"}).status_code == 404
        r = client.post("/api/internal/tick?wait=1", headers={"X-Internal-Token": "internal-secret-1234567890"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["backup"] is True and "risk_error" in body and body["alerts"] == 0
        assert "db/brasa.db" in bucket


def test_cron_tick_runs_in_background(monkeypatch, tmp_path, web):
    """El cron solo dispara el ciclo: la respuesta llega al tiro y el ciclo termina después."""
    bucket: dict[str, bytes] = {}
    fake_storage(web, bucket)
    web.add(lambda r: "open-meteo" in r.url.host, lambda r: httpx.Response(503))
    headers = {"X-Internal-Token": "internal-secret-1234567890"}
    with cloud_client(monkeypatch, tmp_path, web, "disk") as client:
        r = client.post("/api/internal/tick", headers=headers)
        assert r.status_code == 202 and r.json()["started"] is True
        assert wait_for(lambda: (client.get("/api/status").json().get("last_cycle") or {}).get("finished_at"))
        status = client.get("/api/status").json()
        assert status["last_ingest_at"] and status["last_cycle"]["backup"] is True
        assert "risk_error" in status["last_cycle"]


def test_telegram_webhook_mode(monkeypatch, tmp_path, web):
    bucket: dict[str, bytes] = {}
    fake_storage(web, bucket)
    calls = []

    def telegram(request: httpx.Request) -> httpx.Response:
        calls.append((request.url.path.rsplit("/", 1)[-1], json.loads(request.content)))
        return json_response({"ok": True, "result": True})

    web.add(lambda r: "telegram" in r.url.host, telegram)
    env = {"TELEGRAM_BOT_TOKEN": "1:abc", "TELEGRAM_BOT_USERNAME": "b", "TELEGRAM_WEBHOOK_SECRET": "hook-secret-xyz",
           "PUBLIC_BASE_URL": "https://brasa.example.workers.dev"}
    with cloud_client(monkeypatch, tmp_path, web, "disk", **env) as client:
        assert calls[0][0] == "setWebhook"
        assert calls[0][1]["url"] == "https://brasa.example.workers.dev/api/telegram/webhook"
        assert calls[0][1]["secret_token"] == "hook-secret-xyz"
        update = {"message": {"chat": {"id": 99}, "location": {"latitude": -35.43, "longitude": -71.66}}}
        assert client.post("/api/telegram/webhook", json=update).status_code == 403
        r = client.post("/api/telegram/webhook", json=update, headers={"X-Telegram-Bot-Api-Secret-Token": "hook-secret-xyz"})
        assert r.status_code == 200
        assert calls[-1][0] == "sendMessage" and "Talca" in calls[-1][1]["text"]
        assert not any(name == "getUpdates" for name, _ in calls)  # sin long polling en modo webhook


def test_unreachable_storage_never_overwrites_backup(monkeypatch, tmp_path, web):
    bucket = {"db/brasa.db": b"BUENO"}
    state = {"down": True}

    def handler(request: httpx.Request) -> httpx.Response:
        if state["down"]:
            return httpx.Response(503)
        key = request.url.path.lstrip("/")
        if request.method == "PUT":
            bucket[key] = request.content
            return httpx.Response(200)
        return httpx.Response(200, content=bucket[key]) if key in bucket else httpx.Response(404)

    web.add(lambda r: r.url.host == "storage.brasa", handler)
    web.add(lambda r: "open-meteo" in r.url.host, lambda r: httpx.Response(503))
    with cloud_client(monkeypatch, tmp_path, web, "disk") as client:
        client.post("/api/subscribers")
        time.sleep(0.5)
        r = client.post("/api/internal/tick?wait=1", headers={"X-Internal-Token": "internal-secret-1234567890"}).json()
        assert r["backup"] is False and "restore_error" in r
        assert bucket["db/brasa.db"] == b"BUENO"


def test_public_url_learned_from_first_https_visit(monkeypatch, tmp_path, web):
    bucket: dict[str, bytes] = {}
    fake_storage(web, bucket)
    calls = []
    web.add(lambda r: "telegram" in r.url.host, lambda r: calls.append(json.loads(r.content)) or json_response({"ok": True, "result": True}))
    env = {"TELEGRAM_BOT_TOKEN": "1:abc", "TELEGRAM_BOT_USERNAME": "b", "TELEGRAM_WEBHOOK_SECRET": "s3cret", "PUBLIC_BASE_URL": ""}
    with cloud_client(monkeypatch, tmp_path, web, "disk", **env) as client:
        assert calls == []  # sin dirección pública aún, no se registra
        client.get("/api/health", headers={"X-Forwarded-Proto": "https", "Host": "brasa-chile.ejemplo.workers.dev"})
        client.get("/api/health", headers={"Host": "backend"})  # el cron interno no cuenta
    assert calls and calls[0]["url"] == "https://brasa-chile.ejemplo.workers.dev/api/telegram/webhook"


def test_legacy_single_file_database_is_migrated(tmp_path):
    """Una base v0.2 con todo en brasa.db (y la FK observations → ingest_runs) debe abrir sin perder datos de personas."""
    import sqlite3
    from backend.db import Database
    path = tmp_path / "brasa.db"
    conn = sqlite3.connect(path)
    conn.executescript("""
        PRAGMA foreign_keys = ON;
        CREATE TABLE ingest_runs (id INTEGER PRIMARY KEY, provider TEXT, product TEXT, started_at TEXT);
        CREATE TABLE observations (id TEXT PRIMARY KEY, run_id INTEGER REFERENCES ingest_runs(id), lat REAL, lon REAL);
        CREATE TABLE subscribers (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, push_endpoint TEXT, push_p256dh TEXT,
                                  push_auth TEXT, telegram_chat_id TEXT, link_code TEXT UNIQUE);
        INSERT INTO ingest_runs VALUES (1, 'NOAA GOES', 'GOES19_FDCF', 'x');
        INSERT INTO observations VALUES ('o1', 1, -33.0, -71.5);
        INSERT INTO subscribers(id, created_at) VALUES ('persona-que-no-se-pierde', 'x');
    """)
    conn.commit(); conn.close()
    db = Database(path)
    assert db.one("SELECT id FROM subscribers")["id"] == "persona-que-no-se-pierde"
    assert db.one("SELECT COUNT(*) AS n FROM observations")["n"] == 0  # ahora en work.db, se reconstruye
    assert db.one("SELECT name FROM main.sqlite_master WHERE name = 'observations'") is None


def test_a_restored_work_database_from_an_older_version_gets_the_new_columns(tmp_path):
    """Regresión: el work.db de R2 puede no tener las columnas nuevas y el riesgo las lee al servir."""
    import sqlite3
    from backend.db import Database

    old = tmp_path / "resource_work_backup.db"
    conn = sqlite3.connect(old)
    conn.executescript("""
        CREATE TABLE risk_daily (comuna_code INTEGER NOT NULL, date TEXT NOT NULL, level TEXT NOT NULL,
          score INTEGER NOT NULL, hours_3of3 INTEGER NOT NULL, hours_2of3 INTEGER NOT NULL,
          tmax REAL, rhmin REAL, windmax REAL, gustmax REAL, computed_at TEXT NOT NULL,
          PRIMARY KEY (comuna_code, date));
        INSERT INTO risk_daily VALUES (5109, '2026-10-18', 'alto', 90, 3, 5, 33.0, 22.0, 35.0, 60.0, 'x');
    """)
    conn.commit(); conn.close()

    db = Database(tmp_path / "data" / "brasa.db")
    db.restore_work(old.read_bytes())
    columns = {row["name"] for row in db.query("PRAGMA work.table_info(risk_daily)")}
    assert {"level_combined", "fwi", "fwi_level", "reasons"} <= columns
    assert db.one("SELECT level FROM risk_daily")["level"] == "alto"  # los datos no se tocan

"""OPS-14: /api/status publica un resumen de errores de la ingesta, sin datos personales."""

import asyncio
import json
import time
from datetime import timedelta

from backend.providers import firms
from backend.services import stamp, utcnow

ERROR_KEYS = {"window_h", "by_product", "cycle_errors"}
PRODUCT_KEYS = {"runs", "failed", "last_failed_at"}


def seed_run(db, product: str, hours_ago: float, ok: bool, message: str = "detalle que no debe publicarse") -> str:
    started = stamp(utcnow() - timedelta(hours=hours_ago))
    db.execute(
        "INSERT INTO ingest_runs(provider, product, started_at, finished_at, ok, n_records, n_new, message) VALUES (?,?,?,?,?,?,?,?)",
        ("prueba", product, started, started, int(ok), 0, 0, message),
    )
    return started


def test_error_summary_counts_by_product_and_window(make_client):
    with make_client() as client:
        db = client.app.state.services.db
        seed_run(db, "VIIRS", 1, True)
        last_fail = seed_run(db, "VIIRS", 2, False)
        seed_run(db, "VIIRS", 30, False)  # fuera de la ventana de 24 h: no cuenta
        goes_fail = seed_run(db, "GOES-19", 3, False)

        body = client.get("/api/status").json()
        errors = body["errors"]
        assert errors["window_h"] == 24
        assert errors["by_product"] == {
            "GOES-19": {"runs": 1, "failed": 1, "last_failed_at": goes_fail},
            "VIIRS": {"runs": 2, "failed": 1, "last_failed_at": last_fail},
        }


def test_error_summary_cycle_errors_from_last_cycle(make_client):
    with make_client() as client:
        db = client.app.state.services.db
        assert client.get("/api/status").json()["errors"]["cycle_errors"] == []
        db.kv_set("last_cycle", json.dumps({"started_at": stamp(), "fwi_error": True, "backup_error": "x", "backup": False}))
        assert client.get("/api/status").json()["errors"]["cycle_errors"] == ["backup_error", "fwi_error"]


def test_error_summary_shape_and_empty_db(make_client):
    """El bloque solo trae las claves documentadas: conteos e instantes, nada de mensajes libres."""
    with make_client() as client:
        r = client.get("/api/status")
        assert r.status_code == 200
        errors = r.json()["errors"]
        assert set(errors) == ERROR_KEYS
        assert errors["window_h"] == 24 and errors["by_product"] == {} and errors["cycle_errors"] == []
        seed_run(client.app.state.services.db, "VIIRS", 1, False)
        for info in client.get("/api/status").json()["errors"]["by_product"].values():
            assert set(info) == PRODUCT_KEYS


def test_failures_24h_empty(make_client):
    with make_client() as client:
        r = client.get("/api/status")
        assert r.status_code == 200
        assert r.json()["failures_24h"] == {}


def test_failures_24h_counts_and_last_error(make_client):
    with make_client() as client:
        db = client.app.state.services.db
        seed_run(db, "VIIRS", 1, True)
        seed_run(db, "VIIRS", 2, True)
        last_fail = seed_run(db, "VIIRS", 3, False, message="x" * 200)
        failures = client.get("/api/status").json()["failures_24h"]
        assert failures["VIIRS"] == {"runs": 3, "failed": 1, "last_failed_at": last_fail, "last_error": "x" * 160}


def test_failures_24h_ignores_runs_older_than_window(make_client):
    with make_client() as client:
        db = client.app.state.services.db
        seed_run(db, "VIIRS", 30, False, message="viejo")
        assert client.get("/api/status").json()["failures_24h"] == {}


def test_failures_24h_product_without_failures(make_client):
    with make_client() as client:
        db = client.app.state.services.db
        seed_run(db, "GOES-19", 1, True)
        failures = client.get("/api/status").json()["failures_24h"]
        assert failures["GOES-19"] == {"runs": 1, "failed": 0, "last_failed_at": None, "last_error": None}


def test_status_firms_quota_no_espera_a_firms(make_client, monkeypatch):
    """ROB-01: con el cupo vencido y FIRMS colgado, /api/status responde lo guardado en <1 s."""

    async def cuelgue(*_args, **_kwargs):
        await asyncio.sleep(60)
        return {}

    monkeypatch.setattr(firms, "key_status", cuelgue)
    with make_client(FIRMS_MAP_KEY="map-key-secreta-123") as client:
        db = client.app.state.services.db
        db.kv_set("firms_quota", json.dumps({"limit": 5000, "used": 12, "checked_at": "2020-01-01T00:00:00Z"}))
        inicio = time.perf_counter()
        r = client.get("/api/status")
        demora = time.perf_counter() - inicio
        assert r.status_code == 200 and demora < 1.0
        assert r.json()["firms_quota"] == {"limit": 5000, "used": 12, "checked_at": "2020-01-01T00:00:00Z", "error": True}


def test_status_firms_quota_sin_lectura_guardada(make_client):
    """ROB-01: sin lectura previa en `kv` el bloque sale con nulos y error, sin esperar a FIRMS."""
    with make_client(FIRMS_MAP_KEY="map-key-secreta-123") as client:
        r = client.get("/api/status")
        assert r.status_code == 200
        assert r.json()["firms_quota"] == {"limit": None, "used": None, "checked_at": None, "error": True}

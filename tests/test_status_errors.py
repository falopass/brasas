"""OPS-14: /api/status publica un resumen de errores de la ingesta, sin datos personales."""
import json
from datetime import timedelta

from backend.services import stamp, utcnow

ERROR_KEYS = {"window_h", "by_product", "cycle_errors"}
PRODUCT_KEYS = {"runs", "failed", "last_failed_at"}


def seed_run(db, product: str, hours_ago: float, ok: bool) -> str:
    started = stamp(utcnow() - timedelta(hours=hours_ago))
    db.execute("INSERT INTO ingest_runs(provider, product, started_at, finished_at, ok, n_records, n_new, message) "
               "VALUES (?,?,?,?,?,?,?,?)",
               ("prueba", product, started, started, int(ok), 0, 0, "detalle que no debe publicarse"))
    return started


def test_error_summary_counts_by_product_and_window(make_client):
    with make_client() as client:
        db = client.app.state.services.db
        seed_run(db, "VIIRS", 1, True)
        last_fail = seed_run(db, "VIIRS", 2, False)
        seed_run(db, "VIIRS", 30, False)   # fuera de la ventana de 24 h: no cuenta
        goes_fail = seed_run(db, "GOES-19", 3, False)

        body = client.get("/api/status").json()
        errors = body["errors"]
        assert errors["window_h"] == 24
        assert errors["by_product"] == {
            "GOES-19": {"runs": 1, "failed": 1, "last_failed_at": goes_fail},
            "VIIRS": {"runs": 2, "failed": 1, "last_failed_at": last_fail}}


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

"""Pruebas de `backend/diagnostics.py`: ventana de 24 h, recorte y enmascarado de claves."""

from datetime import timedelta

import pytest

from backend.db import Database
from backend.diagnostics import MAX_ERROR_LEN, error_summary, failures_24h, scrub
from backend.services import stamp, utcnow

MAP_KEY = "abcdef1234567890abcdef1234567890"


@pytest.fixture
def db(tmp_path) -> Database:
    return Database(tmp_path / "brasa.db")


def seed_run(db: Database, product: str, hours_ago: float, ok: bool, message: str = "") -> str:
    started = stamp(utcnow() - timedelta(hours=hours_ago))
    db.execute(
        "INSERT INTO ingest_runs(provider, product, started_at, finished_at, ok, n_records, n_new, message) VALUES (?,?,?,?,?,?,?,?)",
        ("prueba", product, started, started, int(ok), 0, 0, message),
    )
    return started


def test_failures_24h_incluye_la_corrida_fallida_reciente(db):
    last_fail = seed_run(db, "VIIRS", 1, False, message="HTTP 500")
    assert failures_24h(db)["VIIRS"] == {"runs": 1, "failed": 1, "last_failed_at": last_fail, "last_error": "HTTP 500"}


def test_failures_24h_ignora_la_corrida_fallida_de_hace_30_horas(db):
    seed_run(db, "VIIRS", 30, False, message="viejo")
    assert failures_24h(db) == {}


def test_failures_24h_producto_con_corridas_sin_fallos(db):
    seed_run(db, "GOES-19", 1, True)
    assert failures_24h(db)["GOES-19"] == {"runs": 1, "failed": 0, "last_failed_at": None, "last_error": None}


def test_failures_24h_recorta_el_mensaje(db):
    seed_run(db, "VIIRS", 1, False, message="x" * 400)
    assert failures_24h(db)["VIIRS"]["last_error"] == "x" * MAX_ERROR_LEN


def test_failures_24h_enmascara_la_map_key_de_la_url(db):
    seed_run(db, "VIIRS", 1, False, message=f"GET https://firms.example/api?MAP_KEY={MAP_KEY}&day=1 falló")
    last_error = failures_24h(db)["VIIRS"]["last_error"]
    assert f"MAP_KEY={MAP_KEY}" not in last_error
    assert "MAP_KEY=***" in last_error


def test_failures_24h_enmascara_antes_de_recortar(db):
    seed_run(db, "VIIRS", 1, False, message="x" * 150 + f" MAP_KEY={MAP_KEY}")
    last_error = failures_24h(db)["VIIRS"]["last_error"]
    assert MAP_KEY[:8] not in last_error
    assert len(last_error) == MAX_ERROR_LEN


def test_scrub_enmascara_bearer(db):
    assert scrub("Authorization: Bearer abc.def-123_456") == "Authorization: Bearer ***"


def test_scrub_enmascara_x_internal_token(db):
    assert scrub("X-Internal-Token: s3cr3t0") == "X-Internal-Token: ***"


def test_scrub_no_toca_una_clave_corta(db):
    assert scrub("?key=abc") == "?key=abc"


def test_error_summary_ventana_y_productos_ordenados(db):
    seed_run(db, "VIIRS", 1, True)
    seed_run(db, "GOES-19", 2, False)
    summary = error_summary(db)
    assert summary["window_h"] == 24
    assert list(summary["by_product"]) == ["GOES-19", "VIIRS"]
    assert summary["by_product"]["GOES-19"]["failed"] == 1

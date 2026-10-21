"""AUTO-34: el último ciclo publica el motivo de cada error, saneado, y no solo el nombre de la clave."""

import asyncio
import json

import pytest

from backend.db import Database
from backend.diagnostics import MAX_ERROR_LEN, error_summary
from backend.services import stamp, utcnow

MAP_KEY = "abcdef1234567890abcdef1234567890"


@pytest.fixture
def db(tmp_path) -> Database:
    return Database(tmp_path / "brasa.db")


def test_cycle_detail_agrega_el_motivo_y_conserva_cycle_errors(make_client):
    with make_client(GOES_ENABLED="0") as client:
        db = client.app.state.services.db
        db.kv_set("last_cycle", json.dumps({"started_at": stamp(utcnow()), "risk_error": "Open-Meteo 429 en la comuna 7301"}))
        errors = error_summary(db)
        assert errors["cycle_errors"] == ["risk_error"]
        assert errors["cycle_detail"] == {"risk_error": "Open-Meteo 429 en la comuna 7301"}


def test_cycle_detail_enmascara_la_map_key(db):
    db.kv_set("last_cycle", json.dumps({"firms_error": f"GET https://firms.example/api?MAP_KEY={MAP_KEY}&day=1"}))
    detalle = error_summary(db)["cycle_detail"]["firms_error"]
    assert MAP_KEY not in detalle and "MAP_KEY=***" in detalle


def test_cycle_detail_recorta_a_160_caracteres(db):
    db.kv_set("last_cycle", json.dumps({"official_error": "x" * 400}))
    assert error_summary(db)["cycle_detail"]["official_error"] == "x" * MAX_ERROR_LEN


def test_cycle_detail_sin_mensaje_dice_error_sin_detalle(db):
    db.kv_set("last_cycle", json.dumps({"risk_error": True, "backup_error": ""}))
    detalle = error_summary(db)["cycle_detail"]
    assert detalle == {"backup_error": "error sin detalle", "risk_error": "error sin detalle"}


def test_cycle_detail_oculta_rutas_absolutas(db):
    db.kv_set(
        "last_cycle",
        json.dumps({"risk_error": "No such file: /home/app/data/brasa.db", "backup_error": "Error en C:\\Users\\brasa\\work.db"}),
    )
    detalle = error_summary(db)["cycle_detail"]
    assert "/home/app" not in detalle["risk_error"] and "C:\\Users" not in detalle["backup_error"]
    assert "(ruta local)" in detalle["risk_error"] and "(ruta local)" in detalle["backup_error"]


def test_api_status_publica_el_motivo_del_riesgo(make_client, monkeypatch):
    with make_client(GOES_ENABLED="0") as client:
        svc = client.app.state.services
        svc._backfilled = True

        async def boom() -> int:
            raise RuntimeError("Open-Meteo 429 en la comuna 7301")

        monkeypatch.setattr(svc, "compute_risk", boom)
        asyncio.run(svc.tick_and_backup())

        body = client.get("/api/status").json()
        assert body["last_cycle"]["risk_error"] == "Open-Meteo 429 en la comuna 7301"
        assert body["errors"]["cycle_detail"]["risk_error"] == "Open-Meteo 429 en la comuna 7301"
        assert "risk_error" in body["errors"]["cycle_errors"]


def test_api_status_enmascara_la_clave_en_el_ciclo(make_client, monkeypatch):
    with make_client(GOES_ENABLED="0") as client:
        svc = client.app.state.services
        svc._backfilled = True

        async def boom() -> int:
            raise RuntimeError(f"GET ?MAP_KEY={MAP_KEY}")

        monkeypatch.setattr(svc, "compute_risk", boom)
        asyncio.run(svc.tick_and_backup())

        body = client.get("/api/status").json()
        assert MAP_KEY not in body["last_cycle"]["risk_error"]
        assert "MAP_KEY=***" in body["last_cycle"]["risk_error"]
        assert body["errors"]["cycle_detail"]["risk_error"] == body["last_cycle"]["risk_error"]

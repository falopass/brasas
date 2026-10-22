"""Pruebas de `backend/diagnostics.py`: ventana de 24 h, recorte, enmascarado y claves del último ciclo."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from backend.db import Database
from backend.diagnostics import MAX_ERROR_LEN, desfase, error_summary, failures_24h, scrub
from backend.services import stamp, utcnow

MAP_KEY = "abcdef1234567890abcdef1234567890"
AHORA = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)


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


def test_failures_24h_cuenta_ok_y_fallida_del_mismo_producto(db):
    seed_run(db, "VIIRS", 1, True)
    last_fail = seed_run(db, "VIIRS", 2, False, message="HTTP 500")
    assert failures_24h(db)["VIIRS"] == {"runs": 2, "failed": 1, "last_failed_at": last_fail, "last_error": "HTTP 500"}


def test_sin_corridas_todo_vacio(db):
    summary = error_summary(db)
    assert summary["window_h"] == 24 and summary["by_product"] == {} and summary["cycle_errors"] == []
    assert summary["desfase"]["estado"] == "sin_datos"
    assert failures_24h(db) == {}


def test_failures_24h_ignora_la_corrida_fallida_de_hace_30_horas(db):
    seed_run(db, "VIIRS", 30, False, message="viejo")
    assert failures_24h(db) == {}


def test_failures_24h_producto_con_corridas_sin_fallos(db):
    seed_run(db, "GOES-19", 1, True)
    assert failures_24h(db)["GOES-19"] == {"runs": 1, "failed": 0, "last_failed_at": None, "last_error": None}


def test_failures_24h_recorta_por_caracteres_y_no_parte_utf8(db):
    message = "ñ🌲" * 200
    seed_run(db, "VIIRS", 1, False, message=message)
    last_error = failures_24h(db)["VIIRS"]["last_error"]
    assert last_error == message[:MAX_ERROR_LEN]
    assert len(last_error.encode("utf-8")) > MAX_ERROR_LEN  # 160 caracteres, no 160 bytes


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


@pytest.mark.parametrize(
    "texto,esperado",
    [
        ("Authorization: Bearer abc.def-123_456", "Authorization: Bearer ***"),
        ("X-Internal-Token: s3cr3t0", "X-Internal-Token: ***"),
        ("?key=abc", "?key=abc"),  # una clave corta no es un secreto
    ],
)
def test_scrub_enmascara_solo_las_claves(texto, esperado):
    assert scrub(texto) == esperado


def test_error_summary_ventana_y_productos_ordenados(db):
    seed_run(db, "VIIRS", 1, True)
    seed_run(db, "GOES-19", 2, False)
    seed_run(db, "GOES-19", 30, False)  # fuera de la ventana de 24 h: no cuenta
    summary = error_summary(db)
    assert summary["window_h"] == 24
    assert list(summary["by_product"]) == ["GOES-19", "VIIRS"]
    assert summary["by_product"]["GOES-19"]["runs"] == 1
    assert summary["by_product"]["GOES-19"]["failed"] == 1


def test_error_summary_cycle_errors_solo_claves_error(db):
    db.kv_set("last_cycle", json.dumps({"started_at": stamp(), "fwi_error": True, "backup_error": "x", "backup": False}))
    assert error_summary(db)["cycle_errors"] == ["backup_error", "fwi_error"]


def seed_obs(db: Database, source: str, hours_ago: float) -> None:
    observed = stamp(AHORA - timedelta(hours=hours_ago))
    db.execute(
        "INSERT INTO observations(id, source, lat, lon, observed_at, ingested_at) VALUES (?,?,?,?,?,?)",
        (f"{source}-{hours_ago}", source, -33.0, -71.0, observed, observed),
    )


def marcar_ingesta(db: Database, minutes_ago: float) -> None:
    db.kv_set("last_ingest_at", stamp(AHORA - timedelta(minutes=minutes_ago)))


def test_desfase_al_dia_con_ciclo_y_fuente_recientes(db):
    marcar_ingesta(db, 5)
    seed_obs(db, "VIIRS_NOAA20_NRT", 20 / 60)
    out = desfase(db, now=AHORA)
    assert out["estado"] == "al_dia"
    assert out["ingest_age_min"] == 5
    assert out["fuentes"] == [{"source": "VIIRS_NOAA20_NRT", "age_h": 0.3, "stale": False}]
    assert "atrasada" not in out["texto"] and "detenido" not in out["texto"]


def test_desfase_atrasada_cuando_la_fuente_no_trae_dato_nuevo(db):
    marcar_ingesta(db, 12)
    seed_obs(db, "VIIRS_NOAA20_NRT", 31)
    out = desfase(db, now=AHORA)
    assert out["estado"] == "atrasada"
    assert out["fuentes"][0]["stale"] is True
    assert 30 <= out["fuentes"][0]["age_h"] <= 32
    assert "31,0 h" in out["texto"] and "VIIRS_NOAA20_NRT" in out["texto"]
    assert "no entró dato nuevo" in out["texto"]
    assert "firms_quota" in out["que_hacer"]


def test_desfase_al_dia_nombra_la_deteccion_mas_nueva(db):
    """Con dos fuentes al día, el texto nombra la más fresca; antes nombraba la más vieja."""
    marcar_ingesta(db, 5)
    seed_obs(db, "GOES-19", 4)
    seed_obs(db, "VIIRS_NOAA20_NRT", 0.3)
    out = desfase(db, now=AHORA)
    assert out["estado"] == "al_dia"
    assert "0,3 h (VIIRS_NOAA20_NRT)" in out["texto"]
    assert "4,0 h" not in out["texto"]


def test_desfase_atrasada_apunta_a_la_fuente_que_se_atraso(db):
    """Si solo GOES dejó de traer dato, la acción no manda a revisar el cupo de FIRMS."""
    marcar_ingesta(db, 12)
    seed_obs(db, "GOES-19", 31)
    seed_obs(db, "VIIRS_NOAA20_NRT", 0.2)
    out = desfase(db, now=AHORA)
    assert out["estado"] == "atrasada"
    assert "GOES" in out["que_hacer"] and "firms_quota" not in out["que_hacer"]


def test_desfase_parado_cuando_el_ciclo_lleva_horas_sin_cerrar(db):
    marcar_ingesta(db, 240)
    assert desfase(db, now=AHORA)["estado"] == "parado"


def test_desfase_reloj_cuando_la_marca_esta_en_el_futuro(db):
    marcar_ingesta(db, -30)
    assert desfase(db, now=AHORA)["estado"] == "reloj"


def test_desfase_sin_marca_no_lanza_y_dice_sin_datos(db):
    out = desfase(db, now=AHORA)
    assert out["estado"] == "sin_datos"
    assert out["ingest_age_min"] is None
    assert out["fuentes"] == []
    assert "Todavía no hay" in out["texto"]


def test_desfase_que_hacer_no_expone_secretos(db):
    marcar_ingesta(db, 12)
    seed_obs(db, "VIIRS_NOAA20_NRT", 31)
    textos = {desfase(db, now=AHORA)["que_hacer"]}
    db.execute("DELETE FROM kv WHERE key = 'last_ingest_at'")
    textos.add(desfase(db, now=AHORA)["que_hacer"])
    marcar_ingesta(db, 240)
    textos.add(desfase(db, now=AHORA)["que_hacer"])
    marcar_ingesta(db, -30)
    textos.add(desfase(db, now=AHORA)["que_hacer"])
    for texto in textos:
        bajo = texto.lower()
        assert "token" not in bajo and "key" not in bajo and "firms_map_key" not in bajo


def test_api_status_publica_errors_desfase(make_client):
    with make_client(GOES_ENABLED="0") as client:
        body = client.get("/api/status").json()
        assert isinstance(body["errors"]["desfase"]["estado"], str)
        assert body["errors"]["desfase"]["texto"]

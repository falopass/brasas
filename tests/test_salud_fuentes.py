"""AUTO-15/AUTO-39: informe de salud de las fuentes (scripts/local/salud_fuentes.py).

Cada prueba siembra `ingest_runs` / `observations` en la base temporal del cliente, o usa el
JSON de /api/status capturado en tests/data/status_produccion.json, y comprueba el
veredicto, el arreglo y el código de salida. Ninguna toca la red.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "local"))
import salud_fuentes as salud  # noqa: E402

from backend.services import stamp, utcnow  # noqa: E402

FUENTE_KEYS = {
    "fuente",
    "tipo",
    "ultimo_dato",
    "dato_min",
    "ultima_corrida",
    "corrida_ok",
    "ultimo_error",
    "error_min",
    "atraso_min",
    "veredicto",
    "arreglo",
}
FUENTES = ["NASA FIRMS", "NOAA GOES", "CONAF", "DMC", "Open-Meteo", "GLM", "humo ADPF"]


def seed_run(db, provider: str, product: str, minutes_ago: float, ok: bool, message: str = "", ahora=None) -> str:
    moment = (ahora or utcnow()) - timedelta(minutes=minutes_ago)
    started = stamp(moment)
    db.execute(
        "INSERT INTO ingest_runs(provider, product, started_at, finished_at, ok, n_records, n_new, message) VALUES (?,?,?,?,?,?,?,?)",
        (provider, product, started, started, int(ok), 0, 0, message),
    )
    return started


def seed_obs(db, source: str, minutes_ago: float, ahora=None) -> str:
    moment = stamp((ahora or utcnow()) - timedelta(minutes=minutes_ago))
    db.execute(
        "INSERT INTO observations(id, source, lat, lon, observed_at, ingested_at) VALUES (?,?,?,?,?,?)",
        (f"obs:{source}:{minutes_ago}", source, -33.0, -71.0, moment, moment),
    )
    return moment


def fila(informe: dict, fuente: str) -> dict:
    return next(f for f in informe["fuentes"] if f["fuente"] == fuente)


def test_fuente_al_dia_no_lleva_arreglo(make_client):
    with make_client() as client:
        db = client.app.state.services.db
        seed_run(db, "NASA FIRMS", "VIIRS_NOAA20_NRT,VIIRS_NOAA21_NRT", 5, True)
        informe = salud.evaluar(db)
        firms = fila(informe, "NASA FIRMS")
        assert firms["veredicto"] == "al día"
        assert firms["corrida_ok"] is True
        assert firms["arreglo"] == ""


def test_error_de_cupo_propone_revisar_la_clave(make_client):
    with make_client() as client:
        db = client.app.state.services.db
        seed_run(db, "NASA FIRMS", "VIIRS_NOAA20_NRT", 5, False, "429 Too Many Requests")
        firms = fila(salud.evaluar(db), "NASA FIRMS")
        assert firms["veredicto"] in ("atrasada", "caída")
        assert "cupo" in firms["arreglo"]
        assert "429" in firms["ultimo_error"]


def test_ultimo_dato_sale_de_observations(make_client):
    with make_client() as client:
        db = client.app.state.services.db
        seed_obs(db, "VIIRS_NOAA20_NRT", 12)
        seed_run(db, "NASA FIRMS", "VIIRS_NOAA20_NRT", 2, True)
        firms = fila(salud.evaluar(db), "NASA FIRMS")
        assert firms["dato_min"] == 12
        assert firms["veredicto"] == "al día"


def test_fuente_sin_corridas_es_nunca_corrio(make_client):
    with make_client() as client:
        informe = salud.evaluar(client.app.state.services.db)
        for fuente in ("GLM", "humo ADPF"):
            row = fila(informe, fuente)
            assert row["veredicto"] == "nunca corrió"
            assert row["ultima_corrida"] is None and row["corrida_ok"] is None
            assert row["arreglo"]


def test_json_es_consumible_y_con_claves_estables(make_client, capsys):
    with make_client() as client:
        seed_run(client.app.state.services.db, "NASA FIRMS", "VIIRS_NOAA20_NRT", 5, True)
        salud.main(["--json", "--db", str(client.app.state.services.db.path)])
        payload = json.loads(capsys.readouterr().out)
        assert [f["fuente"] for f in payload["fuentes"]] == FUENTES
        for row in payload["fuentes"]:
            assert set(row) == FUENTE_KEYS
        assert set(payload["resumen"]) == {"ok", "total", "al_dia", "atrasadas", "caidas", "nunca_corrio"}


def test_codigo_0_cuando_todas_las_programadas_estan_al_dia(make_client):
    with make_client() as client:
        db = client.app.state.services.db
        seed_run(db, "NASA FIRMS", "VIIRS_NOAA20_NRT", 5, True)
        seed_run(db, "NOAA GOES", "GOES19_FDCF", 5, True)
        seed_run(db, "CONAF · reporte público de incendios (GEPRIF)", "CONAF_INCENDIOS", 5, True)
        seed_run(db, "Dirección Meteorológica de Chile (DMC)", "DMC_CAP", 5, True)
        db.kv_set("risk_computed_at", stamp())
        assert salud.main(["--json", "--db", str(db.path)]) == 0


def test_codigo_1_con_una_fuente_caida(make_client):
    with make_client() as client:
        db = client.app.state.services.db
        seed_run(db, "NASA FIRMS", "VIIRS_NOAA20_NRT", 5, False, "503 Service Unavailable")
        assert salud.main(["--json", "--db", str(db.path)]) == 1
        assert fila(salud.evaluar(db), "NASA FIRMS")["veredicto"] == "caída"


def test_conaf_con_error_de_formato_propone_revisar_el_parser(make_client):
    with make_client() as client:
        db = client.app.state.services.db
        seed_run(db, "CONAF · reporte público de incendios (GEPRIF)", "CONAF_INCENDIOS", 5, False, "KeyError: 'sup_total'")
        conaf = fila(salud.evaluar(db), "CONAF")
        assert conaf["veredicto"] == "caída"
        assert "backend/providers/conaf.py" in conaf["arreglo"]


def test_open_meteo_usa_la_marca_de_riesgo(make_client):
    with make_client() as client:
        db = client.app.state.services.db
        db.kv_set("risk_computed_at", stamp())
        db.kv_set("last_cycle", json.dumps({"finished_at": stamp(), "risk_error": "Open-Meteo no respondió"}))
        open_meteo = fila(salud.evaluar(db), "Open-Meteo")
        assert open_meteo["veredicto"] == "atrasada"
        assert open_meteo["ultimo_error"] == "Open-Meteo no respondió"


def test_base_inexistente_no_revienta(tmp_path, capsys):
    destino = tmp_path / "recien-clonado" / "brasa.db"
    assert salud.main(["--json", "--db", str(destino)]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert len(payload["fuentes"]) == 7
    assert all(row["veredicto"] == "nunca corrió" for row in payload["fuentes"])


# --- AUTO-39: informe de producción desde /api/status ---

STATUS_FIXTURE = Path(__file__).parent / "data" / "status_produccion.json"


def status_real() -> dict:
    return json.loads(STATUS_FIXTURE.read_text(encoding="utf-8"))


def status_sano() -> dict:
    """La captura real con sus fallas reparadas: respaldo ok y ciclo sin errores."""
    status = status_real()
    ciclo = status["last_cycle"]
    ciclo.update({"backup": True, "work_backup": True, "backup_error": None, "fwi_error": None, "rain_error": None})
    status["backup"]["updated_at"] = ciclo["finished_at"]
    return status


def ahora_status(status: dict) -> datetime:
    return datetime.fromisoformat(status["time_utc"].replace("Z", "+00:00"))


def test_status_sano_da_0_y_programadas_al_dia(tmp_path, capsys):
    status = status_sano()
    informe = salud.evaluar_status(status, ahora_status(status))
    programadas = [f for f in informe["fuentes"] if f["tipo"] == "ingesta"]
    assert all(f["veredicto"] == "al día" for f in programadas)
    assert all(f["veredicto"] == "al día" for f in informe["fuentes"] if f["tipo"] == "sistema")
    assert informe["resumen"]["ok"] is True
    destino = tmp_path / "status.json"
    destino.write_text(json.dumps(status), encoding="utf-8")
    assert salud.main(["--json", "--desde-archivo", str(destino)]) == 0


def test_status_fuente_atrasada_da_1_y_la_nombra(tmp_path, capsys):
    status = status_sano()
    for run in status["runs"]:
        if run["provider"] == "NASA FIRMS":
            run["started_at"] = "2026-10-21T10:00:50Z"  # más de 3 h antes de time_utc
            run["finished_at"] = run["started_at"]
    informe = salud.evaluar_status(status, ahora_status(status))
    firms = fila(informe, "NASA FIRMS")
    assert firms["veredicto"] == "atrasada"
    destino = tmp_path / "status.json"
    destino.write_text(json.dumps(status), encoding="utf-8")
    assert salud.main(["--json", "--desde-archivo", str(destino)]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert fila(payload, "NASA FIRMS")["veredicto"] == "atrasada"


def test_status_respaldo_fallido_da_1_y_nombra_el_respaldo():
    informe = salud.evaluar_status(status_real(), ahora_status(status_real()))
    respaldo = fila(informe, "Respaldo")
    assert respaldo["veredicto"] == "caída"
    assert "respaldo" in respaldo["arreglo"].lower()
    assert respaldo["ultimo_error"]
    assert informe["resumen"]["ok"] is False


def test_status_cupo_firms_en_error_aparece_como_hallazgo():
    status = status_sano()
    status["firms_quota"]["error"] = True
    informe = salud.evaluar_status(status, ahora_status(status))
    cupo = fila(informe, "Cupo FIRMS")
    assert cupo["veredicto"] == "caída"
    assert "cupo" in cupo["ultimo_error"].lower()
    assert "FIRMS" in cupo["arreglo"]
    assert informe["resumen"]["ok"] is False


def test_status_captura_real_refleja_las_fallas_de_produccion():
    """La captura del 21-oct-2026: respaldo roto y ciclo de riesgo con error."""
    informe = salud.evaluar_status(status_real(), ahora_status(status_real()))
    assert fila(informe, "Respaldo")["veredicto"] == "caída"
    assert fila(informe, "Open-Meteo")["veredicto"] == "atrasada"
    assert fila(informe, "NASA FIRMS")["veredicto"] == "al día"
    assert informe["resumen"]["ok"] is False


def test_status_runs_vacios_informa_nunca_corrio():
    status = status_sano()
    status["runs"] = []
    status["failures_24h"] = {}
    status["newest_observation"] = {}
    informe = salud.evaluar_status(status, ahora_status(status))
    for fuente in ("NASA FIRMS", "NOAA GOES", "CONAF", "DMC"):
        assert fila(informe, fuente)["veredicto"] == "nunca corrió"
    assert informe["resumen"]["ok"] is False

"""OPS-19: /api/status publica la cobertura de FWI, DMC y lluvia para el diagnóstico."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from backend.services import stamp

CHILE_TZ = ZoneInfo("America/Santiago")


def test_status_coverage_cuenta_fwi_dmc_y_lluvia(make_client):
    with make_client() as client:
        db = client.app.state.services.db
        today = datetime.now(CHILE_TZ).date().isoformat()
        now = datetime.now(timezone.utc)
        db.execute(
            "INSERT INTO fwi_daily(comuna_code, date, ffmc, dmc, dc, isi, bui, fwi, level, computed_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (1101, today, 80, 10, 20, 1, 2, 3, "bajo", stamp()),
        )
        db.execute(
            "INSERT INTO rain_normal(comuna_code, days, daily_normals, computed_at) VALUES (?,?,?,?)",
            (1101, 1, json.dumps({"06-01": 1.0}), stamp()),
        )
        db.execute(
            "INSERT INTO rain_season(comuna_code, year, current_mm, normal_mm, ratio, level, computed_at) VALUES (?,?,?,?,?,?,?)",
            (1101, 2026, 10.0, 5.0, 2.0, "humedo", stamp()),
        )
        db.execute(
            "INSERT INTO dmc_alerts(id, kind, event, headline, severity, urgency, onset, expires, web, areas, comunas, fetched_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "aviso-1",
                "viento",
                "Viento fuerte",
                "Viento fuerte en la zona",
                "Moderate",
                "Future",
                (now - timedelta(hours=1)).isoformat(),
                (now + timedelta(hours=1)).isoformat(),
                "https://example.cl/aviso",
                "[]",
                "[1101, 1107]",
                stamp(),
            ),
        )

        coverage = client.get("/api/status?coverage=1").json()["coverage"]
        assert "coverage" not in client.get("/api/status").json()
        assert coverage == {
            "comunas": 345,
            "fwi_comunas": 1,
            "rain_normals": 1,
            "rain_comunas": 1,
            "dmc_alerts": 1,
            "dmc_comunas": 2,
        }


def _corre_script(payload) -> subprocess.CompletedProcess:
    script = Path(__file__).resolve().parents[1] / ".github" / "scripts" / "cobertura_status.py"
    return subprocess.run([sys.executable, str(script)], input=json.dumps(payload), capture_output=True, text=True)


def test_script_de_cobertura_publica_las_anotaciones():
    payload = {
        "coverage": {
            "comunas": 345,
            "fwi_comunas": 344,
            "rain_normals": 317,
            "rain_comunas": 258,
            "dmc_alerts": 6,
            "dmc_comunas": 220,
        },
        "open_meteo": {"calls": 10, "rate_limited": 2},
        "errors": {"cycle_errors": ["fwi_error", "rain_error"]},
    }
    result = _corre_script(payload)
    assert result.returncode == 0, result.stderr
    assert "::notice title=cobertura::" in result.stdout
    assert "::warning title=FWI incompleto::344 de 345 comunas" in result.stdout
    assert "::warning title=Open-Meteo 429::2 respuestas" in result.stdout
    assert "::warning title=Errores del ciclo::fwi_error, rain_error" in result.stdout


@pytest.mark.parametrize("payload", [{}, {"coverage": 345}], ids=["sin-clave", "mal-formada"])
def test_script_sin_cobertura_avisa_y_sale_en_verde(payload):
    """AUTO-48: sin la clave coverage, o con una mal formada, el diagnóstico no puede quedar mudo."""
    result = _corre_script(payload)
    assert result.returncode == 0, result.stderr
    assert "::warning title=Sin cobertura::" in result.stdout


@pytest.mark.parametrize(
    ("last_cycle", "esperado"),
    [
        ({"finished_at": "2026-10-21T00:10:43Z", "fwi_error": "Open-Meteo 429", "rain_error": True}, "FWI, lluvia"),
        ({"fwi_error": True}, "FWI"),
    ],
    ids=["fwi-y-lluvia", "solo-fwi"],
)
def test_script_avisa_ciclo_incompleto(last_cycle, esperado):
    """AUTO-48: fwi_error y rain_error en last_cycle nombran lo que quedó a medias."""
    payload = {"coverage": {"comunas": 345, "fwi_comunas": 345}, "last_cycle": last_cycle}
    result = _corre_script(payload)
    assert result.returncode == 0, result.stderr
    assert f"::warning title=Ciclo incompleto::{esperado}" in result.stdout


def test_script_sano_no_emite_advertencias():
    payload = {
        "coverage": {
            "comunas": 345,
            "fwi_comunas": 345,
            "rain_normals": 345,
            "rain_comunas": 345,
            "dmc_alerts": 0,
            "dmc_comunas": 0,
        },
        "open_meteo": {"calls": 10, "rate_limited": 0},
        "errors": {"cycle_errors": []},
        "last_cycle": {"started_at": "2026-10-21T00:10:39Z", "finished_at": "2026-10-21T00:10:43Z", "backup": True},
    }
    result = _corre_script(payload)
    assert result.returncode == 0, result.stderr
    assert "::warning" not in result.stdout

"""Comparador semana a semana: lógica de comparación, foto diaria del pronóstico y endpoint.

La foto (`risk_snapshot`) es lo que permite comparar: sin ella el pronóstico se sobrescribe y no
queda con qué comparar. Las pruebas usan fotos sintéticas porque en producción la primera semana
todavía no existe.
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta

from backend import trend
from backend.risk import CHILE_TZ


def today_chile() -> date:
    """El mismo día que usa la aplicación (America/Santiago), no una resta fija de horas."""
    return datetime.now(CHILE_TZ).date()


def rank_compare_cases():
    assert trend.rank("bajo") == 0 and trend.rank("extremo") == 3
    assert trend.rank(None) is None and trend.rank("inventado") is None
    assert trend.compare("alto", "moderado") == "sube"
    assert trend.compare("moderado", "alto") == "baja"
    assert trend.compare("alto", "alto") == "igual"
    assert trend.compare("alto", None) is None
    assert trend.compare(None, "alto") is None


def test_compare_uses_the_scale_and_admits_when_there_is_nothing_to_compare():
    rank_compare_cases()


def test_summarize_counts_every_case():
    rows = [
        {"change": "sube"},
        {"change": "sube"},
        {"change": "baja"},
        {"change": "igual"},
        {"change": "sin_anterior", "missing": "semana_pasada"},
        {"change": "sin_anterior", "missing": "hoy"},
        {"change": "sin_anterior", "missing": "ambos"},
    ]
    assert trend.summarize(rows) == {"sube": 2, "baja": 1, "igual": 1, "sin_anterior": 3, "sin_hoy": 2}


def test_row_explains_the_change_and_keeps_both_dates():
    current = {"level": "bajo", "level_combined": "alto", "score": 80}
    previous = {"level": "bajo", "level_combined": "moderado", "score": 55, "snapshot_date": "2026-10-11"}
    out = trend.row("2026-10-18", current, previous)
    assert out["current"] == "alto" and out["previous"] == "moderado"  # manda el combinado
    assert out["change"] == "sube" and out["previous_at"] == "2026-10-11"
    assert out["change_label"] == trend.CHANGE_LABELS["sube"]
    assert out["missing"] is None


def test_row_names_which_forecast_is_missing():
    previous = {"level_combined": "alto", "snapshot_date": "2026-10-13"}
    current = {"level_combined": "alto"}

    hoy = trend.row("2026-10-20", None, previous)
    assert hoy["missing"] == "hoy" and hoy["change"] == "sin_anterior"
    assert hoy["change_label"] == "Hoy no hay pronóstico para ese día"
    assert hoy["previous_at"] == "2026-10-13"

    pasada = trend.row("2026-10-20", current, None)
    assert pasada["missing"] == "semana_pasada" and pasada["change"] == "sin_anterior"
    assert pasada["change_label"] == "No hay pronóstico de la semana pasada para ese día"

    ambos = trend.row("2026-10-20", None, None)
    assert ambos["missing"] == "ambos" and ambos["change"] == "sin_anterior"
    assert ambos["change_label"] == "No hay pronóstico ni de hoy ni de la semana pasada"


def seed_risk(db, comuna: int, levels: list[tuple[date, str, str | None, int]]) -> None:
    for day, level, combined, score in levels:
        db.execute(
            "INSERT OR REPLACE INTO risk_daily(comuna_code, date, level, score, hours_3of3, hours_2of3, "
            "tmax, rhmin, windmax, gustmax, level_combined, computed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (comuna, day.isoformat(), level, score, 0, 1, 30.0, 25.0, 20.0, 30.0, combined, f"{day.isoformat()}T00:00:00Z"),
        )


def seed_snapshot(db, comuna: int, snapshot: date, target: date, level: str, score: int) -> None:
    db.execute(
        "INSERT OR REPLACE INTO risk_snapshot(snapshot_date, comuna_code, target_date, level, level_combined, score) VALUES (?,?,?,?,?,?)",
        (snapshot.isoformat(), comuna, target.isoformat(), level, level, score),
    )


def test_snapshot_is_taken_once_per_day_and_can_be_emptied(make_client):
    with make_client() as client:
        svc = client.app.state.services
        today = today_chile()
        seed_risk(svc.db, 5109, [(today, "bajo", "bajo", 10), (today + timedelta(days=1), "alto", "extremo", 90)])
        assert asyncio.run(svc.capture_risk_snapshot()) == 2  # dos días pronosticados
        assert asyncio.run(svc.capture_risk_snapshot()) == 0  # ya hay foto de hoy
        assert svc.db.one("SELECT COUNT(*) AS n FROM risk_snapshot")["n"] == 2


def test_snapshot_without_forecast_does_not_invent_rows(make_client):
    with make_client() as client:
        svc = client.app.state.services
        assert asyncio.run(svc.capture_risk_snapshot()) == 0
        assert svc.db.one("SELECT COUNT(*) AS n FROM risk_snapshot")["n"] == 0


def test_snapshot_prunes_what_is_older_than_the_window(make_client):
    with make_client() as client:
        svc = client.app.state.services
        today = today_chile()
        seed_risk(svc.db, 5109, [(today, "bajo", "bajo", 10)])
        old = today - timedelta(days=200)
        seed_snapshot(svc.db, 5109, old, old + timedelta(days=1), "alto", 70)
        asyncio.run(svc.capture_risk_snapshot())
        assert svc.db.one("SELECT COUNT(*) AS n FROM risk_snapshot WHERE snapshot_date = ?", (old.isoformat(),))["n"] == 0
        assert svc.db.one("SELECT COUNT(*) AS n FROM risk_snapshot WHERE snapshot_date = ?", (today.isoformat(),))["n"] == 1


def test_trend_endpoint_compares_the_same_day_one_week_apart(make_client):
    with make_client() as client:
        svc = client.app.state.services
        today = today_chile()
        seed_risk(svc.db, 5109, [(today, "bajo", "moderado", 40), (today + timedelta(days=1), "alto", "extremo", 95)])
        seed_snapshot(svc.db, 5109, today - timedelta(days=7), today, "bajo", 10)
        seed_snapshot(svc.db, 5109, today - timedelta(days=6), today + timedelta(days=1), "moderado", 50)
        body = client.get("/api/risk/5109/trend").json()
        by_day = {r["target_date"]: r for r in body["rows"]}
        assert by_day[today.isoformat()]["change"] == "sube"  # bajo → moderado
        assert by_day[(today + timedelta(days=1)).isoformat()]["change"] == "sube"  # moderado → extremo
        assert body["summary"]["sube"] == 2 and body["weeks"] == 1
        assert body["snapshots_from"] == (today - timedelta(days=7)).isoformat()


def test_trend_endpoint_says_unknown_when_there_is_no_previous_forecast(make_client):
    with make_client() as client:
        svc = client.app.state.services
        today = today_chile()
        seed_risk(svc.db, 5109, [(today, "alto", "alto", 80)])
        body = client.get("/api/risk/5109/trend").json()
        assert body["rows"][0]["change"] == "sin_anterior" and body["rows"][0]["previous"] is None
        assert body["rows"][0]["missing"] == "semana_pasada"
        assert body["summary"]["sin_anterior"] == 1 and body["summary"]["sin_hoy"] == 0
        assert body["snapshots_from"] is None


def test_trend_endpoint_names_a_missing_forecast_for_today(make_client):
    with make_client() as client:
        svc = client.app.state.services
        today = today_chile()
        seed_snapshot(svc.db, 5109, today - timedelta(days=7), today, "alto", 80)
        body = client.get("/api/risk/5109/trend").json()
        assert body["rows"][0]["current"] is None and body["rows"][0]["previous"] == "alto"
        assert body["rows"][0]["missing"] == "hoy"
        assert body["rows"][0]["change_label"] == "Hoy no hay pronóstico para ese día"
        assert body["summary"]["sin_anterior"] == 1 and body["summary"]["sin_hoy"] == 1


def test_trend_endpoint_404_for_an_unknown_comuna(make_client):
    with make_client() as client:
        assert client.get("/api/risk/999999/trend").status_code == 404

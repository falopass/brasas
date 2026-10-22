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
    assert trend.compare("extremo_falso", "alto") is None


def test_compare_uses_the_scale_and_admits_when_there_is_nothing_to_compare():
    rank_compare_cases()


def test_row_uses_the_label_of_each_change():
    previous = {"level_combined": "moderado", "snapshot_date": "2026-10-13"}
    for level, change in (("alto", "sube"), ("bajo", "baja"), ("moderado", "igual")):
        out = trend.row("2026-10-20", {"level_combined": level}, previous)
        assert out["change"] == change
        assert out["change_label"] == trend.CHANGE_LABELS[change]


def test_summarize_without_rows_returns_every_counter_at_zero():
    assert trend.summarize([]) == {"sube": 0, "baja": 0, "igual": 0, "sin_anterior": 0, "sin_hoy": 0}


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


def test_row_falls_back_to_level_when_the_combined_level_is_missing_or_empty():
    """Una foto puede traer `level` sin `level_combined` (o con uno vacío): manda `level`."""
    previous = {"level_combined": "moderado", "snapshot_date": "2026-10-13"}
    for current in ({"level": "alto"}, {"level": "alto", "level_combined": ""}, {"level": "alto", "level_combined": None}):
        out = trend.row("2026-10-20", current, previous)
        assert out["current"] == "alto" and out["change"] == "sube"
        assert out["missing"] is None
    for prev in ({"level": "bajo"}, {"level": "bajo", "level_combined": ""}):
        out = trend.row("2026-10-20", {"level_combined": "alto"}, prev)
        assert out["previous"] == "bajo" and out["change"] == "sube"


def test_row_without_snapshot_date_leaves_previous_at_as_none():
    """Sin `snapshot_date` la fecha del pronóstico viejo es None, no la cadena «None»."""
    assert trend.row("2026-10-20", {"level_combined": "alto"}, None)["previous_at"] is None
    out = trend.row("2026-10-20", {"level_combined": "alto"}, {"level_combined": "bajo"})
    assert out["previous_at"] is None
    assert out["change"] == "sube"  # la comparación sí se hace aunque falte la fecha


def test_row_keeps_a_zero_score_as_zero_not_as_missing():
    out = trend.row(
        "2026-10-20",
        {"level_combined": "alto", "score": 0},
        {"level_combined": "bajo", "score": 0, "snapshot_date": "2026-10-13"},
    )
    assert out["current_score"] == 0 and out["previous_score"] == 0
    assert out["current_score"] is not None and out["previous_score"] is not None


def test_row_with_a_level_outside_the_scale_says_what_is_missing_instead_of_comparing():
    """Un nivel que la escala no reconoce nunca se lee como «sube» o «baja»."""
    cases = (
        ({"level_combined": ""}, {"level_combined": "alto"}, "hoy"),
        ({"level_combined": "alto"}, {"level_combined": "NIVEL_X"}, "semana_pasada"),
        ({"level_combined": "???"}, {"level_combined": "!!!"}, "ambos"),
    )
    for current, previous, missing in cases:
        out = trend.row("2026-10-20", current, previous)
        assert out["change"] == "sin_anterior"
        assert out["missing"] == missing
        assert out["change_label"] == trend.MISSING_LABELS[missing]


def test_summarize_counts_an_invented_change_as_uncomparable_without_new_keys():
    rows = [{"change": "sube"}, {"change": "terremoto"}, {"change": None}]
    out = trend.summarize(rows)
    assert set(out) == {"sube", "baja", "igual", "sin_anterior", "sin_hoy"}
    assert out["sin_anterior"] == 2  # los dos cambios desconocidos, no una clave nueva
    assert sum(out.values()) == len(rows)


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

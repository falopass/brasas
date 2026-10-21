"""Frescura del escenario estimado (FUEGO-02, FUEGO-24): ni el FFMC ni el viento pueden ser de otra época.

El escenario se rotula «con las condiciones de ahora»; si el pronóstico más cercano es de hace
días, el dato ya no describe ahora y no debe mostrarse (en la ficha ni, sobre todo, en un aviso
que despierta a alguien). Estos tests van contra `backend.spread.estimate`, que es la función
única que arman la ficha y los avisos, con un reloj fijo para no depender de la hora real.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from backend import spread
from backend.db import Database

CHILE = ZoneInfo("America/Santiago")
NOW = datetime(2026, 1, 20, 18, 0, tzinfo=timezone.utc)  # 15:00 en Chile
INCIDENTE = {"comuna_code": 13101}
COMUNA = 13101


def _stamp(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def _fwi(db: Database, date_iso: str, ffmc: float = 88.0, code: int = COMUNA, computed_at: datetime = NOW) -> None:
    db.execute(
        "INSERT INTO fwi_daily(comuna_code, date, ffmc, dmc, dc, isi, bui, fwi, level, computed_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (code, date_iso, ffmc, 20.0, 100.0, 5.0, 50.0, 15.0, "moderado", _stamp(computed_at)),
    )


def _wind(
    db: Database,
    *,
    computed_at: datetime = NOW,
    hours: list[dict] | None = None,
    code: int = COMUNA,
) -> None:
    hours = hours if hours is not None else [{"time": (NOW + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%MZ"), "wind": 25.0, "dir": 250.0}]
    db.execute(
        "INSERT OR REPLACE INTO risk_hourly(comuna_code, computed_at, payload) VALUES (?,?,?)",
        (code, _stamp(computed_at), json.dumps(hours)),
    )


def test_ffmc_fallback_prefers_the_most_recent_day(tmp_path):
    """Sin FFMC de hoy el escenario usa el día más reciente, no el más viejo guardado."""
    db = Database(tmp_path / "brasa.db")
    today = NOW.astimezone(CHILE).date()
    _fwi(db, (today - timedelta(days=10)).isoformat(), ffmc=50.0)
    _fwi(db, (today - timedelta(days=1)).isoformat(), ffmc=88.0)
    _wind(db)
    sp = spread.estimate(db, INCIDENTE, NOW)
    assert sp is not None
    assert sp["ffmc"] == 88.0
    assert sp["ffmc_date"] == (today - timedelta(days=1)).isoformat()


def test_a_forecast_day_is_not_used_as_todays_ffmc(tmp_path):
    """`fwi_daily` guarda días pronosticados: el escenario no toma el de mañana como el de hoy."""
    db = Database(tmp_path / "brasa.db")
    today = NOW.astimezone(CHILE).date()
    _fwi(db, today.isoformat(), ffmc=88.0)
    _fwi(db, (today + timedelta(days=2)).isoformat(), ffmc=50.0)
    _wind(db)
    sp = spread.estimate(db, INCIDENTE, NOW)
    assert sp is not None
    assert sp["ffmc"] == 88.0 and sp["ffmc_date"] == today.isoformat()


def test_forecast_days_away_yields_no_scenario(tmp_path):
    """Un pronóstico cuya hora más cercana es de hace tres días ya no es «el viento de ahora»."""
    db = Database(tmp_path / "brasa.db")
    _fwi(db, NOW.astimezone(CHILE).date().isoformat())
    _wind(db, hours=[{"time": (NOW - timedelta(days=3)).strftime("%Y-%m-%dT%H:%MZ"), "wind": 25.0, "dir": 250.0}])
    assert spread.estimate(db, INCIDENTE, NOW) is None


def test_today_is_the_day_in_chile_not_in_utc(tmp_path):
    """«Hoy» es la fecha de Chile: a las 02:30 UTC todavía son las 23:30 del día anterior.

    Con la fecha UTC se preferiría el FFMC del 16 («hoy» UTC) sobre el del 14 (hoy en Chile).
    """
    db = Database(tmp_path / "brasa.db")
    now = datetime(2026, 1, 15, 2, 30, tzinfo=timezone.utc)  # 2026-01-14 23:30 en Chile
    _fwi(db, "2026-01-14", ffmc=88.0)  # hoy en Chile
    _fwi(db, "2026-01-16", ffmc=50.0)  # pasado mañana en Chile
    _wind(db, computed_at=now, hours=[{"time": "2026-01-15T04:00Z", "wind": 25.0, "dir": 250.0}])
    sp = spread.estimate(db, INCIDENTE, now)
    assert sp is not None
    assert sp["ffmc_date"] == "2026-01-14" and sp["ffmc"] == 88.0


def test_the_closest_forecast_hour_is_used(tmp_path):
    """El viento sale de la hora pronosticada más cercana a ahora (UTC), no de la primera."""
    db = Database(tmp_path / "brasa.db")
    _fwi(db, NOW.astimezone(CHILE).date().isoformat())
    _wind(
        db,
        hours=[
            {"time": (NOW + timedelta(hours=5)).strftime("%Y-%m-%dT%H:%MZ"), "wind": 99.0, "dir": 250.0},
            {"time": (NOW + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%MZ"), "wind": 20.0, "dir": 250.0},
        ],
    )
    sp = spread.estimate(db, INCIDENTE, NOW)
    assert sp is not None and sp["wind_kmh"] == 20.0

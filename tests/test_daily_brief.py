"""ALR-04: aviso preventivo diario — «hoy hay condiciones» una vez al día, desde las 08:00
de Chile, solo para los lugares que lo pidieron (`daily_brief`) y solo si su comuna tiene
Botón Rojo hoy (pronóstico oficial de CONAF) o riesgo 30-30-30 «alto»/«extremo».

Siempre «aviso», nunca «urgente»: es una prevención de zona, no un foco medido. El «una
por lugar y día» lo garantiza el `observation_id` `daily:<fecha>` y la marca `daily_brief_at`.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

from backend import alerts as alerts_mod
from backend.db import Database

NOW = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)   # 09:00 en Chile (UTC-3, horario de verano)
TODAY = "2026-10-19"                                      # el mismo día en hora local


def _place(db: Database, daily_brief: int = 1, comuna: int | None = 5109, older_adult: int = 0) -> None:
    db.execute("INSERT INTO subscribers(id, created_at) VALUES ('s1','2026-10-01T00:00:00Z')")
    db.execute("INSERT INTO places(id, subscriber_id, name, kind, lat, lon, radius_km, comuna_code, "
               "daily_brief, older_adult, created_at) "
               "VALUES ('p1','s1','Casa','casa',-33.02,-71.55,10,?,?,?,'2026-10-01T00:00:00Z')",
               (comuna, daily_brief, older_adult))


def _boton_rojo(db: Database, comuna: int = 5109, date: str = TODAY) -> None:
    db.execute("INSERT INTO boton_rojo(comuna_code, date, hours, area_ha, proportion, fetched_at) "
               "VALUES (?,?,6,120.0,0.4,?)", (comuna, date, "2026-10-19T01:00:00Z"))


def _risk(db: Database, level: str, comuna: int = 5109, date: str = TODAY) -> None:
    db.execute("INSERT INTO risk_daily(comuna_code, date, level, score, hours_3of3, hours_2of3, computed_at) "
               "VALUES (?,?,?,5,4,3,?)", (comuna, date, level, "2026-10-19T01:00:00Z"))


def test_boton_rojo_today_after_8am_creates_one_alert_and_never_two(make_client):
    """(1) Botón Rojo hoy y ya pasadas las 08:00 de Chile → 1 aviso; las pasadas siguientes no duplican."""
    with make_client(GOES_ENABLED="0") as client:
        svc = client.app.state.services
        db = svc.db
        _place(db)
        _boton_rojo(db)
        assert asyncio.run(svc.daily_brief(NOW)) == 1
        [row] = db.query("SELECT * FROM alerts")
        assert row["observation_id"] == f"daily:{TODAY}" and row["level"] == "aviso"
        assert row["delivered_at"]            # deliver la marcó intentada en el mismo paso
        payload = json.loads(row["payload"])
        assert payload["level"] == "aviso" and payload["footer"] and payload["kind"] == "diario"
        # Ni la pasada del ciclo siguiente ni una evaluación repetida ese día la duplican.
        assert asyncio.run(svc.daily_brief(NOW + timedelta(minutes=10))) == 0
        assert asyncio.run(alerts_mod.evaluate_daily(db, NOW + timedelta(minutes=10))) == []
        assert db.one("SELECT COUNT(*) AS n FROM alerts")["n"] == 1


def test_without_risk_nothing_is_sent(make_client):
    """(2) Ni Botón Rojo ni 30-30-30 alto/extremo: el día no lo justifica y no se crea ninguna."""
    with make_client(GOES_ENABLED="0") as client:
        svc = client.app.state.services
        db = svc.db
        _place(db)
        _risk(db, "bajo")
        assert asyncio.run(svc.daily_brief(NOW)) == 0
        assert db.one("SELECT id FROM alerts") is None


def test_the_level_is_always_aviso(make_client):
    """(3) Ni el riesgo «extremo» ni una persona mayor en el lugar lo suben a «urgente»."""
    with make_client(GOES_ENABLED="0") as client:
        svc = client.app.state.services
        db = svc.db
        _place(db, older_adult=1)
        _risk(db, "extremo")
        assert asyncio.run(svc.daily_brief(NOW)) == 1
        row = db.one("SELECT * FROM alerts")
        assert row["level"] == "aviso"


def test_a_place_that_did_not_opt_in_gets_nothing(make_client):
    """(4) `daily_brief = 0`: el aviso preventivo es opcional por lugar."""
    with make_client(GOES_ENABLED="0") as client:
        svc = client.app.state.services
        db = svc.db
        _place(db, daily_brief=0)
        _boton_rojo(db)
        _risk(db, "extremo")
        assert asyncio.run(svc.daily_brief(NOW)) == 0
        assert db.one("SELECT id FROM alerts") is None


def test_before_8am_chile_nothing_is_sent_and_the_day_stays_open(make_client):
    """Antes de las 08:00 la pasada no corre ni marca el día: a la hora sí avisa."""
    early = NOW - timedelta(hours=2)   # 07:00 en Chile
    with make_client(GOES_ENABLED="0") as client:
        svc = client.app.state.services
        db = svc.db
        _place(db)
        _boton_rojo(db)
        assert asyncio.run(svc.daily_brief(early)) == 0
        assert db.one("SELECT id FROM alerts") is None
        assert db.kv_get("daily_brief_at") is None
        assert asyncio.run(svc.daily_brief(NOW)) == 1

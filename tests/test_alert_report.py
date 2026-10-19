"""ALR-03: un reporte ciudadano recién verificado avisa a los lugares cercanos.

Cuando la moderación marca un reporte como «verificado», los lugares guardados a ≤ 5 km
(y dentro de su radio) reciben un aviso «Un vecino informó… (revisado por BRASA)». Siempre
nivel «aviso»: la revisión humana no reemplaza la evidencia satelital ni a CONAF. Del vecino
no sale nada: ni foto, ni descripción, ni nota del moderador, ni identidad.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from backend import alerts
from backend.db import Database

NOW = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)


def _db(tmp_path, radius=10):
    db = Database(tmp_path / "brasa.db")
    db.execute("INSERT INTO subscribers(id, created_at) VALUES ('s1','2026-10-01T00:00:00Z')")
    db.execute("INSERT INTO places(id, subscriber_id, name, kind, lat, lon, radius_km, created_at) "
               "VALUES ('p1','s1','Casa','casa',-33.05,-71.55,?,'2026-10-01T00:00:00Z')", (radius,))
    return db


def _report(**kw):
    return {"id": "r1", "created_at": NOW.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "lat": -33.05, "lon": -71.52,   # ~2,8 km al este de «Casa»
            "kind": "humo", "status": "verificado", "description": "Columna de humo detrás del cerro",
            "photo": "r1.jpg", "subscriber_id": "s9", "moderator_note": "confirmado por teléfono", **kw}


def test_verified_report_within_5km_creates_one_aviso(tmp_path):
    db = _db(tmp_path)
    created = alerts.evaluate_report(db, _report(), now=NOW)
    assert len(created) == 1
    row = db.one("SELECT * FROM alerts")
    assert row["observation_id"] == "report:r1"
    assert row["level"] == "aviso"
    payload = json.loads(row["payload"])
    assert "Un vecino informó humo visible" in payload["body"]
    assert "revisado por BRASA" in payload["body"]
    assert "SENAPRED" in payload["footer"]
    # Nada del vecino se filtra: sin foto, sin descripción, sin nota, sin identidad.
    leaked = json.dumps(payload, ensure_ascii=False)
    for private in ("r1.jpg", "s9", "confirmado por teléfono", "Columna de humo detrás del cerro"):
        assert private not in leaked


def test_a_place_beyond_5km_gets_no_alert_even_inside_its_radius(tmp_path):
    """El radio del lugar puede ser 20 km: el aviso vecinal se queda en 5 km."""
    db = _db(tmp_path, radius=20)
    far = _report(lat=-33.16, lon=-71.55)   # ~12 km al sur
    assert alerts.evaluate_report(db, far, now=NOW) == []
    assert db.one("SELECT id FROM alerts") is None


def test_a_discarded_report_creates_no_alert(tmp_path):
    db = _db(tmp_path)
    assert alerts.evaluate_report(db, _report(status="descartado"), now=NOW) == []
    assert db.one("SELECT id FROM alerts") is None


def test_a_report_older_than_max_age_creates_no_alert(tmp_path):
    db = _db(tmp_path)
    old = _report(created_at=(NOW - timedelta(hours=8)).strftime("%Y-%m-%dT%H:%M:%SZ"))
    assert alerts.evaluate_report(db, old, now=NOW) == []
    assert db.one("SELECT id FROM alerts") is None

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
    # `observed_at` es el momento del aviso (no el del reporte): con él `deliver` recupera
    # los pendientes aunque el reporte esté cerca de su límite de edad al verificarse.
    assert row["observed_at"] == NOW.strftime("%Y-%m-%dT%H:%M:%SZ")
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


def test_each_kind_uses_its_own_validity_window(tmp_path):
    """Una quema sigue vigente 72 h: verificarla a las 8 h tiene que avisar igual."""
    db = _db(tmp_path)
    old = _report(kind="quema", created_at=(NOW - timedelta(hours=8)).strftime("%Y-%m-%dT%H:%M:%SZ"))
    assert len(alerts.evaluate_report(db, old, now=NOW)) == 1


def test_batch_verification_also_creates_the_alert(make_client):
    """El lote es el camino real de los voluntarios: aprobar ahí también avisa (ALR-03)."""
    with make_client(ADMIN_TOKEN="admin-secret-token-999") as client:
        svc = client.app.state.services
        svc.db.execute("INSERT INTO subscribers(id, created_at) VALUES ('s1','2026-10-01T00:00:00Z')")
        svc.db.execute("INSERT INTO places(id, subscriber_id, name, kind, lat, lon, radius_km, created_at) "
                       "VALUES ('p1','s1','Casa','casa',-33.05,-71.55,10,'2026-10-01T00:00:00Z')")
        created = client.post("/api/reports", data={"lat": "-33.05", "lon": "-71.52", "kind": "humo"}).json()
        body = client.post("/api/admin/reports/batch", headers={"X-Admin-Token": "admin-secret-token-999"},
                           json={"ids": [created["id"]], "status": "verificado"}).json()
        assert body["alerts_created"] == 1
        row = svc.db.one("SELECT * FROM alerts")
        assert row["observation_id"] == f"report:{created['id']}"


def test_two_reports_of_the_same_fire_share_one_aviso(tmp_path):
    """Reportes a menos de 2 km entre sí apuntan a la misma columna de humo: un solo aviso."""
    db = _db(tmp_path)
    first = _report(id="r1", lat=-33.042)    # ~0,9 km al norte de «Casa»
    second = _report(id="r2", lat=-33.058)   # ~0,9 km al sur; ~1,8 km entre sí
    assert len(alerts.evaluate_report(db, first, now=NOW)) == 1
    assert alerts.evaluate_report(db, second, now=NOW + timedelta(minutes=10)) == []
    assert db.one("SELECT COUNT(*) AS n FROM alerts")["n"] == 1


def test_a_second_fire_kilometers_away_alerts_the_same_place(tmp_path):
    """REV-10: la ventana de deduplicación no silencia un incendio distinto.

    Los dos reportes caen dentro del radio del lugar pero están a ~8 km entre sí:
    no son el mismo fuego y el segundo tiene que avisar igual.
    """
    db = _db(tmp_path)
    first = _report(id="r1", lat=-33.02, lon=-71.55)   # ~3,3 km al norte de «Casa»
    second = _report(id="r2", lat=-33.09, lon=-71.55)  # ~4,4 km al sur; ~7,8 km entre sí
    assert len(alerts.evaluate_report(db, first, now=NOW)) == 1
    created = alerts.evaluate_report(db, second, now=NOW + timedelta(minutes=10))
    assert len(created) == 1
    assert created[0]["payload"]["observation"]["id"] == "report:r2"
    assert db.one("SELECT COUNT(*) AS n FROM alerts")["n"] == 2


def test_a_fire_twenty_km_away_alerts_its_own_neighbors(tmp_path):
    """Dos fuegos a ~20 km en la misma ventana generan un aviso por cada lugar cercano."""
    db = _db(tmp_path)
    db.execute("INSERT INTO places(id, subscriber_id, name, kind, lat, lon, radius_km, created_at) "
               "VALUES ('p2','s1','Parcela','casa',-33.24,-71.55,10,'2026-10-01T00:00:00Z')")
    first = _report(id="r1")                              # ~2,8 km de «Casa»
    second = _report(id="r2", lat=-33.23, lon=-71.52)     # ~20 km al sur del primero, ~3 km de «Parcela»
    assert len(alerts.evaluate_report(db, first, now=NOW)) == 1
    created = alerts.evaluate_report(db, second, now=NOW + timedelta(minutes=10))
    assert len(created) == 1
    assert created[0]["payload"]["place"]["id"] == "p2"
    assert db.one("SELECT COUNT(*) AS n FROM alerts")["n"] == 2


def test_reverifying_an_already_verified_report_creates_no_second_alert(make_client):
    """Aprobar en lote un reporte ya verificado no avisa dos veces."""
    with make_client(ADMIN_TOKEN="admin-secret-token-999") as client:
        svc = client.app.state.services
        svc.db.execute("INSERT INTO subscribers(id, created_at) VALUES ('s1','2026-10-01T00:00:00Z')")
        svc.db.execute("INSERT INTO places(id, subscriber_id, name, kind, lat, lon, radius_km, created_at) "
                       "VALUES ('p1','s1','Casa','casa',-33.05,-71.55,10,'2026-10-01T00:00:00Z')")
        created = client.post("/api/reports", data={"lat": "-33.05", "lon": "-71.52", "kind": "humo"}).json()
        headers = {"X-Admin-Token": "admin-secret-token-999"}
        client.post(f"/api/admin/reports/{created['id']}", headers=headers, json={"status": "verificado"})
        assert svc.db.one("SELECT COUNT(*) AS n FROM alerts")["n"] == 1
        body = client.post("/api/admin/reports/batch", headers=headers,
                           json={"ids": [created["id"]], "status": "verificado"}).json()
        assert body["alerts_created"] == 0
        assert svc.db.one("SELECT COUNT(*) AS n FROM alerts")["n"] == 1

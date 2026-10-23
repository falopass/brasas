"""MZ-01: el resumen del lugar trae `trend` del comparador semana a semana."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

HOY = datetime.now(ZoneInfo("America/Santiago")).date()
HACE7 = HOY - timedelta(days=7)


def _seed(db, comuna_code=7101):
    db.execute("INSERT INTO subscribers(id, created_at) VALUES ('ssssssssssssssssssssssss','2026-01-01T00:00:00Z')")
    db.execute("INSERT INTO places(id, subscriber_id, name, kind, lat, lon, radius_km, comuna_code, created_at) "
               "VALUES ('p1','ssssssssssssssssssssssss','Casa','casa',-35.42,-71.66,5,7101,'2026-01-01T00:00:00Z')")
    for i in range(7):
        db.execute("INSERT OR REPLACE INTO risk_daily(comuna_code, date, level, score, hours_3of3, hours_2of3, computed_at) "
                   "VALUES (?,?,?,?,?,?,?)", (7101, (HOY + timedelta(days=i)).isoformat(), "alto", 70, 0, 0, "2026-10-23T12:00:00Z"))
        db.execute("INSERT OR REPLACE INTO risk_snapshot(snapshot_date, comuna_code, target_date, level, level_combined, score) "
                   "VALUES (?,?,?,?,?,?)", (HACE7.isoformat(), 7101, HOY.isoformat(), "extremo", "extremo", 90))


def test_el_resumen_trae_la_comparacion(make_client):
    with make_client() as client:
        db = client.app.state.services.db
        _seed(db)
        body = client.get("/api/places/p1/summary", headers={"X-Brasa-Token": "ssssssssssssssssssssssss"}).json()
    hoy = next((r for r in body["trend"]["rows"] if r["target_date"] == HOY.isoformat()), None)
    assert hoy["change"] == "baja"  # de extremo a alto
    assert "change_label" in hoy


def test_sin_foto_anterior_solo_dice_sin_anterior(make_client):
    with make_client() as client:
        db = client.app.state.services.db
        db.execute("INSERT INTO subscribers(id, created_at) VALUES ('ssssssssssssssssssssssss','2026-01-01T00:00:00Z')")
        db.execute("INSERT INTO places(id, subscriber_id, name, kind, lat, lon, radius_km, comuna_code, created_at) "
                   "VALUES ('p1','ssssssssssssssssssssssss','Casa','casa',-35.42,-71.66,5,7101,'2026-01-01T00:00:00Z')")
        db.execute("INSERT INTO risk_daily(comuna_code, date, level, score, hours_3of3, hours_2of3, computed_at) "
                   "VALUES (7101,?, 'alto', 70, 0, 0, '2026-10-23T12:00:00Z')", (HOY.isoformat(),))
        body = client.get("/api/places/p1/summary", headers={"X-Brasa-Token": "ssssssssssssssssssssssss"}).json()
    assert body["trend"]["summary"]["sin_anterior"] == 1 and not body["trend"]["summary"]["sube"]


def test_lugar_sin_comuna_trae_trend_vacio(make_client):
    with make_client() as client:
        db = client.app.state.services.db
        db.execute("INSERT INTO subscribers(id, created_at) VALUES ('ssssssssssssssssssssssss','2026-01-01T00:00:00Z')")
        db.execute("INSERT INTO places(id, subscriber_id, name, kind, lat, lon, radius_km, created_at) "
                   "VALUES ('p1','ssssssssssssssssssssssss','Cerro','cerro',-35.42,-71.66,5,'2026-01-01T00:00:00Z')")
        body = client.get("/api/places/p1/summary", headers={"X-Brasa-Token": "ssssssssssssssssssssssss"}).json()
    assert body["trend"]["rows"] == [] and body["trend"]["summary"]["sin_anterior"] == 7

"""VEC-01/UX-56: el enlace de familia trae el comparador en `trend` sin otra llamada."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

HOY = datetime.now(ZoneInfo("America/Santiago")).date()
HACE7 = HOY - timedelta(days=7)
TOKEN = "t" * 24


def _seed(db):
    db.execute("INSERT INTO subscribers(id, created_at) VALUES ('ssssssssssssssssssssssss','2026-01-01T00:00:00Z')")
    db.execute("INSERT INTO places(id, subscriber_id, name, kind, lat, lon, radius_km, comuna_code, share_token, created_at) "
               f"VALUES ('p1','ssssssssssssssssssssssss','Casa','casa',-35.42,-71.66,5,7101,'{TOKEN}','2026-01-01T00:00:00Z')")


def test_sin_foto_anterior_no_afirma_cambio(make_client):
    with make_client() as client:
        db = client.app.state.services.db
        _seed(db)
        body = client.get(f"/api/shared/{TOKEN}").json()
    assert body["trend"]["summary"]["sin_anterior"] == 7 and body["trend"]["rows"] == []


def test_con_foto_mas_alta_el_cambio_es_baja(make_client):
    with make_client() as client:
        db = client.app.state.services.db
        _seed(db)
        db.execute("INSERT INTO risk_daily(comuna_code, date, level, score, hours_3of3, hours_2of3, computed_at) "
                   "VALUES (7101,?, 'alto', 70, 0, 0, '2026-10-23T12:00:00Z')", (HOY.isoformat(),))
        db.execute("INSERT INTO risk_snapshot(snapshot_date, comuna_code, target_date, level, level_combined, score) "
                   "VALUES (?,7101,?, 'extremo','extremo', 90)", (HACE7.isoformat(), HOY.isoformat()))
        body = client.get(f"/api/shared/{TOKEN}").json()
    hoy = next((r for r in body["trend"]["rows"] if r["target_date"] == HOY.isoformat()), None)
    assert hoy["change"] == "baja" and "semana pasada" in hoy["change_label"]
    assert set(body) >= {"place", "status", "trend", "risk_days"}  # las claves de antes, más trend

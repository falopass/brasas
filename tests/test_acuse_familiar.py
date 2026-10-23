"""UX-48: el acuse «Estoy bien» se guarda por lugar, caduca a las 12 h y muere con el enlace."""
from datetime import datetime, timedelta, timezone

TOKEN = "t" * 24


def _seed(db):
    db.execute("INSERT INTO subscribers(id, created_at) VALUES ('ssssssssssssssssssssssss','2026-01-01T00:00:00Z')")
    db.execute("INSERT INTO places(id, subscriber_id, name, kind, lat, lon, radius_km, share_token, created_at) "
               f"VALUES ('p1','ssssssssssssssssssssssss','Casa','casa',-35.42,-71.66,5,'{TOKEN}','2026-01-01T00:00:00Z')")


def test_el_acuse_aparece_en_el_enlace(make_client):
    with make_client() as client:
        db = client.app.state.services.db
        _seed(db)
        r = client.post(f"/api/shared/{TOKEN}/estoy-bien")
        assert r.status_code == 200 and r.json()["at"]
        assert client.get(f"/api/shared/{TOKEN}").json()["estoy_bien"]["at"] == r.json()["at"]


def test_el_acuse_caduca_a_las_12h(make_client):
    with make_client() as client:
        db = client.app.state.services.db
        _seed(db)
        viejo = (datetime.now(timezone.utc) - timedelta(hours=13)).strftime("%Y-%m-%dT%H:%M:%SZ")
        db.execute("INSERT INTO family_acks(place_id, share_token, created_at) VALUES ('p1',?,?)", (TOKEN, viejo))
        assert client.get(f"/api/shared/{TOKEN}").json()["estoy_bien"] is None


def test_token_desconocido_o_revocado_da_404(make_client):
    with make_client() as client:
        db = client.app.state.services.db
        _seed(db)
        assert client.post("/api/shared/no-existe-este-token-xxx/estoy-bien").status_code == 404
        client.delete("/api/places/p1/share", headers={"X-Brasa-Token": "ssssssssssssssssssssssss"})
        assert client.post(f"/api/shared/{TOKEN}/estoy-bien").status_code == 404


def test_el_acuse_muere_con_el_lugar_y_con_el_borrado(make_client):
    with make_client() as client:
        db = client.app.state.services.db
        _seed(db)
        client.post(f"/api/shared/{TOKEN}/estoy-bien")
        client.delete("/api/me", headers={"X-Brasa-Token": "ssssssssssssssssssssssss"})
        assert db.one("SELECT COUNT(*) AS n FROM family_acks")["n"] == 0

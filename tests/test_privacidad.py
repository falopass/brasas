"""Derechos y privacidad (Ola 3): exportar los datos del dispositivo, borrado en cascada
y retención de avisos y reportes (SEC-02, FIX-21, FIX-22, Ley 21.719)."""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

STAMP = "%Y-%m-%dT%H:%M:%SZ"


def seed_device(client, *, with_alert=True, older_adult=True):
    """Dispositivo con un lugar marcado «persona mayor», enlace familiar y un aviso."""
    svc = client.app.state.services
    token = client.post("/api/subscribers").json()["token"]
    headers = {"X-Brasa-Token": token}
    place = client.post("/api/places", json={"name": "Casa", "lat": -33.05, "lon": -71.55,
                                           "radius_km": 10, "older_adult": older_adult},
                        headers=headers).json()
    client.post(f"/api/places/{place['id']}/share", headers=headers)
    if with_alert:
        moment = datetime.now(timezone.utc).strftime(STAMP)
        payload = {"title": "Foco de calor", "place": {"name": "Casa"}, "distance_km": 3.2, "url": "/#/mapa"}
        svc.db.execute(
            "INSERT INTO alerts(place_id, observation_id, level, distance_km, bearing_deg, upwind, lat, lon, "
            "observed_at, created_at, payload, delivered) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (place["id"], "obs-1", "urgente", 3.2, 90, 1, -33.06, -71.54,
             moment, moment, json.dumps(payload), json.dumps(["push"])))
    return headers, place


def test_export_returns_everything_of_the_device(make_client):
    with make_client() as client:
        headers, place = seed_device(client)
        body = client.get("/api/me/export", headers=headers)
        assert body.status_code == 200
        assert "attachment" in body.headers["content-disposition"]
        data = body.json()
        assert data["dispositivo"]["id"] == headers["X-Brasa-Token"]  # el identificador también es su dato
        assert data["dispositivo"]["registrado_at"]
        assert [p["id"] for p in data["lugares"]] == [place["id"]]
        assert data["lugares"][0]["older_adult"] is True
        assert data["lugares"][0]["share_token"]  # el enlace familiar también es su dato
        assert len(data["avisos"]) == 1 and data["avisos"][0]["payload"]["title"] == "Foco de calor"
        assert data["avisos"][0]["delivered"] == ["push"]
        assert data["nota"]  # los reportes van sin identificador: la limitación se declara


def test_export_and_delete_require_the_device_token(make_client):
    with make_client() as client:
        assert client.get("/api/me/export").status_code == 401
        assert client.delete("/api/me").status_code == 401


def test_delete_me_cascades_and_revokes_the_token(make_client):
    with make_client() as client:
        headers, place = seed_device(client)
        svc = client.app.state.services
        svc.db.execute("UPDATE subscribers SET push_endpoint='e', push_p256dh='p', push_auth='a', "
                       "telegram_chat_id='123' WHERE id = ?", (headers["X-Brasa-Token"],))
        assert client.delete("/api/me", headers=headers).json() == {"ok": True}
        assert svc.db.one("SELECT COUNT(*) AS n FROM subscribers")["n"] == 0
        assert svc.db.one("SELECT COUNT(*) AS n FROM places")["n"] == 0
        assert svc.db.one("SELECT COUNT(*) AS n FROM alerts")["n"] == 0
        # El identificador ya no existe: el dispositivo queda fuera para siempre.
        assert client.get("/api/me", headers=headers).status_code == 401


def test_delete_me_leaves_other_devices_alone(make_client):
    with make_client() as client:
        headers, place = seed_device(client)
        other, other_place = seed_device(client, older_adult=False)
        client.delete("/api/me", headers=headers)
        assert client.get("/api/me", headers=other).status_code == 200
        assert client.get("/api/places", headers=other).json()["places"][0]["id"] == other_place["id"]


def _insert_report(db, rid, days, status, photo=None):
    moment = (datetime.now(timezone.utc) - timedelta(days=days)).strftime(STAMP)
    db.execute("INSERT INTO reports(id, created_at, lat, lon, kind, description, photo, status) VALUES "
               "(?, ?, -33.5, -70.8, 'humo', 'Humo en el cerro', ?, ?)", (rid, moment, photo, status))


def test_retention_purges_old_alerts_and_reports(make_client, tmp_path):
    with make_client() as client:
        svc = client.app.state.services
        headers, place = seed_device(client)
        svc.db.execute("UPDATE alerts SET created_at = ? WHERE place_id = ?",
                       ((datetime.now(timezone.utc) - timedelta(days=400)).strftime(STAMP), place["id"]))
        # Un reporte descartado de más de 90 días con foto, y otros dentro de plazo.
        (tmp_path / "data" / "uploads").mkdir(parents=True)
        photo = tmp_path / "data" / "uploads" / "vieja.jpg"
        photo.write_bytes(b"jpeg")
        _insert_report(svc.db, "descartado-viejo", 120, "descartado", photo="vieja.jpg")
        _insert_report(svc.db, "verificado-viejo", 800, "verificado")
        _insert_report(svc.db, "descartado-nuevo", 60, "descartado")
        _insert_report(svc.db, "verificado-nuevo", 100, "verificado")
        _insert_report(svc.db, "sin-verificar-viejo", 120, "no_verificado")

        result = asyncio.run(svc.purge_user_data())

        assert result == {"reports": 3, "alerts": 1, "photos": 1}
        kept = {r["id"] for r in svc.db.query("SELECT id FROM reports")}
        assert kept == {"descartado-nuevo", "verificado-nuevo"}
        assert svc.db.one("SELECT COUNT(*) AS n FROM alerts")["n"] == 0
        assert not photo.exists()
        # Los lugares y el dispositivo no se tocan: la retención no borra cuentas vivas.
        assert svc.db.one("SELECT COUNT(*) AS n FROM places")["n"] == 1
        assert svc.db.one("SELECT COUNT(*) AS n FROM subscribers")["n"] == 1


def test_retention_retries_photo_purge_after_remote_failure(make_client, tmp_path):
    """Si el vaciado remoto de la foto falla, el reporte se conserva y el próximo ciclo lo reintenta."""
    with make_client() as client:
        svc = client.app.state.services
        seed_device(client)
        (tmp_path / "data" / "uploads").mkdir(parents=True)
        (tmp_path / "data" / "uploads" / "foto.jpg").write_bytes(b"jpeg")
        _insert_report(svc.db, "con-foto", 120, "descartado", photo="foto.jpg")

        class FlakyStorage:
            calls = 0

            async def put(self, key, content, content_type=""):
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("R2 caído")

        svc.storage = FlakyStorage()
        assert asyncio.run(svc.purge_user_data()) == {"reports": 0, "alerts": 0, "photos": 0}
        assert svc.db.one("SELECT COUNT(*) AS n FROM reports")["n"] == 1  # se conserva para reintentar
        assert asyncio.run(svc.purge_user_data()) == {"reports": 1, "alerts": 0, "photos": 1}
        assert svc.db.one("SELECT COUNT(*) AS n FROM reports")["n"] == 0


def test_retention_keeps_recent_history(make_client):
    with make_client() as client:
        headers, place = seed_device(client)
        svc = client.app.state.services
        _insert_report(svc.db, "reciente", 10, "verificado")
        assert asyncio.run(svc.purge_user_data()) == {"reports": 0, "alerts": 0, "photos": 0}
        assert svc.db.one("SELECT COUNT(*) AS n FROM alerts")["n"] == 1
        assert svc.db.one("SELECT COUNT(*) AS n FROM reports")["n"] == 1

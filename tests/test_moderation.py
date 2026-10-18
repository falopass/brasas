"""Moderación ágil: caducidad, lote, respuesta al autor y duplicados.

Lo operable ya estaba (cola con ADMIN_TOKEN, foto solo con token mientras no se aprueba). Estas
pruebas cubren lo que faltaba para que la cola no se llene de trabajo inútil.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend import reports as reports_mod
from backend.routes.common import limiter

ADMIN = {"X-Admin-Token": "admin-secret-token-999"}
STAMP = "%Y-%m-%dT%H:%M:%SZ"
SPOT = {"lat": "-33.05", "lon": "-71.55", "kind": "humo", "description": "Columna de humo"}


@pytest.fixture(autouse=True)
def fresh_limits():
    """El limitador es por proceso: sin esto, un test agota el cupo de reportes de los demás."""
    limiter.hits.clear()
    yield
    limiter.hits.clear()


def new_report(client, **extra) -> dict:
    response = client.post("/api/reports", data={**SPOT, **extra})
    assert response.status_code == 201, response.text
    return response.json()


def test_a_report_nobody_reviewed_expires_and_is_not_lost(make_client):
    """Caduca como descartado con su motivo: queda el registro de que llegó y no se revisó."""
    with make_client(ADMIN_TOKEN=ADMIN["X-Admin-Token"]) as client:
        svc = client.app.state.services
        old = (datetime.now(timezone.utc) - timedelta(hours=reports_mod.EXPIRE_HOURS + 2)).strftime(STAMP)
        svc.db.execute("INSERT INTO reports(id, created_at, lat, lon, comuna_code, kind, description, status) "
                       "VALUES (?,?,?,?,?,?,?,?)",
                       ("viejo-1", old, -33.05, -71.55, 5109, "humo", "Nadie lo revisó", "no_verificado"))
        queue = client.get("/api/admin/reports", headers=ADMIN).json()
        assert queue["expired_now"] == 1 and queue["reports"] == []
        assert queue["expire_hours"] == reports_mod.EXPIRE_HOURS
        expired = client.get("/api/admin/reports?status=descartado", headers=ADMIN).json()["reports"]
        assert expired[0]["id"] == "viejo-1"
        assert "Caducó sin revisar" in expired[0]["moderator_note"]


def test_a_fresh_report_stays_in_the_queue(make_client):
    with make_client(ADMIN_TOKEN=ADMIN["X-Admin-Token"]) as client:
        created = new_report(client)
        queue = client.get("/api/admin/reports", headers=ADMIN).json()
        assert queue["expired_now"] == 0 and [r["id"] for r in queue["reports"]] == [created["id"]]


def test_batch_approves_several_reports_at_once(make_client):
    """El cuello de botella es humano: aprobar de a uno gasta el tiempo del voluntario."""
    with make_client(ADMIN_TOKEN=ADMIN["X-Admin-Token"]) as client:
        first = new_report(client, description="Humo en el cerro")
        second = new_report(client, lat="-33.20", lon="-71.40", description="Humo más al sur")
        body = client.post("/api/admin/reports/batch", headers=ADMIN,
                           json={"ids": [first["id"], second["id"]], "status": "verificado", "note": "Vistos en la cámara"}).json()
        assert body == {"ok": True, "status": "verificado", "requested": 2, "updated": 2}
        public = client.get("/api/reports").json()["reports"]
        assert {r["id"] for r in public} == {first["id"], second["id"]}
        assert all(r["status_label"] == "Verificado" for r in public)


def test_batch_cannot_moderate_without_the_admin_token(make_client):
    with make_client(ADMIN_TOKEN=ADMIN["X-Admin-Token"]) as client:
        created = new_report(client)
        assert client.post("/api/admin/reports/batch",
                           json={"ids": [created["id"]], "status": "verificado"}).status_code == 403
        assert client.post("/api/admin/reports/batch", headers=ADMIN,
                           json={"ids": [], "status": "verificado"}).status_code == 422


def test_the_author_learns_what_happened_to_their_report(make_client):
    """Quien reporta humo tiene que poder saber si su aviso sirvió."""
    with make_client(ADMIN_TOKEN=ADMIN["X-Admin-Token"]) as client:
        token = client.post("/api/subscribers").json()["token"]
        device = {"X-Brasa-Token": token}
        created = client.post("/api/reports", data=SPOT, headers=device).json()
        mine = client.get("/api/reports/mine", headers=device).json()
        assert mine["total"] == 1 and mine["reports"][0]["status"] == "no_verificado"
        assert mine["reports"][0]["status_label"] == "En revisión"
        client.post(f"/api/admin/reports/{created['id']}", headers=ADMIN,
                    json={"status": "verificado", "note": "Confirmado con la cámara del cerro"})
        mine = client.get("/api/reports/mine", headers=device).json()
        assert mine["reports"][0]["status"] == "verificado"
        assert mine["reports"][0]["moderator_note"] == "Confirmado con la cámara del cerro"


def test_mine_only_shows_your_own_reports(make_client):
    with make_client() as client:
        device = client.post("/api/subscribers").json()["token"]
        client.post("/api/reports", data=SPOT, headers={"X-Brasa-Token": device})
        other = client.post("/api/subscribers").json()["token"]
        assert client.get("/api/reports/mine", headers={"X-Brasa-Token": other}).json()["total"] == 0
        assert client.get("/api/reports/mine").status_code == 401


def test_two_reports_of_the_same_spot_do_not_fill_the_queue(make_client):
    """El mismo hecho avisado dos veces es una fila, no dos."""
    with make_client() as client:
        first = new_report(client)
        second = client.post("/api/reports", data={**SPOT, "description": "Otra vez humo"}).json()
        assert second["duplicate"] is True and second["id"] == first["id"]
        assert client.app.state.services.db.one("SELECT COUNT(*) AS n FROM reports")["n"] == 1


def test_a_different_kind_or_far_away_is_not_a_duplicate(make_client):
    with make_client() as client:
        first = new_report(client)
        llamas = client.post("/api/reports", data={**SPOT, "kind": "llamas"}).json()
        lejos = client.post("/api/reports", data={"lat": "-35.00", "lon": "-71.55", "kind": "humo"}).json()
        assert llamas["duplicate"] is False and lejos["duplicate"] is False
        assert len({first["id"], llamas["id"], lejos["id"]}) == 3


def test_expiry_rules_are_explicit():
    now = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)
    assert reports_mod.expired((now - timedelta(hours=1)).strftime(STAMP), now) is False
    assert reports_mod.expired((now - timedelta(hours=7)).strftime(STAMP), now) is True
    assert reports_mod.expired("no es fecha", now) is False

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


def new_moderator(client, name: str = "Valesca") -> dict:
    """Alta con el token maestro: devuelve {id, name, token}; el token solo sale esta vez."""
    response = client.post("/api/admin/moderators", headers=ADMIN, json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()


def test_a_report_nobody_reviewed_expires_and_is_not_lost(make_client):
    """Caduca como descartado con su motivo: queda el registro de que llegó y no se revisó."""
    with make_client(ADMIN_TOKEN=ADMIN["X-Admin-Token"]) as client:
        svc = client.app.state.services
        old = (datetime.now(timezone.utc) - timedelta(hours=reports_mod.EXPIRE_HOURS + 2)).strftime(STAMP)
        svc.db.execute(
            "INSERT INTO reports(id, created_at, lat, lon, comuna_code, kind, description, status) VALUES (?,?,?,?,?,?,?,?)",
            ("viejo-1", old, -33.05, -71.55, 5109, "humo", "Nadie lo revisó", "no_verificado"),
        )
        queue = client.get("/api/admin/reports", headers=ADMIN).json()
        assert queue["expired_now"] == 1 and queue["reports"] == []
        assert queue["expire_hours"] == reports_mod.EXPIRE_HOURS_BY_KIND
        expired = client.get("/api/admin/reports?status=descartado", headers=ADMIN).json()["reports"]
        assert expired[0]["id"] == "viejo-1"
        assert "Caducó sin revisar" in expired[0]["moderator_note"]


def test_each_kind_expires_in_its_own_window(make_client):
    """Las llamas siguen vigentes al día siguiente y una quema dura días; el humo se disipa en horas."""
    with make_client(ADMIN_TOKEN=ADMIN["X-Admin-Token"]) as client:
        svc = client.app.state.services
        now = datetime.now(timezone.utc)

        def old(hours: float) -> str:
            return (now - timedelta(hours=hours)).strftime(STAMP)

        rows = [
            ("h8", "humo", old(8)),
            ("l8", "llamas", old(8)),
            ("l30", "llamas", old(30)),
            ("q70", "quema", old(70)),
            ("q80", "quema", old(80)),
            ("o30", "otro", old(30)),
        ]
        for report_id, kind, created in rows:
            svc.db.execute(
                "INSERT INTO reports(id, created_at, lat, lon, comuna_code, kind, description, status) VALUES (?,?,?,?,?,?,?,?)",
                (report_id, created, -33.05, -71.55, 5109, kind, "x", "no_verificado"),
            )
        queue = client.get("/api/admin/reports", headers=ADMIN).json()
        assert queue["expired_now"] == 4
        assert {r["id"] for r in queue["reports"]} == {"l8", "q70"}
        assert queue["expire_hours"] == reports_mod.EXPIRE_HOURS_BY_KIND
        discarded = client.get("/api/admin/reports?status=descartado", headers=ADMIN).json()["reports"]
        assert {r["id"] for r in discarded} == {"h8", "l30", "q80", "o30"}
        assert all(r["moderator_note"] == reports_mod.EXPIRED_NOTE for r in discarded)


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
        body = client.post(
            "/api/admin/reports/batch",
            headers=ADMIN,
            json={"ids": [first["id"], second["id"]], "status": "verificado", "note": "Vistos en la cámara"},
        ).json()
        assert body == {"ok": True, "status": "verificado", "requested": 2, "updated": 2, "alerts_created": 0}
        public = client.get("/api/reports").json()["reports"]
        assert {r["id"] for r in public} == {first["id"], second["id"]}
        assert all(r["status_label"] == "Verificado" for r in public)


def test_batch_cannot_moderate_without_the_admin_token(make_client):
    with make_client(ADMIN_TOKEN=ADMIN["X-Admin-Token"]) as client:
        created = new_report(client)
        assert client.post("/api/admin/reports/batch", json={"ids": [created["id"]], "status": "verificado"}).status_code == 403
        assert client.post("/api/admin/reports/batch", headers=ADMIN, json={"ids": [], "status": "verificado"}).status_code == 422


def test_a_batch_also_marks_the_database_for_backup(make_client):
    """La conexión directa se salta el aviso de escritura: sin marcarlo, el lote no se respaldaba."""
    with make_client(ADMIN_TOKEN=ADMIN["X-Admin-Token"]) as client:
        svc = client.app.state.services
        created = new_report(client)
        calls = []
        original, svc.db.on_user_write = svc.db.on_user_write, lambda: calls.append(1)
        try:
            client.post("/api/admin/reports/batch", headers=ADMIN, json={"ids": [created["id"]], "status": "verificado"})
        finally:
            svc.db.on_user_write = original
        assert calls, "moderar en lote tiene que marcar la base para respaldo"


def test_a_duplicate_answers_200_not_201(make_client):
    """No se creó nada: 201 diría que sí."""
    with make_client() as client:
        first = client.post("/api/reports", data=SPOT)
        assert first.status_code == 201
        again = client.post("/api/reports", data={**SPOT, "description": "Otra vez"})
        assert again.status_code == 200 and again.json()["duplicate"] is True


def test_the_author_learns_what_happened_to_their_report(make_client):
    """Quien reporta humo tiene que poder saber si su aviso sirvió."""
    with make_client(ADMIN_TOKEN=ADMIN["X-Admin-Token"]) as client:
        token = client.post("/api/subscribers").json()["token"]
        device = {"X-Brasa-Token": token}
        created = client.post("/api/reports", data=SPOT, headers=device).json()
        mine = client.get("/api/reports/mine", headers=device).json()
        assert mine["total"] == 1 and mine["reports"][0]["status"] == "no_verificado"
        assert mine["reports"][0]["status_label"] == "En revisión"
        client.post(
            f"/api/admin/reports/{created['id']}",
            headers=ADMIN,
            json={"status": "verificado", "note": "Confirmado con la cámara del cerro"},
        )
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


def test_private_responses_vary_by_device_token(make_client):
    """La caché del navegador y del service worker guarda por URL: `Vary` separa un dispositivo de otro."""
    with make_client() as client:
        device = {"X-Brasa-Token": client.post("/api/subscribers").json()["token"]}
        for path in ("/api/reports/mine", "/api/me", "/api/places"):
            vary = client.get(path, headers=device).headers.get("vary", "")
            assert "x-brasa-token" in vary.lower(), path


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


def test_an_old_database_opens_even_without_the_author_column(tmp_path):
    """El índice de autor depende de una columna que las bases ya desplegadas no tienen.

    Si el índice se crea antes de la migración, abrir esa base falla con «no such column:
    subscriber_id» y el arranque (o la restauración de un respaldo) se queda sin datos.
    """
    import sqlite3

    from backend.db import Database

    path = tmp_path / "brasa.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        "CREATE TABLE reports(id TEXT PRIMARY KEY, created_at TEXT NOT NULL, lat REAL NOT NULL, lon REAL NOT NULL,"
        " comuna_code INTEGER, kind TEXT NOT NULL, description TEXT NOT NULL, photo TEXT,"
        " status TEXT NOT NULL DEFAULT 'no_verificado', moderated_at TEXT, moderator_note TEXT);"
        "INSERT INTO reports VALUES ('r1','2026-01-01T00:00:00Z',-33,-71,13101,'humo','Columna',NULL,"
        "'no_verificado',NULL,NULL);"
    )
    conn.commit()
    conn.close()

    db = Database(path)  # no debe lanzar
    assert db.one("SELECT subscriber_id FROM reports WHERE id = 'r1'") == {"subscriber_id": None}
    indexes = {row["name"] for row in db.query("PRAGMA main.index_list(reports)")}
    assert "reports_author" in indexes, "el índice se crea igual, después de la migración"


def test_the_queue_serves_the_oldest_first_and_counts_its_age(make_client):
    """En temporada alta lo nuevo no puede tapar un aviso que lleva horas esperando."""
    with make_client(ADMIN_TOKEN=ADMIN["X-Admin-Token"]) as client:
        svc = client.app.state.services
        now = datetime.now(timezone.utc)
        for report_id, hours in (("viejo", 3), ("medio", 2), ("nuevo", 0)):
            created = (now - timedelta(hours=hours)).strftime(STAMP)
            svc.db.execute(
                "INSERT INTO reports(id, created_at, lat, lon, comuna_code, kind, description, status) VALUES (?,?,?,?,?,?,?,?)",
                (report_id, created, -33.05, -71.55, 5109, "llamas", "x", "no_verificado"),
            )
        queue = client.get("/api/admin/reports", headers=ADMIN).json()["reports"]
        assert [r["id"] for r in queue] == ["viejo", "medio", "nuevo"]
        assert queue[0]["age_s"] > queue[1]["age_s"] > queue[2]["age_s"] >= 0
        assert queue[0]["age_s"] >= 3 * 3600


def test_the_queue_filters_by_comuna(make_client):
    """Con muchos reportes, un moderador puede cubrir solo su comuna."""
    with make_client(ADMIN_TOKEN=ADMIN["X-Admin-Token"]) as client:
        svc = client.app.state.services
        created = datetime.now(timezone.utc).strftime(STAMP)
        for report_id, comuna in (("en-comuna", 5109), ("otra-comuna", 5501)):
            svc.db.execute(
                "INSERT INTO reports(id, created_at, lat, lon, comuna_code, kind, description, status) VALUES (?,?,?,?,?,?,?,?)",
                (report_id, created, -33.05, -71.55, comuna, "llamas", "x", "no_verificado"),
            )
        queue = client.get("/api/admin/reports?comuna=5109", headers=ADMIN).json()["reports"]
        assert [r["id"] for r in queue] == ["en-comuna"]
        assert queue[0]["comuna_code"] == 5109


def test_the_comuna_filter_reaches_beyond_the_200_oldest(make_client):
    """La cola corta en 200 por antigüedad: sin filtro en el servidor, un reporte de la comuna
    elegida que caiga después del corte no llega al navegador (REV-12)."""
    with make_client(ADMIN_TOKEN=ADMIN["X-Admin-Token"]) as client:
        svc = client.app.state.services
        base = datetime.now(timezone.utc)
        for i in range(200):
            created = (base - timedelta(minutes=200 - i)).strftime(STAMP)
            svc.db.execute(
                "INSERT INTO reports(id, created_at, lat, lon, comuna_code, kind, description, status) VALUES (?,?,?,?,?,?,?,?)",
                (f"curico-{i:03d}", created, -33.05, -71.55, 5109, "llamas", "x", "no_verificado"),
            )
        svc.db.execute(
            "INSERT INTO reports(id, created_at, lat, lon, comuna_code, kind, description, status) VALUES (?,?,?,?,?,?,?,?)",
            ("talca-nuevo", base.strftime(STAMP), -35.42, -71.66, 5501, "llamas", "x", "no_verificado"),
        )
        unfiltered = client.get("/api/admin/reports", headers=ADMIN).json()["reports"]
        assert len(unfiltered) == 200 and "talca-nuevo" not in {r["id"] for r in unfiltered}
        filtered = client.get("/api/admin/reports?comuna=5501", headers=ADMIN).json()["reports"]
        assert [r["id"] for r in filtered] == ["talca-nuevo"]


def test_a_moderator_token_moderates_and_leaves_its_name(make_client):
    """Cada voluntario entra con su token y cada decisión queda con su nombre (SEC-10)."""
    with make_client(ADMIN_TOKEN=ADMIN["X-Admin-Token"]) as client:
        mine = {"X-Admin-Token": new_moderator(client)["token"]}
        created = new_report(client)
        ok = client.post(f"/api/admin/reports/{created['id']}", headers=mine, json={"status": "verificado", "note": "Llamé a la oficina"})
        assert ok.status_code == 200
        log = client.get("/api/admin/moderation-log", headers=mine).json()["log"]
        assert log[0]["moderator"] == "Valesca" and log[0]["action"] == "verificado"
        assert log[0]["report_id"] == created["id"] and log[0]["note"] == "Llamé a la oficina"


def test_a_revoked_token_stops_working_but_keeps_its_history(make_client):
    """Revocar corta el acceso al instante y no borra lo que la persona ya decidió."""
    with make_client(ADMIN_TOKEN=ADMIN["X-Admin-Token"]) as client:
        mod = new_moderator(client)
        mine = {"X-Admin-Token": mod["token"]}
        created = new_report(client)
        client.post(f"/api/admin/reports/{created['id']}", headers=mine, json={"status": "descartado"})
        assert client.post(f"/api/admin/moderators/{mod['id']}/revoke", headers=ADMIN).json() == {"ok": True}
        assert client.get("/api/admin/reports", headers=mine).status_code == 403
        assert client.post(f"/api/admin/reports/{created['id']}", headers=mine, json={"status": "verificado"}).status_code == 403
        log = client.get("/api/admin/moderation-log", headers=ADMIN).json()["log"]
        assert log[0]["moderator"] == "Valesca" and log[0]["action"] == "descartado"
        # Revocar dos veces o a alguien que no existe es 404, no un silencio.
        assert client.post(f"/api/admin/moderators/{mod['id']}/revoke", headers=ADMIN).status_code == 404


def test_the_admin_token_still_works_as_superuser(make_client):
    """Aditivo: el token maestro sigue entrando y sus acciones quedan como «administración»."""
    with make_client(ADMIN_TOKEN=ADMIN["X-Admin-Token"]) as client:
        me = client.get("/api/admin/me", headers=ADMIN).json()
        assert me == {"name": "administración", "superuser": True}
        created = new_report(client)
        client.post(f"/api/admin/reports/{created['id']}", headers=ADMIN, json={"status": "verificado"})
        log = client.get("/api/admin/moderation-log", headers=ADMIN).json()["log"]
        assert log[0]["moderator"] == "administración" and log[0]["report_id"] == created["id"]


def test_each_batch_decision_is_logged(make_client):
    """El lote es una decisión por reporte: el registro las anota una por una."""
    with make_client(ADMIN_TOKEN=ADMIN["X-Admin-Token"]) as client:
        first, second = new_report(client), new_report(client, lat="-33.20", lon="-71.40")
        client.post(
            "/api/admin/reports/batch",
            headers=ADMIN,
            json={"ids": [first["id"], second["id"]], "status": "descartado", "note": "Duplicados"},
        )
        log = client.get("/api/admin/moderation-log", headers=ADMIN).json()["log"]
        assert {e["report_id"] for e in log} == {first["id"], second["id"]}
        assert all(e["action"] == "descartado" and e["note"] == "Duplicados" for e in log)


def test_a_moderator_cannot_manage_the_team(make_client):
    """Un voluntario modera y ve el registro, pero no da de alta ni revoca: eso escalaría su acceso."""
    with make_client(ADMIN_TOKEN=ADMIN["X-Admin-Token"]) as client:
        mod = new_moderator(client)
        mine = {"X-Admin-Token": mod["token"]}
        assert client.get("/api/admin/me", headers=mine).json() == {"name": "Valesca", "superuser": False}
        assert client.get("/api/admin/moderators", headers=mine).status_code == 403
        assert client.post("/api/admin/moderators", headers=mine, json={"name": "Otro"}).status_code == 403
        assert client.post(f"/api/admin/moderators/{mod['id']}/revoke", headers=mine).status_code == 403
        assert client.get("/api/admin/moderation-log", headers=mine).status_code == 200


def test_the_token_is_stored_only_as_a_hash(make_client):
    """Una copia de la base no puede reconstruir los tokens de los voluntarios."""
    import hashlib

    with make_client(ADMIN_TOKEN=ADMIN["X-Admin-Token"]) as client:
        mod = new_moderator(client)
        row = client.app.state.services.db.one("SELECT * FROM moderators WHERE id = ?", (mod["id"],))
        assert row["token_hash"] == hashlib.sha256(mod["token"].encode()).hexdigest()
        assert mod["token"] not in row.values()


def test_a_server_without_admin_token_still_moderates_with_the_team(make_client):
    """Sin token maestro la moderación sigue viva si hay voluntarios; sin nadie, sigue siendo 503."""
    import hashlib

    with make_client() as client:
        token = "token-de-prueba-xxxxxxxxxxxxxxxxxxxx"
        client.app.state.services.db.execute(
            "INSERT INTO moderators(id, name, token_hash, created_at) VALUES (?,?,?,?)",
            ("m1", "Equipo", hashlib.sha256(token.encode()).hexdigest(), "2026-10-19T00:00:00Z"),
        )
        assert client.get("/api/admin/me", headers={"X-Admin-Token": token}).json()["superuser"] is False
        assert client.get("/api/admin/reports", headers={"X-Admin-Token": "otro"}).status_code == 403

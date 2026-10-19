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

        rows = [("h8", "humo", old(8)), ("l8", "llamas", old(8)), ("l30", "llamas", old(30)),
                ("q70", "quema", old(70)), ("q80", "quema", old(80)), ("o30", "otro", old(30))]
        for report_id, kind, created in rows:
            svc.db.execute("INSERT INTO reports(id, created_at, lat, lon, comuna_code, kind, description, status) "
                           "VALUES (?,?,?,?,?,?,?,?)",
                           (report_id, created, -33.05, -71.55, 5109, kind, "x", "no_verificado"))
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
        body = client.post("/api/admin/reports/batch", headers=ADMIN,
                           json={"ids": [first["id"], second["id"]], "status": "verificado", "note": "Vistos en la cámara"}).json()
        assert body == {"ok": True, "status": "verificado", "requested": 2, "updated": 2, "alerts_created": 0}
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


def test_a_batch_also_marks_the_database_for_backup(make_client):
    """La conexión directa se salta el aviso de escritura: sin marcarlo, el lote no se respaldaba."""
    with make_client(ADMIN_TOKEN=ADMIN["X-Admin-Token"]) as client:
        svc = client.app.state.services
        created = new_report(client)
        calls = []
        original, svc.db.on_user_write = svc.db.on_user_write, lambda: calls.append(1)
        try:
            client.post("/api/admin/reports/batch", headers=ADMIN,
                        json={"ids": [created["id"]], "status": "verificado"})
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


def tiny_jpeg() -> bytes:
    import io

    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (20, 15), (120, 60, 30)).save(buf, "JPEG")
    return buf.getvalue()


def test_a_second_report_is_kept_as_a_corroboration(make_client):
    """El segundo aviso del mismo hecho no se pierde: 1 reporte visible + 1 testigo registrado."""
    with make_client(ADMIN_TOKEN=ADMIN["X-Admin-Token"]) as client:
        svc = client.app.state.services
        first = new_report(client)
        again = client.post("/api/reports", data={**SPOT, "description": "Yo también lo vi"})
        assert again.status_code == 200 and again.json()["duplicate"] is True
        assert again.json()["corroboraciones"] == 1
        assert svc.db.one("SELECT COUNT(*) AS n FROM reports")["n"] == 1
        row = svc.db.one("SELECT * FROM report_corroborations")
        assert row["report_id"] == first["id"]
        queue = client.get("/api/admin/reports", headers=ADMIN).json()["reports"]
        assert queue[0]["corroboraciones"] == 1
        client.post(f"/api/admin/reports/{first['id']}", headers=ADMIN, json={"status": "verificado"})
        public = client.get("/api/reports").json()["reports"]
        assert public[0]["id"] == first["id"] and public[0]["corroboraciones"] == 1


def test_a_report_outside_the_window_is_not_a_corroboration(make_client):
    """Fuera de las 3 h es otro hecho: fila propia y nada que contar como testigo."""
    with make_client() as client:
        svc = client.app.state.services
        old = (datetime.now(timezone.utc) - timedelta(hours=reports_mod.DUPLICATE_HOURS + 1)).strftime(STAMP)
        svc.db.execute("INSERT INTO reports(id, created_at, lat, lon, comuna_code, kind, description, status) "
                       "VALUES (?,?,?,?,?,?,?,?)",
                       ("viejo", old, -33.05, -71.55, 5109, "humo", "Humo de antes", "no_verificado"))
        fresh = new_report(client)
        assert fresh["duplicate"] is False
        assert svc.db.one("SELECT COUNT(*) AS n FROM reports")["n"] == 2
        assert svc.db.one("SELECT COUNT(*) AS n FROM report_corroborations")["n"] == 0


def test_the_duplicate_photo_moves_to_an_original_without_one(make_client):
    """Si el primer aviso llegó sin foto, la del segundo es evidencia del mismo hecho y se conserva."""
    with make_client(ADMIN_TOKEN=ADMIN["X-Admin-Token"]) as client:
        svc = client.app.state.services
        first = new_report(client)
        dup = client.post("/api/reports", data={**SPOT, "description": "Con foto"},
                          files={"photo": ("vecina.jpg", tiny_jpeg(), "image/jpeg")})
        assert dup.status_code == 200 and dup.json()["duplicate"] is True
        name = svc.db.one("SELECT photo FROM reports WHERE id = ?", (first["id"],))["photo"]
        assert name and (svc.settings.data_dir / "uploads" / name).exists()
        photo = client.get(f"/api/reports/{first['id']}/photo", headers=ADMIN)
        assert photo.status_code == 200 and photo.content.startswith(b"\xff\xd8")


def test_a_duplicate_photo_is_dropped_when_the_original_already_has_one(make_client):
    """Con foto en el original, la del duplicado no se guarda: no hace falta y no hay que retenerla."""
    with make_client(ADMIN_TOKEN=ADMIN["X-Admin-Token"]) as client:
        svc = client.app.state.services
        first = client.post("/api/reports", data=SPOT,
                            files={"photo": ("primera.jpg", tiny_jpeg(), "image/jpeg")}).json()
        name = svc.db.one("SELECT photo FROM reports WHERE id = ?", (first["id"],))["photo"]
        client.post("/api/reports", data=SPOT, files={"photo": ("segunda.jpg", tiny_jpeg(), "image/jpeg")})
        assert svc.db.one("SELECT photo FROM reports WHERE id = ?", (first["id"],))["photo"] == name
        assert [p.name for p in (svc.settings.data_dir / "uploads").glob("*.jpg")] == [name]


def test_the_same_device_does_not_corroborate_twice(make_client):
    """Un vecino cuenta una sola vez, y el autor del primer aviso no se suma a sí mismo."""
    with make_client() as client:
        svc = client.app.state.services
        author = {"X-Brasa-Token": client.post("/api/subscribers").json()["token"]}
        first = client.post("/api/reports", data=SPOT, headers=author)
        assert first.status_code == 201
        again = client.post("/api/reports", data=SPOT, headers=author).json()
        assert again["duplicate"] is True and again["corroboraciones"] == 0
        neighbor = {"X-Brasa-Token": client.post("/api/subscribers").json()["token"]}
        assert client.post("/api/reports", data=SPOT, headers=neighbor).json()["corroboraciones"] == 1
        assert client.post("/api/reports", data=SPOT, headers=neighbor).json()["corroboraciones"] == 1
        assert client.post("/api/reports", data=SPOT).json()["corroboraciones"] == 2
        assert svc.db.one("SELECT COUNT(*) AS n FROM report_corroborations")["n"] == 2


def test_corroborated_reports_lead_the_queue(make_client):
    """Lo que varios vecinos vieron se revisa primero; a igual conteo gana el más viejo."""
    with make_client(ADMIN_TOKEN=ADMIN["X-Admin-Token"]) as client:
        svc = client.app.state.services
        old = (datetime.now(timezone.utc) - timedelta(hours=3)).strftime(STAMP)
        svc.db.execute("INSERT INTO reports(id, created_at, lat, lon, comuna_code, kind, description, status) "
                       "VALUES (?,?,?,?,?,?,?,?)",
                       ("viejo-solo", old, -35.0, -71.6, 5501, "llamas", "Sin testigos", "no_verificado"))
        fresh = new_report(client, kind="llamas")
        client.post("/api/reports", data={**SPOT, "kind": "llamas"})
        queue = client.get("/api/admin/reports", headers=ADMIN).json()["reports"]
        assert [r["id"] for r in queue] == [fresh["id"], "viejo-solo"]
        assert queue[0]["corroboraciones"] == 1 and queue[1]["corroboraciones"] == 0


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
        "'no_verificado',NULL,NULL);")
    conn.commit()
    conn.close()

    db = Database(path)          # no debe lanzar
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
            svc.db.execute("INSERT INTO reports(id, created_at, lat, lon, comuna_code, kind, description, status) "
                           "VALUES (?,?,?,?,?,?,?,?)",
                           (report_id, created, -33.05, -71.55, 5109, "llamas", "x", "no_verificado"))
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
            svc.db.execute("INSERT INTO reports(id, created_at, lat, lon, comuna_code, kind, description, status) "
                           "VALUES (?,?,?,?,?,?,?,?)",
                           (report_id, created, -33.05, -71.55, comuna, "llamas", "x", "no_verificado"))
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
            svc.db.execute("INSERT INTO reports(id, created_at, lat, lon, comuna_code, kind, description, status) "
                           "VALUES (?,?,?,?,?,?,?,?)",
                           (f"curico-{i:03d}", created, -33.05, -71.55, 5109, "llamas", "x", "no_verificado"))
        svc.db.execute("INSERT INTO reports(id, created_at, lat, lon, comuna_code, kind, description, status) "
                       "VALUES (?,?,?,?,?,?,?,?)",
                       ("talca-nuevo", base.strftime(STAMP), -35.42, -71.66, 5501, "llamas", "x", "no_verificado"))
        unfiltered = client.get("/api/admin/reports", headers=ADMIN).json()["reports"]
        assert len(unfiltered) == 200 and "talca-nuevo" not in {r["id"] for r in unfiltered}
        filtered = client.get("/api/admin/reports?comuna=5501", headers=ADMIN).json()["reports"]
        assert [r["id"] for r in filtered] == ["talca-nuevo"]

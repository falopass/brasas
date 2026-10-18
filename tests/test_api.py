import asyncio
import io
import json

import httpx
from PIL import Image

from tests.conftest import json_response

SECRETS = {"FIRMS_MAP_KEY": "firms-secret-abc123", "TELEGRAM_BOT_TOKEN": "123456:tg-secret-xyz",
           "TELEGRAM_BOT_USERNAME": "brasa_test_bot", "ADMIN_TOKEN": "admin-secret-token-999"}
FIRMS_CSV = """latitude,longitude,bright_ti4,acq_date,acq_time,frp,confidence
-33.06,-71.45,340.2,2027-01-15,1810,55.0,n
-35.00,-60.00,330.0,2027-01-15,1810,10.0,n
"""


def register(client) -> dict:
    token = client.post("/api/subscribers").json()["token"]
    return {"X-Brasa-Token": token}


def test_config_and_status_never_expose_secrets(make_client):
    with make_client(**SECRETS) as client:
        config = client.get("/api/config")
        assert config.status_code == 200
        body = config.text
        for secret in SECRETS.values():
            if secret != "brasa_test_bot":
                assert secret not in body
        data = config.json()
        assert data["firms_configured"] is True and data["telegram"] == {"enabled": True, "username": "brasa_test_bot"}
        assert len(data["push"]["public_key"]) > 60  # clave pública VAPID (la privada nunca sale)
        assert "PRIVATE" not in body
        assert "region-4" in data["zones"]
        status = client.get("/api/status").text
        assert all(s not in status for s in SECRETS.values() if s != "brasa_test_bot")


def test_security_headers_and_pwa_routes(make_client):
    with make_client() as client:
        r = client.get("/api/health")
        assert r.headers["x-content-type-options"] == "nosniff" and r.headers["cache-control"] == "no-store"
        assert client.get("/sw.js").headers["service-worker-allowed"] == "/"
        assert client.get("/manifest.webmanifest").status_code == 200
        assert client.get("/web/../.env").status_code == 404


def test_explore_validations(make_client):
    with make_client() as client:
        assert client.get("/api/explore?zone=nope").status_code == 422
        assert client.get("/api/explore?mode=historical").status_code == 422
        assert client.get("/api/explore?mode=historical&start=2999-01-01").status_code == 422
        assert client.get("/api/explore?mode=historical&start=1999-01-01").status_code == 422
        missing = client.get("/api/explore?zone=region-7")
        assert missing.status_code == 503 and missing.json()["detail"]["code"] == "FIRMS_KEY_MISSING"


def test_explore_historical_uses_archive_products_and_assigns_comunas(make_client, web):
    web.add(lambda r: "firms" in r.url.host, lambda r: httpx.Response(200, text=FIRMS_CSV))
    with make_client(FIRMS_MAP_KEY="k-123") as client:
        r = client.get("/api/explore?zone=chile&mode=historical&start=2024-02-02&days=3")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["sources"] == ["VIIRS_NOAA20_SP", "VIIRS_SNPP_SP", "MODIS_SP"]
        assert data["in_chile"] == 3 and data["outside_chile"] == 0 and data["points"][0]["comuna"] in {"Quilpué", "Viña del Mar", "Villa Alemana"}
        paths = [req.url.path for req in web.requests]
        assert all("/3/2024-02-02" in p for p in paths)


def test_places_flow_and_isolation(make_client):
    with make_client() as client:
        assert client.get("/api/places").status_code == 401
        mine, other = register(client), register(client)
        r = client.post("/api/places", json={"name": "Casa de mis papás", "kind": "familia", "lat": -33.03, "lon": -71.53, "radius_km": 8},
                        headers=mine)
        assert r.status_code == 201 and r.json()["comuna"]["name"] == "Viña del Mar"
        place_id = r.json()["id"]
        assert client.post("/api/places", json={"name": "Lejos", "lat": 40.0, "lon": -3.0}, headers=mine).status_code == 422
        assert client.get("/api/places", headers=other).json()["places"] == []
        assert client.delete(f"/api/places/{place_id}", headers=other).status_code == 404
        listed = client.get("/api/places", headers=mine).json()["places"]
        assert listed[0]["name"] == "Casa de mis papás" and listed[0]["comuna"]["region"] == "Valparaíso"
        assert client.delete(f"/api/places/{place_id}", headers=mine).json() == {"ok": True}


def test_ingest_cycle_creates_alert_and_delivers_to_telegram(make_client, web):
    sent = []

    def telegram(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return json_response({"ok": True, "result": {}})

    web.add(lambda r: "firms" in r.url.host, lambda r: httpx.Response(200, text=FIRMS_CSV))
    web.add(lambda r: "open-meteo" in r.url.host,
            lambda r: json_response({"current": {"wind_speed_10m": 28.0, "wind_direction_10m": 95.0, "time": "2027-01-15T15:00"}}))
    web.add(lambda r: "telegram" in r.url.host, telegram)
    with make_client(FIRMS_MAP_KEY="k-123", TELEGRAM_BOT_TOKEN="123:tok", TELEGRAM_BOT_USERNAME="b", GOES_ENABLED="0") as client:
        headers = register(client)
        client.post("/api/places", json={"name": "Parcela", "kind": "parcela", "lat": -33.06, "lon": -71.55, "radius_km": 15}, headers=headers)
        svc = client.app.state.services
        sub = svc.db.one("SELECT id FROM subscribers WHERE id = ?", (headers["X-Brasa-Token"],))
        svc.db.execute("UPDATE subscribers SET telegram_chat_id = '777' WHERE id = ?", (sub["id"],))
        result = asyncio.run(svc.ingest_cycle())
        assert result["firms_new"] == 2  # 2 productos × 1 fila; la de Argentina queda fuera de la caja de Chile
        assert result["alerts"] == 1
        alert = client.get("/api/alerts", headers=headers).json()["alerts"][0]
        assert alert["level"] == "urgente" and alert["upwind"] is True and alert["delivered"] == ["telegram"]
        assert sent and sent[0]["chat_id"] == "777" and "URGENTE" in sent[0]["text"] and "SENAPRED" in sent[0]["text"]
        # Un segundo ciclo con los mismos datos no duplica observaciones ni alertas.
        again = asyncio.run(svc.ingest_cycle())
        assert again == {"firms_new": 0, "goes_new": 0, "alerts": 0, "incidents": 0, "failed_sources": []}
        obs = client.get("/api/observations?hours=336&reliable=true").json()
        assert obs["count"] == 2 and obs["points"][0]["comuna"] in {"Quilpué", "Viña del Mar", "Villa Alemana"}
        place_id = client.get("/api/places", headers=headers).json()["places"][0]["id"]
        summary = client.get(f"/api/places/{place_id}/summary", headers=headers).json()
        assert summary["status"] == "urgente" and summary["nearby"][0]["upwind"] is True


def test_risk_computation_and_map(make_client, web):
    def forecast(request: httpx.Request) -> httpx.Response:
        lats = request.url.params["latitude"].split(",")
        hourly = {"time": [f"2027-01-15T{h:02d}:00" for h in range(3, 24)] + [f"2027-01-16T{h:02d}:00" for h in range(3)], "temperature_2m": [32] * 24,
                  "relative_humidity_2m": [25] * 24, "wind_speed_10m": [31] * 2 + [5] * 22,
                  "wind_gusts_10m": [50] * 24, "wind_direction_10m": [220] * 24}
        return json_response([{"hourly": hourly} for _ in lats])

    web.add(lambda r: "open-meteo" in r.url.host, forecast)
    with make_client() as client:
        svc = client.app.state.services
        assert asyncio.run(svc.compute_risk()) == 345
        assert sum("open-meteo" in r.url.host for r in web.requests) == 7  # lotes de 50 comunas
        data = client.get("/api/risk?day=2027-01-15").json()
        assert len(data["comunas"]) == 345 and data["comunas"]["5109"]["level"] == "extremo"
        detail = client.get("/api/risk/5109").json()
        assert detail["comuna"]["name"] == "Viña del Mar" and len(detail["hours"]) == 24


def jpeg_with_gps() -> bytes:
    img = Image.new("RGB", (64, 48), (200, 80, 30))
    exif = Image.Exif()
    exif[0x010F] = "CamaraDePrueba"
    exif[0x8825] = {1: "S", 2: (33.0, 2.0, 0.0)}  # GPSInfo
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif.tobytes())
    return buf.getvalue()


def test_report_moderation_flow_strips_metadata(make_client, tmp_path):
    with make_client(ADMIN_TOKEN="admin-secret-token-999") as client:
        original = jpeg_with_gps()
        assert Image.open(io.BytesIO(original)).getexif()
        r = client.post("/api/reports", data={"lat": "-33.05", "lon": "-71.5", "kind": "humo", "description": "Columna de humo"},
                        files={"photo": ("foto.jpg", original, "image/jpeg")})
        assert r.status_code == 201, r.text
        report_id = r.json()["id"]
        assert client.get("/api/reports").json()["reports"] == []  # sin verificar: no es público
        assert client.get(f"/api/reports/{report_id}/photo").status_code == 403
        assert client.get("/api/admin/reports").status_code == 403
        admin = {"X-Admin-Token": "admin-secret-token-999"}
        queue = client.get("/api/admin/reports", headers=admin).json()["reports"]
        assert queue[0]["id"] == report_id and queue[0]["comuna"] == "Viña del Mar"
        stored = client.get(f"/api/reports/{report_id}/photo", headers=admin)
        assert stored.status_code == 200 and not Image.open(io.BytesIO(stored.content)).getexif()
        assert client.post(f"/api/admin/reports/{report_id}", json={"status": "verificado", "note": "Confirmado por brigada"},
                           headers=admin).json() == {"ok": True}
        public = client.get("/api/reports").json()["reports"]
        assert public[0]["status"] == "verificado" and public[0]["lat"] == -33.05
        assert client.get(f"/api/reports/{report_id}/photo").status_code == 200
        bad = client.post("/api/reports", data={"lat": "-33.05", "lon": "-71.5", "kind": "humo"},
                          files={"photo": ("x.jpg", b"not an image", "image/jpeg")})
        assert bad.status_code == 422


def test_cases_catalog_and_real_goes_timeline(make_client):
    with make_client() as client:
        catalog = client.get("/api/cases").json()["cases"]
        assert {c["id"] for c in catalog} == {"penco-lirquen-2026", "vina-del-mar-2024", "nuble-biobio-araucania-2023",
                                              "las-maquinas-2017", "valparaiso-2014", "torres-del-paine-2011"}
        # Cada cifra lleva su fuente, enlace y fecha; el alcance dice si es un incendio, un complejo o un episodio.
        for case in catalog:
            assert case["scope"] in {"fire", "complex", "episode", "season"}
            for figure in case["figures"]:
                assert figure["revisions"] and all(r["source"] and r["url"].startswith("https://") and r["date"] for r in figure["revisions"])
        penco = client.get("/api/cases/penco-lirquen-2026").json()
        assert penco["timeline"]["counts"]["goes"] > 1000 and penco["timeline"]["events"][0]["kind"] == "inicio"
        vina = client.get("/api/cases/vina-del-mar-2024").json()
        timeline = vina["timeline"]
        assert len(timeline["hours"]) == 72 and timeline["counts"]["goes"] > 1000
        assert timeline["events"][0]["kind"] == "inicio"
        assert "No es perímetro oficial" in timeline["footprint_note"]
        assert len(vina["scans"]) > 400
        maquinas = client.get("/api/cases/las-maquinas-2017").json()
        assert maquinas["timeline"]["counts"]["goes"] == 0 and "GOES" in maquinas["case"]["goes_note"]
        assert client.get("/api/cases/nope").status_code == 404
        assert client.post("/api/cases/vina-del-mar-2024/polar").status_code == 503


def test_telegram_linking_and_location(make_client):
    from backend.notify import telegram

    with make_client() as client:
        svc = client.app.state.services
        headers = register(client)
        client.post("/api/places", json={"name": "Casa", "lat": -35.43, "lon": -71.66}, headers=headers)
        svc.db.execute("UPDATE subscribers SET link_code = 'abc' WHERE id = ?", (headers["X-Brasa-Token"],))
        reply = telegram.handle_update(svc.db, {"message": {"chat": {"id": 42}, "text": "/start abc"}})
        assert "1 lugar" in reply
        assert client.get("/api/me", headers=headers).json()["telegram"] is True
        reply = telegram.handle_update(svc.db, {"message": {"chat": {"id": 42}, "location": {"latitude": -36.82, "longitude": -73.05}}})
        assert "Concepción" in reply
        assert len(client.get("/api/places", headers=headers).json()["places"]) == 2
        assert "Casa" in telegram.handle_update(svc.db, {"message": {"chat": {"id": 42}, "text": "/lugares"}})


def test_one_failing_source_does_not_block_the_other(make_client, web):
    web.add(lambda r: "firms" in r.url.host, lambda r: httpx.Response(200, text=FIRMS_CSV))
    with make_client(FIRMS_MAP_KEY="k-123", GOES_ENABLED="1") as client:
        svc = client.app.state.services

        async def broken():
            raise RuntimeError("S3 caído")

        svc.ingest_goes = broken
        result = asyncio.run(svc.ingest_cycle())
        assert result["firms_new"] == 2 and result["failed_sources"] == ["goes"]
        assert svc.db.kv_get("last_ingest_at")


def test_place_names_are_cleaned_and_errors_do_not_leak_config(make_client):
    with make_client() as client:
        headers = register(client)
        r = client.post("/api/places", json={"name": "<img src=x onerror=alert(1)>Casa\x07", "lat": -33.05, "lon": -71.55}, headers=headers)
        assert r.status_code == 201, r.text
        name = client.get("/api/places", headers=headers).json()["places"][0]["name"]
        assert "<" not in name and ">" not in name and "\x07" not in name
        assert client.post("/api/places", json={"name": "<>", "lat": -33.05, "lon": -71.55}, headers=headers).status_code == 422
        admin = client.get("/api/admin/reports", headers={"X-Admin-Token": "x"})
        assert admin.status_code == 503 and "ADMIN_TOKEN" not in admin.text and ".env" not in admin.text


def test_shared_place_is_read_only_without_owner_data_and_can_be_revoked(make_client):
    with make_client() as client:
        owner = register(client)
        pid = client.post("/api/places", json={"name": "Casa de mi mamá", "lat": -33.05, "lon": -71.55, "older_adult": True},
                          headers=owner).json()["id"]
        token = client.post(f"/api/places/{pid}/share", headers=owner).json()["token"]
        assert client.post(f"/api/places/{pid}/share", headers=owner).json()["token"] == token  # mismo enlace
        assert client.post(f"/api/places/{pid}/share", headers=register(client)).status_code == 404  # ajeno
        shared = client.get(f"/api/shared/{token}")  # sin cuenta ni token de dispositivo
        assert shared.status_code == 200
        body = shared.json()
        assert body["place"]["name"] == "Casa de mi mamá" and body["place"]["older_adult"] is True
        assert "subscriber_id" not in str(body) and "share_token" not in str(body) and owner["X-Brasa-Token"] not in str(body)
        listed = client.get("/api/places", headers=owner).json()["places"][0]
        assert listed["shared"] is True and listed["older_adult"] is True
        assert client.delete(f"/api/places/{pid}/share", headers=owner).json() == {"ok": True}
        assert client.get(f"/api/shared/{token}").status_code == 404
        assert client.get("/api/shared/corto").status_code == 404


def test_older_adult_makes_any_nearby_heat_urgent():
    from backend import alerts
    assert alerts.classify(8.0, False, "bajo") == "aviso"
    assert alerts.classify(8.0, False, "bajo", older_adult=True) == "urgente"


def test_old_backup_gets_new_place_columns(tmp_path):
    import sqlite3
    from backend.db import Database
    old = tmp_path / "old.db"
    conn = sqlite3.connect(old)
    conn.executescript("CREATE TABLE subscribers(id TEXT PRIMARY KEY, created_at TEXT);"
                       "CREATE TABLE places(id TEXT PRIMARY KEY, subscriber_id TEXT, name TEXT, kind TEXT, lat REAL, lon REAL,"
                       " radius_km REAL, comuna_code INTEGER, created_at TEXT);"
                       "INSERT INTO places VALUES ('p1','s1','Casa','casa',-33,-71,10,NULL,'2026-01-01');")
    conn.commit(); conn.close()
    db = Database(tmp_path / "brasa.db")
    db.restore(old.read_bytes())
    row = db.one("SELECT name, older_adult, share_token FROM places WHERE id = 'p1'")
    assert row == {"name": "Casa", "older_adult": 0, "share_token": None}

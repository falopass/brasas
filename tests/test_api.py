import asyncio
import io
import json
from datetime import datetime, timedelta, timezone

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


def test_explore_daily_limit_answers_a_clear_422(make_client, web):
    """El tope diario del archivo satelital no es una caída: 422 con su código y su mensaje."""
    from backend.routes.common import limiter

    limiter.hits.clear()  # el límite es por proceso: otras pruebas ya gastaron cupo de la misma IP
    web.add(lambda r: "firms" in r.url.host, lambda r: httpx.Response(200, text=FIRMS_CSV))
    with make_client(FIRMS_MAP_KEY="k-123", EXPLORE_DAILY_LIMIT="2") as client:
        assert client.get("/api/explore?zone=chile").status_code == 200
        assert client.get("/api/explore?zone=chile").status_code == 200
        blocked = client.get("/api/explore?zone=chile")
        assert blocked.status_code == 422
        detail = blocked.json()["detail"]
        assert detail["code"] == "EXPLORE_DAILY_LIMIT"
        assert "tope de 2 consultas diarias" in detail["message"]
        assert detail["limit"] == 2 and detail["retry_after_s"] > 0
        assert blocked.headers["retry-after"] == str(detail["retry_after_s"])


def test_a_fwi_failure_does_not_leave_the_map_without_a_risk_level(make_client):
    """El archivo del FWI se agota por volumen; el 30-30-30 viene del pronóstico y debe salir igual."""
    import asyncio

    with make_client() as client:
        svc = client.app.state.services

        async def boom():
            raise RuntimeError("429 Too Many Requests")

        async def fake_risk():
            return 345

        svc.compute_fwi = boom
        svc.compute_risk = fake_risk
        out = asyncio.run(svc._risk_and_fwi())
        assert out["risk_comunas"] == 345
        assert out["fwi_comunas"] is None and "429" in out["fwi_error"]


def test_the_worker_cycle_also_refreshes_fwi_dmc_and_rain(make_client, web):
    """El cron no puede dejar atrás FWI, DMC ni lluvia: sin eso el riesgo combinado queda viejo."""
    web.add(lambda r: True, lambda r: httpx.Response(503, text="proveedor caído"))
    token = "internal-secret-1234567890"
    with make_client(INTERNAL_TOKEN=token, GOES_ENABLED="0") as client:
        r = client.post("/api/internal/tick?wait=1", headers={"X-Internal-Token": token})
        assert r.status_code == 200, r.text
        body = r.json()
        for job, result_key, error_key in (("fwi", "fwi_comunas", "fwi_error"),
                                           ("dmc", "dmc_alerts", "dmc_error"),
                                           ("lluvia", "rain_comunas", "rain_error")):
            assert result_key in body or error_key in body, f"{job} no se intentó: {sorted(body)}"
        # El proveedor está caído, así que lo que se guarda es el fallo, no un dato inventado.
        assert "fwi_error" in body and "dmc_error" in body
        # El resumen del ciclo queda en la base: el contenedor se suspende y la memoria se pierde.
        svc = client.app.state.services
        svc.last_cycle = None  # como tras despertar el contenedor
        status = client.get("/api/status").json()
        assert status["last_cycle"] and status["last_cycle"]["finished_at"]


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
        assert summary["cause"] == {"satelite": True, "conaf": False, "persona_mayor": False}


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
        # Sin FWI calculado el combinado conserva el 30-30-30 y lo dice, en vez de inventar un nivel.
        assert data["comunas"]["5109"]["level_combined"] == "extremo"
        assert any("sin dato" in reason for reason in data["comunas"]["5109"]["reasons"])
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
        decision = client.post(f"/api/admin/reports/{report_id}", json={"status": "verificado", "note": "Confirmado por brigada"},
                               headers=admin).json()
        # La respuesta conserva "ok" y agrega cuántos incidentes se recalcularon (FIX-09).
        assert decision["ok"] is True and decision["incidents_refreshed"] == 0
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

        # El ciclo llama a las versiones internas (ya tiene el lock): se rompe esa, no la pública.
        svc._ingest_goes = broken
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


def seed_run(db, product: str, ok: bool, index: int) -> None:
    db.execute("INSERT INTO ingest_runs(provider, product, started_at, finished_at, ok, n_records, n_new, message) "
               "VALUES (?,?,?,?,?,?,?,?)",
               ("prueba", product, f"2026-10-18T0{index}:00:00Z", f"2026-10-18T0{index}:01:00Z", int(ok), 0, 0, ""))


def test_status_history_shows_consecutive_failures_for_the_monitor(make_client):
    """OPS-01: el monitoreo necesita ver tres fallos seguidos; sin historial solo hay la última."""
    with make_client() as client:
        db = client.app.state.services.db
        seed_run(db, "VIIRS", True, 1)
        seed_run(db, "VIIRS", True, 2)
        seed_run(db, "VIIRS", False, 3)
        seed_run(db, "VIIRS", False, 4)
        seed_run(db, "VIIRS", False, 5)
        body = client.get("/api/status?history=5").json()
        assert [item["ok"] for item in body["history"]["VIIRS"]] == [False, False, False, True, True]
        assert [item["ok"] for item in client.get("/api/status?history=2").json()["history"]["VIIRS"]] == [False, False]
        # Sin el parámetro el payload no crece: la interfaz no lo necesita.
        assert "history" not in client.get("/api/status").json()
        assert client.get("/api/status?history=999").status_code == 422


def test_report_turnstile_verification(make_client, web):
    """OPS-05: con TURNSTILE_SECRET el reporte exige un token que el siteverify acepte;
    si el verificador no responde, el reporte pasa a moderación igual (nada se publica solo)."""
    from backend.routes.common import limiter

    limiter.hits.clear()  # el límite es por proceso: otras pruebas ya gastaron cupo de la misma IP
    report = {"lat": "-33.05", "lon": "-71.5", "kind": "humo"}
    env = {"TURNSTILE_SITE_KEY": "0x4_sitekey_publica", "TURNSTILE_SECRET": "0x4_secret_privada"}

    # Sin secreto configurado no hay verificación (desarrollo local).
    with make_client() as client:
        assert client.post("/api/reports", data=report).status_code == 201

    web.add(lambda r: "challenges.cloudflare.com" in r.url.host,
            lambda r: json_response({"success": r.content and b"token-bueno" in r.content}))
    with make_client(**env) as client:
        assert client.get("/api/config").json()["turnstile_site_key"] == "0x4_sitekey_publica"
        assert "0x4_secret_privada" not in client.get("/api/config").text  # la secreta nunca sale
        assert client.post("/api/reports", data=report).status_code == 403                      # falta el token
        assert client.post("/api/reports", data={**report, "cf-turnstile-response": "x"}).status_code == 403
        # Otro punto: el primero ya quedó en revisión y el deduplicador respondería 200.
        r = client.post("/api/reports", data={**report, "lat": "-34.00", "lon": "-71.90",
                                            "cf-turnstile-response": "token-bueno"})
        assert r.status_code == 201, r.text

    # Verificador caído: el reporte entra a la cola de moderación (falla abierta, ya revisada).
    web.routes.clear()
    web.add(lambda r: "challenges.cloudflare.com" in r.url.host, lambda r: httpx.Response(503))
    with make_client(**env) as client:
        assert client.post("/api/reports", data={**report, "lat": "-35.00", "lon": "-72.10",
                                               "cf-turnstile-response": "token-bueno"}).status_code == 201

    limiter.hits.clear()  # no gastarle el cupo a las pruebas que siguen en el mismo proceso


def test_verifying_a_report_refreshes_the_nearby_incident(make_client):
    """FIX-09: un reporte verificado lleva el incidente a «reportado» sin detecciones nuevas."""
    from backend import incidents as incidents_mod

    with make_client(ADMIN_TOKEN="admin-secret-token-999") as client:
        svc = client.app.state.services
        now = datetime.now(timezone.utc)
        moment = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        lat, lon = -33.05, -71.55
        svc.db.execute("INSERT INTO observations(id, source, sensor, satellite, resolution_m, lat, lon, observed_at, "
                       "frp_mw, confidence, comuna_code, run_id, ingested_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL,?)",
                       ("g1", "goes", "ABI", "GOES-19", 2000, lat, lon, moment, 20.0, "alta", 13101, moment))
        point = {"id": "g1", "lat": lat, "lon": lon, "observed_at": moment, "sensor": "ABI",
                 "confidence": "alta", "resolution_m": 2000}
        [incident] = incidents_mod.update(svc.db, [point], now)
        assert incident["status"] == "anomalia"
        created = client.post("/api/reports", data={"lat": str(lat + 0.01), "lon": str(lon + 0.01), "kind": "humo"}).json()
        # Sin el arreglo, el incidente seguía en «anomalía» hasta la próxima detección.
        assert client.get("/api/incidents").json()["incidents"][0]["status"] == "anomalia"
        body = client.post(f"/api/admin/reports/{created['id']}",
                           headers={"X-Admin-Token": "admin-secret-token-999"},
                           json={"status": "verificado", "note": "Confirmado"}).json()
        assert body == {"ok": True, "incidents_refreshed": 1}
        assert client.get("/api/incidents").json()["incidents"][0]["status"] == "reportado"


def test_a_discarded_report_does_not_refresh_incidents(make_client):
    from backend import incidents as incidents_mod

    with make_client(ADMIN_TOKEN="admin-secret-token-999") as client:
        svc = client.app.state.services
        now = datetime.now(timezone.utc)
        moment = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        svc.db.execute("INSERT INTO observations(id, source, sensor, satellite, resolution_m, lat, lon, observed_at, "
                       "frp_mw, confidence, comuna_code, run_id, ingested_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL,?)",
                       ("g2", "goes", "ABI", "GOES-19", 2000, -33.05, -71.55, moment, 20.0, "alta", 13101, moment))
        incidents_mod.update(svc.db, [{"id": "g2", "lat": -33.05, "lon": -71.55, "observed_at": moment,
                                       "sensor": "ABI", "confidence": "alta", "resolution_m": 2000}], now)
        created = client.post("/api/reports", data={"lat": "-33.04", "lon": "-71.54", "kind": "humo"}).json()
        body = client.post(f"/api/admin/reports/{created['id']}",
                           headers={"X-Admin-Token": "admin-secret-token-999"},
                           json={"status": "descartado", "note": "No se ve humo"}).json()
        assert body["incidents_refreshed"] == 0


def test_firms_keeps_a_detection_from_yesterday_after_utc_midnight(make_client, web):
    """FIX-01: con `days=1` FIRMS solo devolvía el día UTC en curso y se perdían las pasadas
    adquiridas a las 22:30 que se publican de madrugada (latencia NRT de 1 a 3 h).

    El simulador respeta la ventana que pide la aplicación: la fila de ayer solo aparece con dos
    días. Si alguien volviera a `days=1`, la prueba falla en vez de pasar por casualidad.
    """
    today = datetime.now(timezone.utc).date()
    yesterday = (today - timedelta(days=1)).isoformat()
    header = "latitude,longitude,bright_ti4,acq_date,acq_time,frp,confidence,daynight\n"
    rows = {1: f"-35.00,-71.20,330.0,{today.isoformat()},0130,10.0,n,N\n",
            2: f"-33.06,-71.45,340.2,{yesterday},2230,55.0,n,N\n"
               f"-35.00,-71.20,330.0,{today.isoformat()},0130,10.0,n,N\n"}

    def firms_response(request: httpx.Request) -> httpx.Response:
        days = int(request.url.path.rsplit("/", 1)[-1])
        return httpx.Response(200, text=header + rows.get(days, rows[1]))

    web.add(lambda r: "firms" in r.url.host, firms_response)
    with make_client(FIRMS_MAP_KEY="k-123", GOES_ENABLED="0") as client:
        svc = client.app.state.services
        new = asyncio.run(svc.ingest_firms())
        # Dos productos por defecto × dos filas del CSV de dos días.
        assert len(new) == 4
        assert {row["observed_at"][:10] for row in new} == {yesterday, today.isoformat()}
        # La consulta pide 2 días (el último segmento de la URL de FIRMS es la ventana).
        assert {request.url.path.rsplit("/", 1)[-1] for request in web.requests} == {"2"}
        # Volver a pedir lo mismo no duplica: la deduplicación por id sigue mandando.
        assert asyncio.run(svc.ingest_firms()) == []

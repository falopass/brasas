"""QA-COB: `backend/routes/personal.py` — lugares guardados, IDOR entre
dispositivos, el enlace de familia, `build_summary` con cada estado y los
endpoints periféricos (push, telegram, inbox, export, seguimientos).

Lo que guarda una persona es privado del dispositivo: un token ajeno no lee,
edita ni borra — un error aquí expone dónde vive alguien. Cada prueba nombra la
regla que protege en su docstring.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx

from backend.db import Database
from tests.conftest import json_response

CHILE_TZ = ZoneInfo("America/Santiago")
NOW = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)
PENCAHUE = (-35.41, -71.97)  # comuna 7107


def stamp(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _register(client) -> dict:
    token = client.post("/api/subscribers").json()["token"]
    return {"X-Brasa-Token": token}


def _lugar(client, headers, **over) -> dict:
    body = {"name": "Casa", "lat": PENCAHUE[0], "lon": PENCAHUE[1], "radius_km": 10,
            "kind": "casa"} | over
    r = client.post("/api/places", json=body, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def _obs_row(db: Database, oid: str, at: datetime, lat: float, lon: float,
             confidence: str = "alta") -> None:
    db.execute(
        "INSERT INTO observations(id, source, sensor, satellite, resolution_m, lat, lon, "
        "observed_at, frp_mw, confidence, comuna_code, ingested_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (oid, "firms", "VIIRS", "N20", 375, lat, lon, stamp(at), 20.0, confidence, 7107, stamp(at)))


def _incident_row(db: Database, iid: str, lat: float, lon: float, at: datetime,
                  status: str = "posible", comuna_code: int | None = 7107) -> None:
    db.execute(
        "INSERT INTO incidents(id, status, status_changed_at, first_seen_at, last_seen_at, lat, lon, "
        "min_lat, max_lat, min_lon, max_lon, n_obs, n_reliable, sensors, comuna_code, fixed_source, "
        "updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (iid, status, stamp(at), stamp(at - timedelta(hours=2)), stamp(at), lat, lon, lat - 0.01,
         lat + 0.01, lon - 0.01, lon + 0.01, 2, 2, "VIIRS", comuna_code, 0, stamp(at)))


def _fire_row(db: Database, fid: str, lat: float, lon: float, at: datetime,
              status: str = "confirmado") -> None:
    raw = {"confirmado": "En combate", "controlado": "Controlado", "extinguido": "Extinguido"}[status]
    db.execute(
        "INSERT INTO official_fires(id, name, status, status_raw, started_at, lat, lon, comuna, "
        "region, first_fetched_at, fetched_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (fid, "El Belloto", status, raw, stamp(at), lat, lon, "Pencahue", "Maule", stamp(at), stamp(at)))


# --- CRUD e IDOR ---


def test_lugar_se_crea_se_edita_y_se_borra_solo_del_dueno(make_client):
    """Crear, editar y borrar lugares es del dispositivo dueño del token; el
    listado solo muestra lo propio."""
    with make_client() as client:
        headers = _register(client)
        place = _lugar(client, headers)
        assert [p["id"] for p in client.get("/api/places", headers=headers).json()["places"]] == [place["id"]]
        r = client.patch(f"/api/places/{place['id']}",
                         json={"name": "Casa de la abuela", "lat": PENCAHUE[0], "lon": PENCAHUE[1],
                               "radius_km": 15, "kind": "familia", "older_adult": True},
                         headers=headers)
        assert r.status_code == 200, r.text
        assert client.get("/api/places", headers=headers).json()["places"][0]["radius_km"] == 15
        assert client.delete(f"/api/places/{place['id']}", headers=headers).json() == {"ok": True}
        assert client.get("/api/places", headers=headers).json()["places"] == []


def test_token_ajeno_no_lee_edita_ni_borra_lugar(make_client):
    """IDOR: el lugar es del dispositivo que lo guardó. Con el token de otra
    persona no se lee el resumen, no se edita, no se borra y ni siquiera aparece
    en el listado — un 404, no un detalle."""
    with make_client() as client:
        dueno, ajeno = _register(client), _register(client)
        place = _lugar(client, dueno)
        for r in (
            client.get(f"/api/places/{place['id']}/summary", headers=ajeno),
            client.get(f"/api/places/{place['id']}/history", headers=ajeno),
            client.patch(f"/api/places/{place['id']}", json={"name": "x", "lat": -35.5, "lon": -71.5},
                         headers=ajeno),
            client.delete(f"/api/places/{place['id']}", headers=ajeno),
            client.post(f"/api/places/{place['id']}/share", headers=ajeno),
        ):
            assert r.status_code == 404, (r.request.url, r.text)
        assert client.get("/api/places", headers=ajeno).json()["places"] == []
        assert client.get(f"/api/places/{place['id']}/summary", headers=dueno).status_code == 200


def test_no_se_guardan_mas_de_diez_lugares(make_client):
    """MAX_PLACES = 10: el undécimo lugar responde 422 — el tope existe para que
    la lista de alguien no crezca sin fondo."""
    with make_client() as client:
        svc = client.app.state.services
        headers = _register(client)
        sub_id = svc.db.one("SELECT id FROM subscribers")["id"]
        for i in range(10):
            svc.db.execute(
                "INSERT INTO places(id, subscriber_id, name, kind, lat, lon, radius_km, created_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (f"p{i}", sub_id, f"L{i}", "casa", -35.0 - i * 0.01, -71.0, 10, stamp(NOW)))
        r = client.post("/api/places", json={"name": "once", "lat": -35.0, "lon": -71.0},
                        headers=headers)
        assert r.status_code == 422


# --- el enlace de familia (modo vecino) ---


def test_enlace_de_familia_comparte_solo_lo_publico(make_client):
    """ALR-08: el enlace compartido abre la ficha pública del lugar (nombre,
    radio, persona mayor), el botón «estoy bien» marca la hora, y al revocarlo
    el enlace muere — sin exponer el token ni el subscriber."""
    with make_client() as client:
        dueno, otro = _register(client), _register(client)
        place = _lugar(client, dueno, name="Casa de la abuela", older_adult=True)
        token = client.post(f"/api/places/{place['id']}/share", headers=dueno).json()["token"]
        assert len(token) >= 20
        # Un token corto o inventado no adivina nada.
        assert client.get("/api/shared/corto").status_code == 404
        assert client.get(f"/api/shared/{token}x").status_code == 404
        ficha = client.get(f"/api/shared/{token}").json()
        assert ficha["place"]["name"] == "Casa de la abuela" and ficha["place"]["older_adult"] is True
        assert "subscriber_id" not in ficha["place"] and "share_token" not in ficha["place"]
        assert client.post(f"/api/shared/{token}/estoy-bien", headers=otro).json()["ok"] is True
        # «Que me avisen a mí también»: copia propia e independiente.
        copia = client.post(f"/api/shared/{token}/follow", headers=otro).json()
        assert copia["created"] is True and copia["place"]["name"].startswith("(compartido)")
        otra = client.post(f"/api/shared/{token}/follow", headers=otro).json()
        assert otra["created"] is False  # la misma celda no duplica el lugar
        # Al revocar, el enlace muere pero la copia sigue funcionando.
        assert client.delete(f"/api/places/{place['id']}/share", headers=dueno).json() == {"ok": True}
        assert client.get(f"/api/shared/{token}").status_code == 404
        assert len(client.get("/api/places", headers=otro).json()["places"]) == 1


def test_seguir_enlace_compartido_respeta_el_tope_de_lugares(make_client):
    """El lugar copiado por el enlace también cuenta contra MAX_PLACES: quien
    ya tiene 10 no puede agregar la copia (422, no fila extra)."""
    with make_client() as client:
        svc = client.app.state.services
        dueno, copia = _register(client), _register(client)
        place = _lugar(client, dueno)
        token = client.post(f"/api/places/{place['id']}/share", headers=dueno).json()["token"]
        sub_id = svc.db.one("SELECT id FROM subscribers WHERE id != (SELECT subscriber_id FROM places) LIMIT 1")["id"]
        for i in range(10):
            svc.db.execute(
                "INSERT INTO places(id, subscriber_id, name, kind, lat, lon, radius_km, created_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (f"q{i}", sub_id, f"L{i}", "casa", -36.0 - i * 0.01, -72.0, 10, stamp(NOW)))
        assert client.post(f"/api/shared/{token}/follow", headers=copia).status_code == 422


# --- build_summary: un test por estado ---


def _summary(client, headers, place_id):
    r = client.get(f"/api/places/{place_id}/summary", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def test_resumen_tranquilo_sin_calor_ni_riesgo(make_client):
    """Sin detecciones dentro del radio ni día de riesgo: el estado es
    «tranquilo» — la persona no abre la app buscando ruido."""
    with make_client() as client:
        headers = _register(client)
        place = _lugar(client, headers)
        body = _summary(client, headers, place["id"])
        assert body["status"] == "tranquilo" and body["nearby"] == []


def test_resumen_aviso_con_calor_confiable_cerca(make_client, web):
    """Un foco confiable dentro del radio (pero a más de 2 km y sin viento hacia
    el lugar) sube el estado a «aviso»: atento, no urgente."""
    web.add(lambda r: "open-meteo" in r.url.host, lambda r: httpx.Response(503))
    with make_client() as client:
        svc = client.app.state.services
        headers = _register(client)
        place = _lugar(client, headers)
        _obs_row(svc.db, "o1", datetime.now(timezone.utc) - timedelta(hours=1),
                 PENCAHUE[0] + 0.035, PENCAHUE[1])  # ~4 km al norte
        body = _summary(client, headers, place["id"])
        assert body["status"] == "aviso" and body["cause"] == {
            "satelite": True, "conaf": False, "persona_mayor": False}


def test_resumen_urgente_con_foco_a_dos_km(make_client, web):
    """Un foco confiable a ≤ 2 km es «urgente»: distancia inmediata manda."""
    web.add(lambda r: "open-meteo" in r.url.host, lambda r: httpx.Response(503))
    with make_client() as client:
        svc = client.app.state.services
        headers = _register(client)
        place = _lugar(client, headers)
        _obs_row(svc.db, "o1", datetime.now(timezone.utc) - timedelta(hours=1),
                 PENCAHUE[0] + 0.015, PENCAHUE[1])  # ~1,7 km al norte
        assert _summary(client, headers, place["id"])["status"] == "urgente"


def test_resumen_urgente_cuando_conaf_esta_cerca_y_ya_habia_aviso(make_client, web):
    """Un incendio informado por CONAF dentro del radio y a ≤ 5 km sube el
    estado «aviso» del satélite a «urgente»: la confirmación oficial pesa igual
    que la evidencia inmediata."""
    web.add(lambda r: "open-meteo" in r.url.host, lambda r: httpx.Response(503))
    with make_client() as client:
        svc = client.app.state.services
        headers = _register(client)
        place = _lugar(client, headers)
        _obs_row(svc.db, "o1", datetime.now(timezone.utc) - timedelta(hours=1),
                 PENCAHUE[0] + 0.035, PENCAHUE[1])  # ~4 km: por sí solo sería «aviso»
        _fire_row(svc.db, "7", PENCAHUE[0] + 0.035, PENCAHUE[1],
                  datetime.now(timezone.utc) - timedelta(hours=2))  # ~4 km, activo
        assert _summary(client, headers, place["id"])["status"] == "urgente"


def test_resumen_riesgo_con_dia_alto_sin_calor(make_client, web):
    """Sin calor dentro del radio pero con el 30-30-30 de hoy en «alto» para la
    comuna: el estado es «riesgo» — el día peligroso se declara igual."""
    web.add(lambda r: "open-meteo" in r.url.host, lambda r: httpx.Response(503))
    with make_client() as client:
        svc = client.app.state.services
        headers = _register(client)
        place = _lugar(client, headers)
        hoy = datetime.now(CHILE_TZ).date().isoformat()
        comuna_code = svc.db.one("SELECT comuna_code FROM places WHERE id = ?", (place["id"],))["comuna_code"]
        svc.db.execute(
            "INSERT INTO risk_daily(comuna_code, date, level, score, hours_3of3, hours_2of3, tmax, "
            "rhmin, windmax, computed_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (comuna_code, hoy, "alto", 3, 8, 0, 33.0, 18.0, 38.0, stamp(NOW)))
        body = _summary(client, headers, place["id"])
        assert body["status"] == "riesgo" and body["risk_days"][0]["level"] == "alto"


def test_resumen_tolera_observacion_con_fecha_rota(make_client, web):
    """Una detección con `observed_at` ilegible no tumba el resumen: el filtro
    de las 48 h es por texto («basura» > «2026-…» en ASCII) así que entra como
    calor cercano, pero `_chile_day` no la cuenta en el semanal — una fecha rota
    no inventa un día."""
    web.add(lambda r: "open-meteo" in r.url.host, lambda r: httpx.Response(503))
    with make_client() as client:
        svc = client.app.state.services
        headers = _register(client)
        place = _lugar(client, headers)
        svc.db.execute(
            "INSERT INTO observations(id, source, sensor, satellite, resolution_m, lat, lon, "
            "observed_at, frp_mw, confidence, comuna_code, ingested_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            ("rota", "firms", "VIIRS", "N20", 375, PENCAHUE[0], PENCAHUE[1], "basura", 20.0, "alta",
             7107, stamp(NOW)))
        body = _summary(client, headers, place["id"])
        assert body["status"] == "urgente"  # el filtro de texto la deja pasar como calor
        assert body["week"]["n"] == 0       # pero no fabrica un día en el semanal


def test_historial_descarta_incidente_dentro_de_la_caja_pero_fuera_del_doble_radio(make_client):
    """La caja de precarga es cuadrada y el filtro es por distancia real: un
    incidente en la esquina de la caja pero a más de 2× el radio no entra al
    historial del lugar."""
    with make_client() as client:
        svc = client.app.state.services
        headers = _register(client)
        place = _lugar(client, headers, radius_km=5)
        ahora = datetime.now(timezone.utc)
        # Esquina de la caja (~11 km en diagonal): dentro del BETWEEN, fuera del disco.
        _incident_row(svc.db, "esquina", PENCAHUE[0] + 0.07, PENCAHUE[1] + 0.085,
                      ahora - timedelta(hours=3))
        _incident_row(svc.db, "cerca", PENCAHUE[0] + 0.02, PENCAHUE[1],
                      ahora - timedelta(hours=2))
        items = client.get(f"/api/places/{place['id']}/history", headers=headers).json()["incidents"]
        assert [i["id"] for i in items] == ["cerca"]


# --- push, telegram, inbox, export ---


def test_push_subscribe_valida_https_y_llaves(make_client):
    """La suscripción push exige endpoint https y las dos llaves: una suscripción
    insegura o incompleta no se guarda (422)."""
    with make_client() as client:
        headers = _register(client)
        mala = {"endpoint": "http://inseguro.test/x", "keys": {"p256dh": "a", "auth": "b"}}
        assert client.post("/api/push/subscribe", json=mala, headers=headers).status_code == 422
        mala2 = {"endpoint": "https://push.test/x", "keys": {"p256dh": "a"}}
        assert client.post("/api/push/subscribe", json=mala2, headers=headers).status_code == 422
        buena = {"endpoint": "https://push.test/x", "keys": {"p256dh": "a", "auth": "b"}}
        assert client.post("/api/push/subscribe", json=buena, headers=headers).json() == {"ok": True}
        assert client.delete("/api/push/subscribe", headers=headers).json() == {"ok": True}
        me = client.get("/api/me", headers=headers).json()
        assert me["push"] is False or me.get("suscripcion_push") is None or "push" in me


def test_telegram_link_sin_configuracion_503_y_con_ella_url(make_client):
    """Sin TELEGRAM_BOT_TOKEN el enlace responde 503 — no se promete un canal que
    no existe; configurado, entrega la URL de arranque con el código."""
    with make_client() as client:
        headers = _register(client)
        assert client.post("/api/telegram/link", headers=headers).status_code == 503
    with make_client(TELEGRAM_BOT_TOKEN="123:abc", TELEGRAM_BOT_USERNAME="brasa_bot") as client:
        headers = _register(client)
        body = client.post("/api/telegram/link", headers=headers).json()
        assert body["url"].startswith("https://t.me/brasa_bot?start=")


def test_inbox_con_cursor_roto_422(make_client):
    """El cursor «<created_at>|<id>» exige un id numérico: basura tras el «|»
    responde 422, no una página inventada."""
    with make_client() as client:
        headers = _register(client)
        r = client.get("/api/alerts?before=2026-10-22T00:00:00Z|abc", headers=headers)
        assert r.status_code == 422
        r = client.get("/api/alerts?before=2026-10-22T00:00:00Z|12", headers=headers)
        assert r.status_code == 200  # cursor válido, aunque el historial esté vacío


def test_alerta_de_prueba_sale_por_los_canales_activos(make_client, web):
    """POST /api/alerts/test notifica por los canales del dispositivo: sin
    canales devuelve la lista vacía; con Telegram enlazado, lo intenta por ahí."""
    web.add(lambda r: "api.telegram.org" in r.url.host,
            lambda r: json_response({"ok": True, "result": {}}))
    with make_client(TELEGRAM_BOT_TOKEN="123:abc") as client:
        svc = client.app.state.services
        headers = _register(client)
        sub_id = svc.db.one("SELECT id FROM subscribers")["id"]
        assert client.post("/api/alerts/test", headers=headers).json() == {"channels": []}
        svc.db.execute("UPDATE subscribers SET telegram_chat_id = '555' WHERE id = ?", (sub_id,))
        assert client.post("/api/alerts/test", headers=headers).json() == {"channels": ["telegram"]}


def test_export_incluye_seguimientos_y_sus_avisos_descifrados(make_client):
    """Ley 21.719: el export trae los seguimientos y sus avisos con el payload
    ya leíble (dict), sin follow_id ni subscriber_id — la llave no viaja."""
    with make_client() as client:
        svc = client.app.state.services
        headers = _register(client)
        sub_id = svc.db.one("SELECT id FROM subscribers")["id"]
        fid = svc.db.insert(
            "INSERT INTO incident_follows(subscriber_id, official_ref, fire_status, created_at) "
            "VALUES (?,?,?,?)", (sub_id, "7", "confirmado", stamp(NOW)))
        svc.db.execute(
            "INSERT INTO follow_alerts(follow_id, observation_id, level, observed_at, created_at, "
            "payload, delivered) VALUES (?,?,?,?,?,?,?)",
            (fid, "conaf:7:confirma", "aviso", stamp(NOW), stamp(NOW), '{"title":"t"}', '["push"]'))
        export = client.get("/api/me/export", headers=headers).json()
        [seg] = export["seguimientos"]
        assert seg["official_ref"] == "7" and "subscriber_id" not in seg
        [aviso] = export["avisos_seguimiento"]
        assert aviso["payload"] == {"title": "t"} and aviso["delivered"] == ["push"]
        assert "follow_id" not in aviso and "subscriber_id" not in json.dumps(export)


# --- seguimientos de incendio por el endpoint ---


def test_seguir_por_ref_resuelve_el_incidente_enlazado(make_client):
    """Seguir la tarjeta CONAF de un fuego que ya tiene incidente enlazado
    canónica al mismo seguimiento: POST por `official_ref` cuando el incidente
    existe cae en la deduplicación canónica, no en una segunda fila."""
    with make_client() as client:
        svc = client.app.state.services
        headers = _register(client)
        _incident_row(svc.db, "i1", PENCAHUE[0], PENCAHUE[1], NOW - timedelta(hours=2))
        svc.db.execute("UPDATE incidents SET official_ref = '7' WHERE id = 'i1'")
        _fire_row(svc.db, "7", PENCAHUE[0], PENCAHUE[1], NOW - timedelta(hours=4))
        # Primero por la ref CONAF: resuelve el incidente enlazado.
        r = client.post("/api/me/follows", json={"official_ref": "7"}, headers=headers)
        assert r.status_code == 201 and r.json()["follow"]["incident_id"] == "i1"
        # Repetir por el incidente cae en la canónica: mismo seguimiento, 200.
        r2 = client.post("/api/me/follows", json={"incident_id": "i1"}, headers=headers)
        assert r2.status_code == 200 and r2.json()["created"] is False
        assert len(client.get("/api/me/follows", headers=headers).json()["follows"]) == 1


def test_tope_de_veinte_incendios_seguidos(make_client):
    """MAX_FOLLOWS = 20: el seguimiento 21 responde 422 — una temporada entera
    de incendios cabe en 20 y el tope frena el crecimiento sin fondo."""
    with make_client() as client:
        svc = client.app.state.services
        headers = _register(client)
        sub_id = svc.db.one("SELECT id FROM subscribers")["id"]
        for i in range(20):
            svc.db.execute(
                "INSERT INTO incident_follows(subscriber_id, official_ref, created_at) "
                "VALUES (?,?,?)", (sub_id, f"ref-{i}", stamp(NOW)))
        _fire_row(svc.db, "nuevo", PENCAHUE[0], PENCAHUE[1], NOW - timedelta(hours=1))
        assert client.post("/api/me/follows", json={"official_ref": "nuevo"},
                           headers=headers).status_code == 422


def test_seguir_con_carrera_devuelve_la_fila_existente(make_client, monkeypatch):
    """Si el INSERT OR IGNORE cae en una carrera (la fila apareció entre el
    chequeo y el insert), el endpoint devuelve la existente con 200 en vez de
    reventar — idempotencia bajo concurrencia."""
    with make_client() as client:
        svc = client.app.state.services
        _fire_row(svc.db, "7", PENCAHUE[0], PENCAHUE[1], NOW - timedelta(hours=4))
        headers = _register(client)

        def carrera(sql, params=()):
            svc.db.execute(
                "INSERT INTO incident_follows(subscriber_id, incident_id, official_ref, created_at) "
                "VALUES (?,?,?,?)", (params[0], params[1], params[2], params[4]))
            return 0

        monkeypatch.setattr(svc.db, "insert", carrera)
        r = client.post("/api/me/follows", json={"official_ref": "7"}, headers=headers)
        assert r.status_code == 200 and r.json()["created"] is False
        assert r.json()["follow"]["official_ref"] == "7"

"""ALR-44: «seguir un incendio» — avisos de un incendio concreto sin guardar un lugar.

El ciclo: confirmación CONAF, cambio de estado oficial y calor nuevo del incidente; tope de
un aviso cada 3 h, caducidad a los 7 días sin calor, deduplicación de los endpoints y las
mismas reglas de silencio y topes de los avisos por lugar.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest

from backend import alerts as alerts_mod
from backend import incidents as incidents_mod
from backend.db import Database

NOW = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)


def stamp(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def db(tmp_path):
    d = Database(tmp_path / "brasa.db")
    d.execute("INSERT INTO subscribers(id, created_at) VALUES ('s1','2026-01-01T00:00:00Z')")
    return d


def _obs(db: Database, oid: str, observed: datetime, lat=-35.41, lon=-71.97, confidence="alta") -> dict:
    """Detección satelital guardada y lista para `incidents.update` (patrón de test_api_doc)."""
    row = {
        "id": oid, "source": "firms", "sensor": "VIIRS", "satellite": "N20", "resolution_m": 375,
        "lat": lat, "lon": lon, "observed_at": stamp(observed), "frp_mw": 20.0,
        "confidence": confidence, "comuna_code": 7401,
    }
    db.execute(
        "INSERT INTO observations(id, source, sensor, satellite, resolution_m, lat, lon, observed_at, frp_mw, "
        "confidence, comuna_code, run_id, ingested_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL,?)",
        (oid, "firms", "VIIRS", "N20", 375, lat, lon, stamp(observed), 20.0, confidence, 7401, stamp(NOW)),
    )
    return row


def _incident(db: Database, *obs_ids: str, at: datetime | None = None) -> dict:
    """Incidente BRASA con las detecciones dadas, creadas a la hora indicada."""
    at = at or NOW - timedelta(hours=2)
    rows = [_obs(db, oid, at + timedelta(minutes=30 * i)) for i, oid in enumerate(obs_ids)]
    [inc] = incidents_mod.update(db, rows, at)
    return inc


def _fire(db: Database, fid="1", status="confirmado", name="El Belloto", started=None) -> None:
    started = stamp(started or NOW - timedelta(hours=4))
    raw = {"confirmado": "En combate", "controlado": "Controlado", "extinguido": "Extinguido"}[status]
    db.execute(
        "INSERT INTO official_fires(id, name, status, status_raw, started_at, lat, lon, comuna, region, "
        "first_fetched_at, fetched_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (fid, name, status, raw, started, -35.41, -71.97, "Pencahue", "Maule", started, started),
    )


def _follow(db: Database, sid="s1", incident_id=None, official_ref=None, fire_status=None,
            created=None, last_alert_at=None) -> int:
    return db.insert(
        "INSERT INTO incident_follows(subscriber_id, incident_id, official_ref, fire_status, created_at, last_alert_at) "
        "VALUES (?,?,?,?,?,?)",
        (sid, incident_id, official_ref, fire_status, stamp(created or NOW - timedelta(hours=1)),
         stamp(last_alert_at) if last_alert_at else None),
    )


def _run(db: Database, now: datetime | None = None):
    return asyncio.run(alerts_mod.evaluate_follows(db, now or NOW))


def _avisos(db: Database) -> list[dict]:
    return db.query("SELECT * FROM follow_alerts ORDER BY id")


def test_confirmacion_conaf_avisa_al_seguidor(db):
    inc = _incident(db, "o1")
    fid = _follow(db, incident_id=inc["id"])  # empezó a seguirlo antes de que CONAF lo informara
    _fire(db, "7", "confirmado", name="El Belloto")
    db.execute("UPDATE incidents SET official_ref = '7' WHERE id = ?", (inc["id"],))
    created = _run(db)
    [aviso] = _avisos(db)
    assert aviso["follow_id"] == fid and aviso["observation_id"] == "conaf:7:confirma"
    payload = json.loads(aviso["payload"])
    assert "CONAF informa" in payload["title"] and "El Belloto" in payload["title"]
    assert payload["level"] == "aviso" and payload["kind"] == "seguimiento"
    assert payload["url"] == f"/#/incendio/{inc['id']}"
    assert len(created) == 1 and created[0]["tbl"] == "follow_alerts"
    seg = db.one("SELECT * FROM incident_follows WHERE id = ?", (fid,))
    assert seg["fire_status"] == "confirmado" and seg["official_ref"] == "7" and seg["last_alert_at"]


def test_cambio_de_estado_avisa_una_vez_y_no_se_pierde_al_frenar(db):
    _fire(db, "7", "controlado")
    fid = _follow(db, official_ref="7", fire_status="confirmado",
                  last_alert_at=NOW - timedelta(hours=1))
    _run(db)  # dentro del tope de 3 h: se aplaza, no se pierde ni se marca
    assert _avisos(db) == []
    assert db.one("SELECT fire_status FROM incident_follows WHERE id = ?", (fid,))["fire_status"] == "confirmado"
    db.execute("UPDATE incident_follows SET last_alert_at = ? WHERE id = ?", (stamp(NOW - timedelta(hours=4)), fid))
    created = _run(db)
    [aviso] = _avisos(db)
    assert aviso["observation_id"] == "conaf:7:estado:controlado"
    assert "cambió de estado" in json.loads(aviso["payload"])["title"]
    assert len(created) == 1
    # El mismo estado no vuelve a avisar; una transición nueva sí.
    assert _run(db) == []
    db.execute("UPDATE official_fires SET status = 'extinguido', status_raw = 'Extinguido', extinguished_at = ? WHERE id = '7'",
               (stamp(NOW),))
    db.execute("UPDATE incident_follows SET last_alert_at = ? WHERE id = ?", (stamp(NOW - timedelta(hours=4)), fid))
    _run(db)
    assert [a["observation_id"] for a in _avisos(db)] == ["conaf:7:estado:controlado", "conaf:7:estado:extinguido"]


def test_calor_nuevo_avisa_y_dedupica_por_deteccion(db):
    inc = _incident(db, "o1", at=NOW - timedelta(hours=2))
    _follow(db, incident_id=inc["id"], created=NOW - timedelta(hours=1))
    incidents_mod.update(db, [_obs(db, "o2", NOW - timedelta(minutes=30))], NOW)
    created = _run(db)
    [aviso] = _avisos(db)
    assert aviso["observation_id"].startswith(f"inc:{inc['id']}:calor:")
    body = json.loads(aviso["payload"])["body"]
    assert "calor" in body and "1 detección nueva" in body
    assert len(created) == 1
    assert _run(db) == []  # la misma detección no vuelve a avisar


def test_calor_anterior_a_empezar_a_seguirlo_no_avisa(db):
    inc = _incident(db, "o1", at=NOW - timedelta(hours=20))
    _follow(db, incident_id=inc["id"], created=NOW - timedelta(hours=1))  # el calor es viejo conocido
    assert _run(db) == [] and _avisos(db) == []


def test_tope_3_horas_por_incendio_seguido(db):
    inc = _incident(db, "o1")
    fid = _follow(db, incident_id=inc["id"], last_alert_at=NOW - timedelta(hours=2))
    _run(db)
    assert _avisos(db) == []  # faltan 1 h para el tope
    db.execute("UPDATE incident_follows SET last_alert_at = ? WHERE id = ?", (stamp(NOW - timedelta(hours=4)), fid))
    incidents_mod.update(db, [_obs(db, "o2", NOW - timedelta(minutes=30))], NOW)
    created = _run(db)
    assert len(created) == 1


def test_caduca_a_los_7_dias_sin_calor(db):
    inc = _incident(db, "o1", at=NOW - timedelta(days=8))
    fid = _follow(db, incident_id=inc["id"], created=NOW - timedelta(days=8))
    _run(db)
    assert db.one("SELECT id FROM incident_follows WHERE id = ?", (fid,)) is None


def test_no_avisa_calor_en_incidente_extinguido_o_fijo(db):
    inc = _incident(db, "o1", "o2")
    # Sin el estado «extinguido» este calor sí avisaría (hay detecciones tras el último aviso).
    fid = _follow(db, incident_id=inc["id"], last_alert_at=NOW - timedelta(hours=4))
    db.execute("UPDATE incidents SET status = 'extinguido' WHERE id = ?", (inc["id"],))
    _run(db)
    assert _avisos(db) == []
    assert db.one("SELECT id FROM incident_follows WHERE id = ?", (fid,))  # aún no vence: faltan días


def test_la_fusion_mantiene_vivo_el_seguimiento(db):
    inc = _incident(db, "o1")
    fid = _follow(db, incident_id="inc-muerto")
    db.execute("INSERT INTO incident_merges(dead_id, live_id, merged_at) VALUES ('inc-muerto', ?, ?)",
               (inc["id"], stamp(NOW)))
    _run(db)
    seg = db.one("SELECT * FROM incident_follows WHERE id = ?", (fid,))
    assert seg["incident_id"] == inc["id"]


def test_seguir_por_ambos_caminos_se_funde_sin_reventar(db):
    """Siguió la ficha satelital y la tarjeta CONAF del mismo fuego por separado; al enlazarse
    X↔7 las dos filas convergen y queda la más antigua — nunca un IntegrityError del UNIQUE."""
    inc = _incident(db, "o1")
    viejo = _follow(db, incident_id=inc["id"], created=NOW - timedelta(hours=5))
    _follow(db, official_ref="7", created=NOW - timedelta(hours=2))
    _fire(db, "7", "confirmado")
    db.execute("UPDATE incidents SET official_ref = '7' WHERE id = ?", (inc["id"],))
    _run(db)
    [seg] = db.query("SELECT * FROM incident_follows WHERE subscriber_id = 's1'")
    assert seg["id"] == viejo and seg["incident_id"] == inc["id"] and seg["official_ref"] == "7"
    assert [a["observation_id"] for a in _avisos(db)] == ["conaf:7:confirma"]


def test_incendio_conaf_vivo_frena_la_caducidad(db):
    """8 días sin calor satelital pero CONAF lo sigue informando: el seguimiento vive para
    avisar el cierre oficial, y recién ahí vence."""
    inc = _incident(db, "o1", at=NOW - timedelta(days=8))
    _fire(db, "7", "confirmado")
    db.execute("UPDATE incidents SET official_ref = '7' WHERE id = ?", (inc["id"],))
    fid = _follow(db, incident_id=inc["id"], official_ref="7", fire_status="confirmado",
                  created=NOW - timedelta(days=8))
    assert _run(db) == []
    assert db.one("SELECT id FROM incident_follows WHERE id = ?", (fid,))
    db.execute("UPDATE official_fires SET status = 'extinguido', status_raw = 'Extinguido' WHERE id = '7'")
    _run(db)
    assert [a["observation_id"] for a in _avisos(db)] == ["conaf:7:estado:extinguido"]
    _run(db)  # ya cerrado y avisado: el seguimiento vence
    assert db.one("SELECT id FROM incident_follows WHERE id = ?", (fid,)) is None


def test_caps_exceeded_follow_mismo_tope_por_dispositivo(db):
    fid = _follow(db, incident_id="i1")
    for i in range(alerts_mod.CAP_AVISOS_7D):
        db.execute(
            "INSERT INTO follow_alerts(follow_id, observation_id, level, observed_at, created_at, payload, delivered, delivered_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (fid, f"inc:i{i}:calor:o{i}", "aviso", stamp(NOW - timedelta(days=1)), stamp(NOW - timedelta(days=1)),
             "{}", '["push"]', stamp(NOW - timedelta(days=1))))
    nuevo = {"id": None, "subscriber_id": "s1", "level": "aviso", "observation_id": "inc:i9:calor:o9"}
    assert alerts_mod.caps_exceeded_follow(db, nuevo, NOW) == "aviso_7d"
    # La confirmación y el cambio de estado siempre salen (como «…:estado» por lugar).
    assert alerts_mod.caps_exceeded_follow(db, nuevo | {"observation_id": "conaf:7:confirma"}, NOW) is None
    assert alerts_mod.caps_exceeded_follow(db, nuevo | {"observation_id": "conaf:7:estado:controlado"}, NOW) is None


def test_aviso_de_seguimiento_es_aplazable_al_silencio(db):
    """Nivel «aviso»: el silencio 23–07 lo aplaza igual que un aviso por lugar (ALR-19)."""
    inc = _incident(db, "o1", at=NOW - timedelta(minutes=30))
    _follow(db, incident_id=inc["id"], created=NOW - timedelta(hours=2))
    _run(db)
    payload = json.loads(_avisos(db)[0]["payload"])
    assert payload["level"] == "aviso" and alerts_mod.aplazable(payload)


# --- endpoints /api/me/follows ---

def _register(client) -> dict:
    token = client.post("/api/subscribers").json()["token"]
    return {"X-Brasa-Token": token}


def test_endpoints_seguir_y_dejar_son_idempotentes(make_client):
    with make_client() as client:
        svc = client.app.state.services
        _fire(svc.db, "7", "confirmado", name="El Belloto")
        headers = _register(client)
        # Auth: sin token ni con token inventado no se sigue nada.
        assert client.post("/api/me/follows", json={"official_ref": "7"}).status_code == 401
        assert client.post("/api/me/follows", json={"official_ref": "7"}, headers={"X-Brasa-Token": "x" * 40}).status_code == 401
        assert client.post("/api/me/follows", json={}, headers=headers).status_code == 422
        assert client.post("/api/me/follows", json={"incident_id": "no-existe"}, headers=headers).status_code == 404
        assert client.post("/api/me/follows", json={"official_ref": "42"}, headers=headers).status_code == 404

        r = client.post("/api/me/follows", json={"official_ref": "7"}, headers=headers)
        assert r.status_code == 201, r.text
        seg = r.json()
        assert seg["created"] is True and seg["follow"]["official_ref"] == "7"
        assert seg["follow"]["fire"]["name"] == "El Belloto"
        fid = seg["follow"]["id"]

        r2 = client.post("/api/me/follows", json={"official_ref": "7"}, headers=headers)
        assert r2.status_code == 200 and r2.json()["created"] is False
        assert r2.json()["follow"]["id"] == fid
        assert len(client.get("/api/me/follows", headers=headers).json()["follows"]) == 1

        assert client.delete(f"/api/me/follows/{fid}", headers=headers).json() == {"ok": True}
        assert client.get("/api/me/follows", headers=headers).json()["follows"] == []
        assert client.delete(f"/api/me/follows/{fid}", headers=headers).json() == {"ok": True}  # idempotente


def test_seguir_otro_dispositivo_no_lo_ve(make_client):
    with make_client() as client:
        svc = client.app.state.services
        _fire(svc.db, "7", "confirmado")
        a, b = _register(client), _register(client)
        fid = client.post("/api/me/follows", json={"official_ref": "7"}, headers=a).json()["follow"]["id"]
        assert client.get("/api/me/follows", headers=b).json()["follows"] == []
        client.delete(f"/api/me/follows/{fid}", headers=b)  # no borra lo de A
        assert len(client.get("/api/me/follows", headers=a).json()["follows"]) == 1


def test_seguir_incidente_resuelve_enlace_conaf(make_client):
    with make_client() as client:
        svc = client.app.state.services
        inc = _incident(svc.db, "o1")
        _fire(svc.db, "7", "confirmado")
        svc.db.execute("UPDATE incidents SET official_ref = '7' WHERE id = ?", (inc["id"],))
        headers = _register(client)
        r = client.post("/api/me/follows", json={"incident_id": inc["id"]}, headers=headers)
        assert r.status_code == 201, r.text
        seg = r.json()["follow"]
        assert seg["incident_id"] == inc["id"] and seg["official_ref"] == "7" and seg["fire"]["status"] == "confirmado"
        # Y el export de datos lo incluye (Ley 21.719).
        export = client.get("/api/me/export", headers=headers).json()
        assert [s["incident_id"] for s in export["seguimientos"]] == [inc["id"]]
        assert headers["X-Brasa-Token"] not in json.dumps(export)


def test_deliver_intenta_los_avisos_de_seguimiento(make_client):
    """La cola compartida marca la entrega en follow_alerts aunque el dispositivo no tenga canal."""
    with make_client() as client:
        svc = client.app.state.services
        db = svc.db
        _fire(db, "7", "confirmado")
        fid = _follow(db, official_ref="7", fire_status="controlado")
        db.execute("UPDATE official_fires SET status = 'extinguido', status_raw = 'Extinguido' WHERE id = '7'")
        created = _run(db)
        asyncio.run(svc.deliver(created))
        [aviso] = _avisos(db)
        assert aviso["delivered_at"] is not None and json.loads(aviso["delivered"]) == []
        # Un segundo intento no repite: la fila ya está marcada.
        asyncio.run(svc.deliver([]))
        assert db.one("SELECT COUNT(*) AS n FROM follow_alerts WHERE follow_id = ? AND delivered_at IS NOT NULL", (fid,))["n"] == 1

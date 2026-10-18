"""Alertas: no despertar a nadie por un foco de ayer, y no perder avisos si el proceso muere.

Dos huecos que aparecieron al revisar FIX-01:
1. Con FIRMS pidiendo dos días, el primer ciclo tras una caída o una base nueva puede insertar
   detecciones de ayer. Si generan alerta, el aviso diría «foco cerca» con el viento y el riesgo de
   ahora para un fuego de hace 26 horas.
2. Guardar la detección, marcarla como procesada y avisar son pasos separados: un reinicio en medio
   dejaba la detección registrada con ok=1 y sin alerta, y el reintento ya no la miraba.
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import datetime, timedelta, timezone

import httpx

from backend import alerts
from backend import services as services_mod
from backend.db import Database
from tests.conftest import json_response

NOW = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)


def observation(ident: str, minutes_ago: int) -> dict:
    return {"id": ident, "source": "firms", "sensor": "VIIRS", "satellite": "N20", "resolution_m": 375,
            "lat": -33.05, "lon": -71.55, "frp_mw": 20.0, "confidence": "alta", "comuna_code": 13101,
            "observed_at": (NOW - timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")}


def place(db: Database, radius_km: float = 10) -> None:
    db.execute("INSERT INTO subscribers(id, created_at) VALUES ('s1','2026-01-01T00:00:00Z')")
    db.execute("INSERT INTO places(id, subscriber_id, name, kind, lat, lon, radius_km, created_at) "
               "VALUES ('p1','s1','Casa','casa',-33.05,-71.55,?,'2026-01-01T00:00:00Z')", (radius_km,))


def test_a_detection_from_yesterday_does_not_wake_anyone(tmp_path):
    db = Database(tmp_path / "brasa.db")
    place(db)
    assert asyncio.run(alerts.evaluate(db, [observation("vieja", 26 * 60)], now=NOW)) == []
    assert db.one("SELECT COUNT(*) AS n FROM alerts")["n"] == 0


def test_a_recent_detection_does_wake_someone(tmp_path):
    db = Database(tmp_path / "brasa.db")
    place(db)
    created = asyncio.run(alerts.evaluate(db, [observation("nueva", 10)], now=NOW))
    assert len(created) == 1 and created[0]["level"] == "urgente"


def test_the_age_limit_is_the_same_for_the_whole_system(tmp_path):
    db = Database(tmp_path / "brasa.db")
    place(db)
    just_inside = observation("borde", alerts.MAX_AGE_H * 60 - 1)
    just_outside = observation("fuera", alerts.MAX_AGE_H * 60 + 1)
    assert alerts.is_recent(just_inside, NOW) is True
    assert alerts.is_recent(just_outside, NOW) is False
    assert asyncio.run(alerts.evaluate(db, [just_outside], now=NOW)) == []


def test_the_old_detection_stays_in_the_database(tmp_path):
    """No se borra: sirve para el mapa y para el incidente; solo no genera aviso."""
    db = Database(tmp_path / "brasa.db")
    old = observation("vieja", 26 * 60)
    db.execute("INSERT INTO observations(id, source, sensor, satellite, resolution_m, lat, lon, observed_at, "
               "frp_mw, confidence, comuna_code, run_id, ingested_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL,?)",
               (old["id"], old["source"], old["sensor"], old["satellite"], old["resolution_m"], old["lat"],
                old["lon"], old["observed_at"], old["frp_mw"], old["confidence"], old["comuna_code"], old["observed_at"]))
    assert db.one("SELECT COUNT(*) AS n FROM observations")["n"] == 1


def store(db: Database, obs: dict) -> None:
    """Inserta la observación como la dejaría la ingesta (sin marcar como evaluada)."""
    db.execute("INSERT INTO observations(id, source, sensor, satellite, resolution_m, lat, lon, observed_at, "
               "frp_mw, confidence, comuna_code, run_id, ingested_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL,?)",
               (obs["id"], obs["source"], obs["sensor"], obs["satellite"], obs["resolution_m"], obs["lat"],
                obs["lon"], obs["observed_at"], obs["frp_mw"], obs["confidence"], obs["comuna_code"],
                obs["observed_at"]))


def test_pending_alerts_are_recovered_after_a_restart(make_client, monkeypatch):
    monkeypatch.setattr(services_mod, "utcnow", lambda: NOW)
    with make_client() as client:
        svc = client.app.state.services
        place(svc.db)
        # Como si el proceso hubiera muerto tras guardarla: está en la base y no se evaluó.
        store(svc.db, observation("huerfana", 20))
        assert [row["id"] for row in svc.pending_alert_observations()] == ["huerfana"]
        created = asyncio.run(alerts.evaluate(svc.db, svc.pending_alert_observations(), now=NOW))
        assert len(created) == 1
        # Avisar no es lo que la saca de pendientes: eso lo hace el marcado explícito del ciclo.
        assert [row["id"] for row in svc.pending_alert_observations()] == ["huerfana"]
        assert svc.mark_alerts_evaluated(svc.pending_alert_observations()) == 1
        assert svc.pending_alert_observations() == []


def test_a_detection_without_any_nearby_place_is_marked_too(make_client, monkeypatch):
    """La mayoría no tiene lugares cerca y nunca crearía alerta: si siguiera pendiente, se
    reconsultaría y reevaluaría cada diez minutos durante seis horas."""
    monkeypatch.setattr(services_mod, "utcnow", lambda: NOW)
    with make_client() as client:
        svc = client.app.state.services
        store(svc.db, observation("sin-vecinos", 10))     # no hay ningún lugar guardado
        pending = svc.pending_alert_observations()
        assert [row["id"] for row in pending] == ["sin-vecinos"]
        assert asyncio.run(alerts.evaluate(svc.db, pending, now=NOW)) == []
        svc.mark_alerts_evaluated(pending)
        assert svc.pending_alert_observations() == []


def test_the_cycle_marks_what_it_evaluated(make_client, web):
    """El ciclo deja marcadas sus detecciones, avisen o no: si no, volverían cada diez minutos."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    body = ("latitude,longitude,bright_ti4,acq_date,acq_time,frp,confidence,daynight\n"
            f"-33.05,-71.55,340.0,{today},0130,10.0,n,N\n")
    web.add(lambda r: "firms" in r.url.host, lambda r: httpx.Response(200, text=body))
    with make_client(FIRMS_MAP_KEY="k-123", GOES_ENABLED="0") as client:
        svc = client.app.state.services
        asyncio.run(svc.ingest_cycle())
        assert svc.pending_alert_observations() == []
        row = svc.db.one("SELECT alerts_evaluated_at FROM observations LIMIT 1")
        assert row["alerts_evaluated_at"]


def test_the_migration_marks_observations_already_evaluated(tmp_path):
    """Las filas anteriores a la columna ya pasaron por aviso: sin la marca, la recuperación las
    vería como pendientes y una ya avisada podía tapar a un foco nuevo (la evaluación solo mira
    la detección más cercana de cada lugar)."""
    work = sqlite3.connect(tmp_path / "work.db")
    work.execute("""CREATE TABLE observations(id TEXT PRIMARY KEY, source TEXT, sensor TEXT, satellite TEXT,
                    resolution_m INTEGER, lat REAL, lon REAL, observed_at TEXT, frp_mw REAL,
                    brightness_k REAL, confidence TEXT, confidence_raw TEXT, comuna_code INTEGER,
                    run_id INTEGER, ingested_at TEXT)""")
    work.execute("INSERT INTO observations(id, source, observed_at, lat, lon, ingested_at) "
                 "VALUES ('vieja','firms','2026-10-18T00:00:00Z',-33.0,-71.5,'2026-10-18T00:01:00Z')")
    work.commit()
    work.close()
    db = Database(tmp_path / "brasa.db")   # adjunta work.db y corre _migrate_work
    assert db.one("SELECT alerts_evaluated_at FROM observations")["alerts_evaluated_at"] == "2026-10-18T00:01:00Z"
    assert db.query("SELECT id FROM observations WHERE alerts_evaluated_at IS NULL") == []


def test_the_migration_marks_alerts_already_attempted(tmp_path):
    """Las alertas ya escritas pasaron por su intento de entrega: quedan con marca para que el
    reintento solo tome las que quedaron a medio entregar."""
    main = sqlite3.connect(tmp_path / "brasa.db")
    main.execute("""CREATE TABLE alerts(id INTEGER PRIMARY KEY AUTOINCREMENT, place_id TEXT,
                    observation_id TEXT, level TEXT, distance_km REAL, bearing_deg REAL, upwind INTEGER,
                    lat REAL, lon REAL, observed_at TEXT, created_at TEXT, payload TEXT,
                    delivered TEXT DEFAULT '[]', UNIQUE(place_id, observation_id))""")
    main.execute("INSERT INTO alerts(place_id, observation_id, level, distance_km, bearing_deg, upwind, "
                 "lat, lon, observed_at, created_at, payload, delivered) VALUES ('p1','o1','aviso',1,0,0,"
                 "-33,-71,'2026-10-18T00:00:00Z','2026-10-18T00:05:00Z','{}','[\"push\"]')")
    main.commit()
    main.close()
    db = Database(tmp_path / "brasa.db")
    assert db.one("SELECT delivered_at FROM alerts")["delivered_at"] == "2026-10-18T00:05:00Z"


def test_an_alert_left_undelivered_is_retried_from_the_database(make_client, web):
    """La alerta se escribe antes de mandarla: si el proceso se cortó antes de entregar, la
    siguiente entrega la reintenta desde la base (su detección ya está evaluada)."""
    sent = []

    def telegram(request):
        sent.append(json.loads(request.content))
        return json_response({"ok": True, "result": {}})

    web.add(lambda r: "telegram" in r.url.host, telegram)
    with make_client(TELEGRAM_BOT_TOKEN="123:tok") as client:
        svc = client.app.state.services
        place(svc.db)
        svc.db.execute("UPDATE subscribers SET telegram_chat_id = '777' WHERE id = 's1'")
        payload = {"title": "Foco", "body": "cuerpo", "footer": "pie", "level": "aviso", "url": "/#/mapa"}
        svc.db.execute("INSERT INTO alerts(place_id, observation_id, level, distance_km, bearing_deg, upwind, "
                       "lat, lon, observed_at, created_at, payload) VALUES ('p1','o1','aviso',1.0,0,0,"
                       "-33.05,-71.55,'2026-10-18T00:00:00Z','2026-10-18T00:01:00Z',?)",
                       (json.dumps(payload),))
        asyncio.run(svc.deliver([]))
        assert sent and sent[0]["chat_id"] == "777"
        row = svc.db.one("SELECT delivered, delivered_at FROM alerts")
        assert json.loads(row["delivered"]) == ["telegram"] and row["delivered_at"]
        # Una segunda pasada no vuelve a mandarla.
        asyncio.run(svc.deliver([]))
        assert len(sent) == 1

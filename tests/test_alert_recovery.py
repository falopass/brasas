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
from datetime import datetime, timedelta, timezone

import httpx

from backend import alerts
from backend.db import Database

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


def test_pending_alerts_are_recovered_after_a_restart(make_client):
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


def test_a_detection_without_any_nearby_place_is_marked_too(make_client):
    """La mayoría no tiene lugares cerca y nunca crearía alerta: si siguiera pendiente, se
    reconsultaría y reevaluaría cada diez minutos durante seis horas."""
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

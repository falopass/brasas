"""Frescura del dato e historial de alertas: el contrato que consume la interfaz nueva.

La regla de los 30 minutos vive en el servidor (`backend/freshness.py`) y se publica en
`/api/status`; el historial se pagina en `/api/alerts` sin agregar tablas: las alertas ya se
guardaban por lugar y dispositivo.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from backend import freshness

STAMP = "%Y-%m-%dT%H:%M:%SZ"


def test_freshness_marks_recent_fresh_and_old_stale():
    now = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)
    recent = (now - timedelta(minutes=5)).strftime(STAMP)
    old = (now - timedelta(minutes=45)).strftime(STAMP)
    assert freshness.status(recent, now)["stale"] is False
    assert freshness.status(old, now) == {"last_ingest_at": old, "age_seconds": 2700,
                                          "stale_after_s": 1800, "stale": True}


def test_freshness_without_data_is_never_dressed_as_fresh():
    missing = freshness.status(None)
    assert missing["stale"] is True and missing["age_seconds"] is None
    assert freshness.age_seconds("no es una fecha") is None


def test_status_endpoint_publishes_the_freshness_contract(make_client):
    with make_client() as client:
        body = client.get("/api/status").json()
    assert set(body["freshness"]) == {"last_ingest_at", "age_seconds", "stale_after_s", "stale"}
    assert body["freshness"]["stale_after_s"] == 1800


def seed_alerts(client, count: int = 4, delivered: list[str] | None = None) -> dict[str, str]:
    """Crea un dispositivo con un lugar y `count` alertas, una por hora hacia atrás."""
    svc = client.app.state.services
    token = client.post("/api/subscribers").json()["token"]
    headers = {"X-Brasa-Token": token}
    place = client.post("/api/places", json={"name": "Casa", "lat": -33.05, "lon": -71.55, "radius_km": 10},
                        headers=headers).json()
    base = datetime.now(timezone.utc)
    for index in range(count):
        moment = (base - timedelta(hours=index)).strftime(STAMP)
        payload = {"title": f"Foco de calor {index}", "place": {"name": "Casa"}, "distance_km": 3.2,
                   "url": "/#/mapa?lat=-33.06&lon=-71.54&z=12"}
        svc.db.execute(
            "INSERT INTO alerts(place_id, observation_id, level, distance_km, bearing_deg, upwind, lat, lon, "
            "observed_at, created_at, payload, delivered) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (place["id"], f"obs-{index}", "urgente" if index == 0 else "aviso", 3.2, 90, 0, -33.06, -71.54,
             moment, moment, json.dumps(payload), json.dumps(delivered if delivered is not None else ["push"])))
    return headers


def test_alert_history_paginates_without_repeating(make_client):
    with make_client() as client:
        headers = seed_alerts(client, 4)
        first = client.get("/api/alerts?limit=2", headers=headers).json()
        assert len(first["alerts"]) == 2 and first["total"] == 4 and first["has_more"] is True
        second = client.get(f"/api/alerts?limit=2&before={first['alerts'][-1]['created_at']}",
                            headers=headers).json()
        assert len(second["alerts"]) == 2 and second["has_more"] is False
        assert {a["id"] for a in first["alerts"]}.isdisjoint({a["id"] for a in second["alerts"]})


def test_alert_history_keeps_the_delivery_channels(make_client):
    """«Por dónde te llegó» es parte del historial: si no salió por ningún canal, se dice."""
    with make_client() as client:
        headers = seed_alerts(client, 1, delivered=[])
        alert = client.get("/api/alerts", headers=headers).json()["alerts"][0]
        assert alert["delivered"] == []
        assert alert["title"] == "Foco de calor 0" and alert["level"] == "urgente"


def test_alert_history_is_per_device(make_client):
    with make_client() as client:
        mine = seed_alerts(client, 2)
        other = client.post("/api/subscribers").json()["token"]
        assert client.get("/api/alerts", headers={"X-Brasa-Token": other}).json()["total"] == 0
        assert client.get("/api/alerts", headers=mine).json()["total"] == 2


def test_alert_history_requires_the_device_token(make_client):
    with make_client() as client:
        assert client.get("/api/alerts").status_code == 401

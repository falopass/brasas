"""Historial de alertas: el contrato que consume la interfaz nueva.

El historial se pagina en `/api/alerts` sin agregar tablas: las alertas ya se
guardaban por lugar y dispositivo. La frescura del dato vive en `test_freshness.py`.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

STAMP = "%Y-%m-%dT%H:%M:%SZ"


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


def test_el_cursor_no_pierde_avisos_del_mismo_segundo(make_client):
    """ALR-17: varios avisos comparten segundo; el cursor «created_at|id» no los pierde."""
    with make_client() as client:
        headers = seed_alerts(client, 3)
        client.app.state.services.db.execute("UPDATE alerts SET created_at = '2026-10-19T12:00:00Z'")
        first = client.get("/api/alerts?limit=2", headers=headers).json()
        assert len(first["alerts"]) == 2 and first["has_more"] is True
        cursor = first["next_before"]
        assert cursor and "|" in cursor
        second = client.get("/api/alerts", params={"limit": 2, "before": cursor}, headers=headers).json()
        assert len(second["alerts"]) == 1 and second["has_more"] is False
        assert second["next_before"] is None
        ids = [a["id"] for a in first["alerts"] + second["alerts"]]
        assert len(set(ids)) == 3 and ids == sorted(ids, reverse=True)


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

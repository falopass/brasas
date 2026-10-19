"""ALR-17: el historial pagina con un cursor «<created_at>|<id>» y no pierde avisos.

`created_at` tiene precisión de segundos: en un ciclo de ingesta varios avisos de lugares
distintos comparten el mismo segundo. Paginar solo con `created_at` saltaba todos los que
empataban con el último de la página anterior; el cursor nuevo desempata con el `id` y el
servidor lo devuelve como `next_before`. Un `before` sin «|» sigue funcionando (clientes
antiguos).
"""
from __future__ import annotations

import json

from tests.test_features import seed_alerts

MOMENT = "2026-10-19T12:00:00Z"


def seed_same_second(client, count: int = 3) -> dict[str, str]:
    """Un dispositivo con un lugar y `count` avisos con el MISMO created_at."""
    svc = client.app.state.services
    token = client.post("/api/subscribers").json()["token"]
    headers = {"X-Brasa-Token": token}
    place = client.post("/api/places", json={"name": "Casa", "lat": -33.05, "lon": -71.55, "radius_km": 10},
                        headers=headers).json()
    for index in range(count):
        payload = {"title": f"Foco {index}", "place": {"name": "Casa"}, "distance_km": 3.2}
        svc.db.execute(
            "INSERT INTO alerts(place_id, observation_id, level, distance_km, bearing_deg, upwind, lat, lon, "
            "observed_at, created_at, payload, delivered) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (place["id"], f"obs-{index}", "aviso", 3.2, 90, 0, -33.06, -71.54,
             MOMENT, MOMENT, json.dumps(payload), json.dumps(["push"])))
    return headers


def test_el_cursor_no_pierde_avisos_del_mismo_segundo(make_client):
    with make_client() as client:
        headers = seed_same_second(client, 3)
        first = client.get("/api/alerts?limit=2", headers=headers).json()
        assert len(first["alerts"]) == 2 and first["has_more"] is True
        cursor = first["next_before"]
        assert cursor and "|" in cursor
        second = client.get("/api/alerts", params={"limit": 2, "before": cursor}, headers=headers).json()
        assert len(second["alerts"]) == 1 and second["has_more"] is False
        assert second["next_before"] is None
        ids = [a["id"] for a in first["alerts"] + second["alerts"]]
        assert len(set(ids)) == 3 and ids == sorted(ids, reverse=True)


def test_before_sin_separador_sigue_paginando_por_fecha(make_client):
    with make_client() as client:
        headers = seed_alerts(client, 3)
        first = client.get("/api/alerts?limit=2", headers=headers).json()
        second = client.get(f"/api/alerts?limit=2&before={first['alerts'][-1]['created_at']}",
                            headers=headers).json()
        assert len(second["alerts"]) == 1 and second["has_more"] is False
        assert {a["id"] for a in first["alerts"]}.isdisjoint({a["id"] for a in second["alerts"]})

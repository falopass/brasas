"""Contrato HTTP del comparador semanal (`GET /api/risk/{code}/trend`).

`tests/test_trend.py` cubre la lógica del módulo y algunos casos del endpoint; este archivo fija
el contrato completo de la ruta antes de que la interfaz la consuma (UX-45): 404, rango de
`weeks`, respuesta vacía sin inventar comparaciones y ausencia de datos personales.
"""

from __future__ import annotations

from datetime import timedelta

from tests.test_trend import seed_risk, seed_snapshot, today_chile


def test_404_for_an_unknown_comuna(make_client):
    with make_client() as client:
        resp = client.get("/api/risk/99999/trend")
        assert resp.status_code == 404
        assert "comuna" in resp.json()["detail"].lower()


def test_empty_comuna_returns_zeroes_without_inventing_comparisons(make_client):
    with make_client() as client:
        resp = client.get("/api/risk/5109/trend")
        assert resp.status_code == 200
        body = resp.json()
        assert body["rows"] == []
        assert body["summary"] == {"sube": 0, "baja": 0, "igual": 0, "sin_anterior": 0}
        assert body["snapshots_from"] is None
        assert "expectativa" in body["method"]  # no promete lo que ocurrió


def test_compare_one_week_apart_and_ignore_other_offsets(make_client):
    with make_client() as client:
        svc = client.app.state.services
        today = today_chile()
        seed_risk(
            svc.db,
            5109,
            [
                (today, "bajo", "moderado", 40),
                (today + timedelta(days=1), "alto", "bajo", 20),
                (today + timedelta(days=2), "bajo", "alto", 80),
                (today + timedelta(days=3), "bajo", "alto", 80),
            ],
        )
        week = timedelta(days=7)
        seed_snapshot(svc.db, 5109, today - week, today, "bajo", 10)  # → sube
        seed_snapshot(svc.db, 5109, today + timedelta(days=1) - week, today + timedelta(days=1), "alto", 90)  # → baja
        seed_snapshot(svc.db, 5109, today + timedelta(days=2) - week, today + timedelta(days=2), "alto", 85)  # → igual
        seed_snapshot(
            svc.db, 5109, today + timedelta(days=3) - timedelta(days=6), today + timedelta(days=3), "extremo", 99
        )  # desfase distinto: no cuenta

        resp = client.get("/api/risk/5109/trend?weeks=1")
        assert resp.status_code == 200
        by_day = {r["target_date"]: r for r in resp.json()["rows"]}
        assert by_day[today.isoformat()]["change"] == "sube"
        assert by_day[(today + timedelta(days=1)).isoformat()]["change"] == "baja"
        assert by_day[(today + timedelta(days=2)).isoformat()]["change"] == "igual"
        assert by_day[(today + timedelta(days=3)).isoformat()]["change"] == "sin_anterior"
        assert resp.json()["summary"] == {"sube": 1, "baja": 1, "igual": 1, "sin_anterior": 1}


def test_weeks_range_is_validated(make_client):
    with make_client() as client:
        assert client.get("/api/risk/5109/trend?weeks=0").status_code == 422
        assert client.get("/api/risk/5109/trend?weeks=9").status_code == 422
        assert client.get("/api/risk/5109/trend?weeks=8").status_code == 200


def test_response_carries_no_personal_data(make_client):
    with make_client() as client:
        svc = client.app.state.services
        today = today_chile()
        seed_risk(svc.db, 5109, [(today, "bajo", "alto", 80)])
        seed_snapshot(svc.db, 5109, today - timedelta(days=7), today, "moderado", 50)

        def keys(obj):
            found = set()
            if isinstance(obj, dict):
                for k, v in obj.items():
                    found.add(k)
                    found |= keys(v)
            elif isinstance(obj, list):
                for v in obj:
                    found |= keys(v)
            return found

        body = client.get("/api/risk/5109/trend").json()
        assert not keys(body) & {"subscriber_id", "place_id", "lat", "lon", "latitude", "longitude"}

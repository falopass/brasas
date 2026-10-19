"""QA-52: el contrato de `GET /api/places/{id}/history` tal como lo consume «Mi zona».

test_place_history.py (UX-17) ya fija la cercanía (2× el radio), la exclusión de fuentes
de calor fijas, el orden por `last_seen_at` descendente, el tope de 10 y que el historial
es solo del dispositivo dueño del lugar. Aquí queda el resto del contrato: la forma exacta
de la respuesta, `distance_km` como haversine redondeado y los límites 1..90 de `days`.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.geo import haversine_km
from tests.test_place_history import _incident, _setup, _stamp


def test_la_respuesta_tiene_la_forma_que_la_vista_espera(make_client):
    with make_client() as client:
        db, headers, place_id = _setup(client)
        now = _stamp(datetime.now(timezone.utc))
        _incident(db, "fuego", -33.10, -71.55, now, status="confirmado")
        _incident(db, "alto-mar", -33.12, -71.55, now, comuna_code=None)  # sin comuna: null, no se omite
        body = client.get(f"/api/places/{place_id}/history", headers=headers).json()
        assert set(body) == {"days", "incidents"}
        assert isinstance(body["days"], int) and body["days"] == 30
        assert len(body["incidents"]) == 2
        for item in body["incidents"]:
            assert set(item) == {"id", "status", "distance_km", "first_seen_at", "last_seen_at", "n_obs", "comuna"}
            assert isinstance(item["id"], str) and isinstance(item["status"], str)
            assert isinstance(item["distance_km"], float) and isinstance(item["n_obs"], int)
            assert isinstance(item["first_seen_at"], str) and item["first_seen_at"].endswith("Z")
            assert isinstance(item["last_seen_at"], str) and item["last_seen_at"].endswith("Z")
        by_id = {i["id"]: i for i in body["incidents"]}
        assert by_id["fuego"]["comuna"] == "Santiago"
        assert by_id["alto-mar"]["comuna"] is None


def test_distance_km_es_el_haversine_redondeado_a_dos_decimales(make_client):
    with make_client() as client:
        db, headers, place_id = _setup(client)
        _incident(db, "fuego", -33.17, -71.62, _stamp(datetime.now(timezone.utc)))
        item = client.get(f"/api/places/{place_id}/history", headers=headers).json()["incidents"][0]
        esperado = haversine_km(-33.05, -71.55, -33.17, -71.62)
        assert 0 < esperado < 20  # el punto de prueba queda dentro del 2× radio
        assert item["distance_km"] == round(esperado, 2)
        assert item["distance_km"] == round(item["distance_km"], 2)


def test_days_fuera_de_1_a_90_da_422(make_client):
    with make_client() as client:
        _db, headers, place_id = _setup(client)
        for valor in ("0", "91", "-5", "abc"):
            res = client.get(f"/api/places/{place_id}/history?days={valor}", headers=headers)
            assert res.status_code == 422, f"days={valor} debió rechazarse"
        res = client.get(f"/api/places/{place_id}/history?days=90", headers=headers)
        assert res.status_code == 200 and res.json()["days"] == 90


def test_days_90_alcanza_incidentes_de_hasta_noventa_dias(make_client):
    with make_client() as client:
        db, headers, place_id = _setup(client)
        now = datetime.now(timezone.utc)
        _incident(db, "dentro", -33.10, -71.55, _stamp(now - timedelta(days=89)))
        _incident(db, "fuera", -33.10, -71.55, _stamp(now - timedelta(days=91)))
        res = client.get(f"/api/places/{place_id}/history?days=30", headers=headers)
        assert res.json()["incidents"] == []
        ids = {i["id"] for i in client.get(f"/api/places/{place_id}/history?days=90", headers=headers).json()["incidents"]}
        assert ids == {"dentro"}

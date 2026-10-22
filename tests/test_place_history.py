"""Contrato de `GET /api/places/{id}/history` (UX-17 y QA-52).

El historial lista los incidentes recientes dentro de 2× el radio del lugar, es del
dispositivo dueño (sin token 401; con el token de otro, 404) y excluye las fuentes de
calor fijas. Aquí quedan la cercanía, el orden, el tope de 10, la forma exacta de la
respuesta, `distance_km` como haversine redondeado y los límites 1..90 de `days`.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.geo import haversine_km


def _stamp(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _incident(db, ident: str, lat: float, lon: float, last_seen: str, *, status: str = "posible",
              fixed: int = 0, comuna_code: int = 13101, first_seen: str | None = None) -> None:
    first_seen = first_seen or last_seen
    db.execute("INSERT INTO incidents(id, status, status_changed_at, first_seen_at, last_seen_at, lat, lon, min_lat, "
               "max_lat, min_lon, max_lon, n_obs, n_reliable, sensors, comuna_code, fixed_source, updated_at) "
               "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
               (ident, status, last_seen, first_seen, last_seen, lat, lon, lat - 0.01, lat + 0.01,
                lon - 0.01, lon + 0.01, 3, 3, "VIIRS", comuna_code, fixed, last_seen))


def _setup(client):
    """Un dispositivo con un lugar en (-33.05, -71.55) con aviso a 10 km (historia: hasta 20 km)."""
    token = client.post("/api/subscribers").json()["token"]
    headers = {"X-Brasa-Token": token}
    place = client.post("/api/places", json={"name": "Casa", "lat": -33.05, "lon": -71.55, "radius_km": 10}, headers=headers).json()
    return client.app.state.services.db, headers, place["id"]


def test_solo_los_incidentes_dentro_del_doble_del_radio(make_client):
    with make_client() as client:
        db, headers, place_id = _setup(client)
        now = datetime.now(timezone.utc)
        for i in range(3):  # ~5,5 km por cada 0,05° de latitud: dentro de los 20 km
            # Una hora de margen: con `days=2` exacto, `cerca-1` quedaba justo en el borde de la
            # ventana y el test fallaba si el reloj cambiaba de segundo entre insertar y consultar.
            _incident(db, f"cerca-{i}", -33.05 + 0.05 * (i + 1), -71.55, _stamp(now - timedelta(days=i + 1) + timedelta(hours=1)))
        _incident(db, "lejos", -33.05 + 0.6, -71.55, _stamp(now - timedelta(days=1)))   # ~67 km: fuera
        _incident(db, "viejo", -33.10, -71.55, _stamp(now - timedelta(days=40)))        # dentro, pero > 30 días
        res = client.get(f"/api/places/{place_id}/history", headers=headers)
        assert res.status_code == 200
        body = res.json()
        assert body["days"] == 30
        assert [i["id"] for i in body["incidents"]] == ["cerca-0", "cerca-1", "cerca-2"]  # más recientes primero
        item = body["incidents"][0]
        assert item["status"] == "posible" and item["n_obs"] == 3 and item["comuna"] == "Santiago"
        assert 5 < item["distance_km"] < 6
        # El parámetro `days` acota la ventana: con 2 días solo quedan los dos más nuevos.
        body = client.get(f"/api/places/{place_id}/history?days=2", headers=headers).json()
        assert body["days"] == 2 and [i["id"] for i in body["incidents"]] == ["cerca-0", "cerca-1"]


def test_una_fuente_fija_no_aparece(make_client):
    with make_client() as client:
        db, headers, place_id = _setup(client)
        now = _stamp(datetime.now(timezone.utc))
        _incident(db, "volcan", -33.08, -71.55, now, fixed=1)
        _incident(db, "fuego", -33.10, -71.55, now, status="confirmado")
        body = client.get(f"/api/places/{place_id}/history", headers=headers).json()
        assert [i["id"] for i in body["incidents"]] == ["fuego"]


def test_el_historial_es_del_dueno_del_lugar(make_client):
    with make_client() as client:
        db, headers, place_id = _setup(client)
        _incident(db, "fuego", -33.10, -71.55, _stamp(datetime.now(timezone.utc)))
        assert client.get(f"/api/places/{place_id}/history").status_code == 401
        otro = {"X-Brasa-Token": client.post("/api/subscribers").json()["token"]}
        assert client.get(f"/api/places/{place_id}/history", headers=otro).status_code == 404
        assert client.get("/api/places/no-existe/history", headers=headers).status_code == 404


def test_el_tope_es_10(make_client):
    with make_client() as client:
        db, headers, place_id = _setup(client)
        now = datetime.now(timezone.utc)
        for i in range(12):
            _incident(db, f"foco-{i:02d}", -33.05 - 0.003 * i, -71.55, _stamp(now - timedelta(hours=i)))
        body = client.get(f"/api/places/{place_id}/history", headers=headers).json()
        assert len(body["incidents"]) == 10
        assert "foco-11" not in {i["id"] for i in body["incidents"]}  # el más viejo queda fuera


def test_la_respuesta_tiene_la_forma_y_el_haversine_redondeado(make_client):
    with make_client() as client:
        db, headers, place_id = _setup(client)
        now = _stamp(datetime.now(timezone.utc))
        _incident(db, "fuego", -33.17, -71.62, now, status="confirmado")
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
        esperado = haversine_km(-33.05, -71.55, -33.17, -71.62)
        assert 0 < esperado < 20  # el punto de prueba queda dentro del 2× radio
        assert by_id["fuego"]["distance_km"] == round(esperado, 2)
        assert by_id["fuego"]["distance_km"] == round(by_id["fuego"]["distance_km"], 2)


def test_days_limita_a_1_90_y_alcanza_incidentes_de_hasta_noventa_dias(make_client):
    with make_client() as client:
        db, headers, place_id = _setup(client)
        for valor in ("0", "91", "-5", "abc"):
            res = client.get(f"/api/places/{place_id}/history?days={valor}", headers=headers)
            assert res.status_code == 422, f"days={valor} debió rechazarse"
        now = datetime.now(timezone.utc)
        _incident(db, "dentro", -33.10, -71.55, _stamp(now - timedelta(days=89)))
        _incident(db, "fuera", -33.10, -71.55, _stamp(now - timedelta(days=91)))
        res = client.get(f"/api/places/{place_id}/history?days=30", headers=headers)
        assert res.json()["incidents"] == []
        res = client.get(f"/api/places/{place_id}/history?days=90", headers=headers)
        assert res.status_code == 200 and res.json()["days"] == 90
        assert {i["id"] for i in res.json()["incidents"]} == {"dentro"}

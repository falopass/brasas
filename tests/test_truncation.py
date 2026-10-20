"""FIX-17: /api/observations avisa cuando recorta al límite en vez de hacerlo en silencio."""
from __future__ import annotations

from datetime import datetime, timezone

import backend.routes.public as public


def _insert_observations(db, n: int) -> None:
    moment = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for i in range(n):
        db.execute("INSERT INTO observations(id, source, sensor, satellite, resolution_m, lat, lon, observed_at, "
                   "frp_mw, confidence, comuna_code, run_id, ingested_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL,?)",
                   (f"trunc-{i}", "goes", "ABI", "GOES-19", 2000, -33.05, -71.55, moment, 20.0, "alta", 13101, moment))


def test_observations_report_truncation(make_client, monkeypatch):
    monkeypatch.setattr(public, "OBSERVATIONS_LIMIT", 3)
    with make_client() as client:
        _insert_observations(client.app.state.services.db, 4)
        data = client.get("/api/observations").json()
    assert data["truncated"] is True and data["limit"] == 3
    assert data["count"] == 3 and len(data["points"]) == 3


def test_observations_without_truncation(make_client, monkeypatch):
    monkeypatch.setattr(public, "OBSERVATIONS_LIMIT", 3)
    with make_client() as client:
        _insert_observations(client.app.state.services.db, 2)
        data = client.get("/api/observations").json()
    assert data["truncated"] is False and data["limit"] == 3
    assert data["count"] == 2 and len(data["points"]) == 2


# DET-20: el contrato público de cada punto. Las columnas internas de `observations`
# (run_id, ingested_at, alerts_evaluated_at, confidence_raw, brightness_k) no se
# publican, y una columna nueva tampoco sale sin pasar por esta lista.
OBSERVATION_KEYS = {"id", "source", "sensor", "satellite", "resolution_m", "lat", "lon", "observed_at",
                    "frp_mw", "confidence", "comuna_code", "comuna", "region",
                    "incident_id", "incident_status", "incident_n", "incident_fixed"}


def test_observations_point_contract(make_client):
    with make_client() as client:
        _insert_observations(client.app.state.services.db, 1)
        points = client.get("/api/observations").json()["points"]
    assert len(points) == 1
    assert set(points[0]) == OBSERVATION_KEYS

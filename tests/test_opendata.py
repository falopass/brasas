"""Datos abiertos en GeoJSON: forma del contrato, filtros y que no se filtre nada de personas.

La API pública de solo lectura (plan 3.3) tiene que ser aburrida de probar: tres conjuntos, la misma
forma, parámetros validados y ningún dato que identifique a alguien.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone

from backend.routes import opendata

STAMP = "%Y-%m-%dT%H:%M:%SZ"


def ago(hours: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime(STAMP)


def seed_incident(db, ident: str, status: str = "posible", fixed: int = 0, hours: int = 1) -> None:
    moment = ago(hours)
    db.execute(
        "INSERT OR REPLACE INTO incidents(id, status, status_changed_at, first_seen_at, last_seen_at, lat, lon, "
        "min_lat, max_lat, min_lon, max_lon, n_obs, n_reliable, sensors, max_frp, comuna_code, fixed_source, "
        "official_ref, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (ident, status, moment, moment, moment, -33.05, -71.55, -33.06, -33.04, -71.56, -71.54,
         3, 2, "GOES19, VIIRS", 42.5, 5109, fixed, None, moment))


def seed_observation(db, ident: str, source: str = "VIIRS_NOAA20_NRT", hours: int = 1) -> None:
    db.execute(
        "INSERT OR REPLACE INTO observations(id, source, sensor, satellite, resolution_m, lat, lon, observed_at, "
        "frp_mw, brightness_k, confidence, confidence_raw, comuna_code, run_id, ingested_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (ident, source, "I4", "NOAA-20", 375, -33.05, -71.55, ago(hours), 12.0, 340.0, "nominal", "n",
         5109, None, ago(0)))


def test_index_describes_every_dataset(make_client):
    with make_client() as client:
        body = client.get("/api/opendata").json()
    assert [d["id"] for d in body["datasets"]] == ["incidents", "observations", "risk", "lightning", "smoke", "response"]
    assert "no es una fuente oficial" in body["not_official"]
    assert all(d["url"].startswith("/api/opendata/") and d["properties"] for d in body["datasets"])
    assert body["limits"]["max_features"] == 5000


def test_incidents_geojson_has_the_expected_shape(make_client):
    with make_client() as client:
        seed_incident(client.app.state.services.db, "inc-1")
        response = client.get("/api/opendata/incidents.geojson")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/geo+json")
        body = response.json()
        assert body["type"] == "FeatureCollection" and body["count"] == 1
        feature = body["features"][0]
        assert feature["type"] == "Feature" and feature["geometry"]["type"] == "Point"
        assert feature["geometry"]["coordinates"] == [-71.55, -33.05]
        props = feature["properties"]
        assert props["id"] == "inc-1" and props["status_label"] == "Posible incendio"
        assert props["sensors"] == ["GOES19", "VIIRS"] and props["comuna"] == "Viña del Mar"


def test_incidents_hide_fixed_sources_unless_asked(make_client):
    with make_client() as client:
        db = client.app.state.services.db
        seed_incident(db, "volcan", fixed=1)
        assert client.get("/api/opendata/incidents.geojson").json()["count"] == 0
        assert client.get("/api/opendata/incidents.geojson?include_fixed=true").json()["count"] == 1


def test_incidents_only_return_open_states_and_the_time_window(make_client):
    with make_client() as client:
        db = client.app.state.services.db
        seed_incident(db, "viejo", hours=200)
        seed_incident(db, "extinguido", status="extinguido")
        assert client.get("/api/opendata/incidents.geojson").json()["count"] == 0
        assert client.get("/api/opendata/incidents.geojson?hours=336").json()["count"] == 1


def test_observations_geojson_filters_by_source(make_client):
    with make_client() as client:
        db = client.app.state.services.db
        seed_observation(db, "obs-viirs")
        seed_observation(db, "obs-goes", source="GOES19_FDCF")
        assert client.get("/api/opendata/observations.geojson").json()["count"] == 2
        only_goes = client.get("/api/opendata/observations.geojson?source=GOES19_FDCF").json()
        assert only_goes["count"] == 1 and only_goes["features"][0]["properties"]["id"] == "obs-goes"


def test_risk_geojson_uses_the_comuna_centroid(make_client):
    with make_client() as client:
        db = client.app.state.services.db
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        db.execute("INSERT OR REPLACE INTO risk_daily(comuna_code, date, level, score, hours_3of3, hours_2of3, "
                   "tmax, rhmin, windmax, gustmax, level_combined, computed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                   (5109, today, "alto", 80, 2, 4, 33.0, 22.0, 35.0, 55.0, "extremo", ago(1)))
        body = client.get(f"/api/opendata/risk.geojson?day={today}").json()
        assert body["count"] == 1 and body["date"] == today
        props = body["features"][0]["properties"]
        assert props["comuna"] == "Viña del Mar" and props["level"] == "alto" and props["level_combined"] == "extremo"
        assert "peligro de propagación" in body["method"]


def test_parameters_are_validated(make_client):
    with make_client() as client:
        assert client.get("/api/opendata/incidents.geojson?hours=0").status_code == 422
        assert client.get("/api/opendata/incidents.geojson?hours=9999").status_code == 422
        assert client.get("/api/opendata/observations.geojson?hours=0").status_code == 422
        assert client.get("/api/opendata/risk.geojson?day=mañana").status_code == 422
        assert client.get("/api/opendata/lightning.geojson?hours=0").status_code == 422
        assert client.get("/api/opendata/lightning.geojson?hours=7").status_code == 422


def test_the_public_datasets_carry_nothing_about_people(make_client):
    """Ni lugares guardados, ni dispositivos, ni reportes sin verificar."""
    with make_client() as client:
        db = client.app.state.services.db
        seed_incident(db, "inc-1")
        seed_observation(db, "obs-1")
        text = json.dumps([client.get("/api/opendata/incidents.geojson").json(),
                           client.get("/api/opendata/observations.geojson").json()])
    for forbidden in ("subscriber", "place_id", "token", "push_endpoint", "description", "photo"):
        assert forbidden not in text.lower()


def test_datasets_report_when_they_truncated(make_client, monkeypatch):
    """FIX-39: con el tope en 2 y 3 elementos, `truncated` avisa y `count` cuenta lo entregado."""
    monkeypatch.setattr(opendata, "MAX_FEATURES", 2)
    with make_client() as client:
        db = client.app.state.services.db
        for i in range(3):
            seed_incident(db, f"inc-{i}")
            seed_observation(db, f"obs-{i}")
        for url in ("/api/opendata/incidents.geojson", "/api/opendata/observations.geojson"):
            body = client.get(url).json()
            assert body["truncated"] is True and body["limit"] == 2
            assert body["count"] == 2 and len(body["features"]) == 2


def test_datasets_dont_report_truncation_under_the_limit(make_client, monkeypatch):
    monkeypatch.setattr(opendata, "MAX_FEATURES", 2)
    with make_client() as client:
        seed_observation(client.app.state.services.db, "obs-1")
        body = client.get("/api/opendata/observations.geojson").json()
    assert body["truncated"] is False and body["count"] == 1


def test_lightning_reports_truncation_from_memory(make_client, monkeypatch):
    """El recorte en memoria (rayos) también se avisa: `count` no puede quedar bajo el total sin nota."""
    monkeypatch.setattr(opendata, "MAX_FEATURES", 2)
    flashes = [{"id": f"f-{i}", "observed_at": ago(1), "lat": -33.05, "lon": -71.55,
                "energy_j": 1.0, "area_km2": 4.0} for i in range(3)]
    monkeypatch.setattr(opendata, "_LIGHTNING_CACHE", {1: (time.monotonic() + 60, flashes)})
    with make_client() as client:
        body = client.get("/api/opendata/lightning.geojson").json()
    assert body["truncated"] is True and body["count"] == 2 and len(body["features"]) == 2


def test_sensor_names_come_without_leading_spaces(make_client):
    """Los sensores se guardan separados por coma; ni este conjunto ni /api/incidents deben
    devolver « VIIRS» con espacio delante: es el mismo dato y tiene que leerse igual en los dos."""
    with make_client() as client:
        seed_incident(client.app.state.services.db, "inc-2")
        open_data = client.get("/api/opendata/incidents.geojson").json()["features"][0]["properties"]
        public_api = client.get("/api/incidents").json()["incidents"][0]
    assert open_data["sensors"] == ["GOES19", "VIIRS"]
    assert public_api["sensors"] == ["GOES19", "VIIRS"]

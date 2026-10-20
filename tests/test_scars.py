"""Cicatrices de la temporada (AGUA-01): unión por comuna de las huellas de detecciones.

La cicatriz se sirve como dato abierto en `/api/opendata/scars.geojson`: un polígono por
comuna con la huella unida de sus incidentes no descartados ni fijos.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

STAMP = "%Y-%m-%dT%H:%M:%SZ"


def ago(hours: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime(STAMP)


def seed_incident(db, ident: str, status: str = "posible", hours: float = 48, comuna: int = 5109) -> None:
    moment, first = ago(hours), ago(hours + 24)
    db.execute(
        "INSERT OR REPLACE INTO incidents(id, status, status_changed_at, first_seen_at, last_seen_at, lat, lon, "
        "min_lat, max_lat, min_lon, max_lon, n_obs, n_reliable, sensors, max_frp, comuna_code, fixed_source, "
        "official_ref, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            ident,
            status,
            moment,
            first,
            moment,
            -33.05,
            -71.55,
            -33.06,
            -33.04,
            -71.56,
            -71.54,
            1,
            1,
            "VIIRS",
            12.0,
            comuna,
            0,
            None,
            moment,
        ),
    )
    db.execute(
        "INSERT OR REPLACE INTO observations(id, source, sensor, satellite, resolution_m, lat, lon, observed_at, "
        "frp_mw, brightness_k, confidence, confidence_raw, comuna_code, run_id, ingested_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            f"{ident}-o1",
            "VIIRS_NOAA20_NRT",
            "VIIRS",
            "NOAA-20",
            375,
            -33.05,
            -71.55,
            moment,
            12.0,
            340.0,
            "nominal",
            "n",
            comuna,
            None,
            ago(0),
        ),
    )
    db.execute("INSERT OR REPLACE INTO incident_observations(observation_id, incident_id) VALUES (?,?)", (f"{ident}-o1", ident))


def test_scars_unites_two_incidents_of_the_same_comuna(make_client):
    with make_client() as client:
        db = client.app.state.services.db
        seed_incident(db, "inc-a")
        seed_incident(db, "inc-b")
        response = client.get("/api/opendata/scars.geojson")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/geo+json")
        body = response.json()
        assert body["type"] == "FeatureCollection" and body["count"] == 1
        feature = body["features"][0]
        assert feature["geometry"]["type"] in ("Polygon", "MultiPolygon")
        props = feature["properties"]
        assert props["comuna"] == "Viña del Mar" and props["comuna_code"] == 5109
        assert props["ha"] > 0 and props["n_incidentes"] == 2
        assert "no es perímetro oficial" in body["source"]


def test_scars_skips_discarded_incidents(make_client):
    with make_client() as client:
        db = client.app.state.services.db
        seed_incident(db, "descartado", status="descartado")
        assert client.get("/api/opendata/scars.geojson").json()["count"] == 0


def test_scars_respects_the_time_window(make_client):
    with make_client() as client:
        db = client.app.state.services.db
        seed_incident(db, "viejo", hours=24 * 200)
        assert client.get("/api/opendata/scars.geojson").json()["count"] == 0
        assert client.get("/api/opendata/scars.geojson?days=180").json()["count"] == 0
        assert client.get("/api/opendata/scars.geojson?days=0").status_code == 422
        assert client.get("/api/opendata/scars.geojson?days=181").status_code == 422


def test_scars_empty_without_incidents(make_client):
    with make_client() as client:
        body = client.get("/api/opendata/scars.geojson").json()
        assert body["type"] == "FeatureCollection"
        assert body["count"] == 0 and body["features"] == []


def test_index_lists_the_scars_dataset(make_client):
    with make_client() as client:
        body = client.get("/api/opendata").json()
        scars = next((d for d in body["datasets"] if d["id"] == "scars"), None)
        assert scars is not None and scars["url"] == "/api/opendata/scars.geojson"
        assert "scars" in body["limits"]

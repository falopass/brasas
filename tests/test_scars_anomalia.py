"""SCARS-02 — la cicatriz mide zona con calor, así que incluye anomalías.

Una anomalía es una detección suelta que no alcanzó el umbral de «posible». La regla
vigente (la más conservadora: no cambiar hectáreas ya publicadas) es que también cuenta
como cicatriz, porque la cicatriz no es superficie quemada con evidencia. Esta prueba fija
esa regla; si se aprueba separar `ha` y `ha_anomalia`, cámbiala junto con el contrato.
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


def test_la_cicatriz_incluye_una_anomalia_y_lo_declara(make_client):
    """SCARS-02: la anomalía cuenta como zona con calor; no se excluye de `ha`."""
    with make_client() as client:
        db = client.app.state.services.db
        seed_incident(db, "suelta", status="anomalia")
        body = client.get("/api/opendata/scars.geojson").json()
    assert body["count"] == 1
    props = body["features"][0]["properties"]
    assert props["n_incidentes"] == 1 and props["ha"] > 0
    assert body["incidents_examined"] == 1
    assert "anomalía" in body["method"]

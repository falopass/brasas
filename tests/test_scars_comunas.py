"""Cicatrices sin comuna (CICATRIES-01): `season_scars` cuenta los incidentes que quedaron
fuera por no tener comuna asignada y lo declara en `sin_comuna`.

Los incidentes sin comuna no entran a la geometría a propósito (la atribución por cercanía
está abierta en FUEGO-61), pero antes desaparecían sin dejar rastro y la capa subestimaba
el suelo quemado sin avisar.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.scars import MAX_INCIDENTS, season_scars

STAMP = "%Y-%m-%dT%H:%M:%SZ"


def ago(hours: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime(STAMP)


def seed_incident(
    db, ident: str, status: str = "posible", hours: float = 48, comuna: int | None = 5109, confidence: str = "nominal"
) -> None:
    """Un incidente con un píxel sembrado; `confidence` fuera de {alta, media, nominal} lo hace no confiable."""
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
            confidence,
            "n",
            comuna,
            None,
            ago(0),
        ),
    )
    db.execute("INSERT OR REPLACE INTO incident_observations(observation_id, incident_id) VALUES (?,?)", (f"{ident}-o1", ident))


def seed_incident_sin_pixeles(db, ident: str, hours: float = 48, comuna: int | None = None) -> None:
    """Solo la fila del incidente: con comuna en NULL queda fuera sin pedir sus observaciones."""
    moment, first = ago(hours), ago(hours + 24)
    db.execute(
        "INSERT OR REPLACE INTO incidents(id, status, status_changed_at, first_seen_at, last_seen_at, lat, lon, "
        "min_lat, max_lat, min_lon, max_lon, n_obs, n_reliable, sensors, max_frp, comuna_code, fixed_source, "
        "official_ref, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            ident,
            "posible",
            moment,
            first,
            moment,
            -33.05,
            -71.55,
            -33.06,
            -33.04,
            -71.56,
            -71.54,
            0,
            0,
            "VIIRS",
            0.0,
            comuna,
            0,
            None,
            moment,
        ),
    )


def test_dos_con_comuna_y_uno_sin_comuna_una_cicatriz_y_sin_comuna_1(make_client):
    with make_client() as client:
        db = client.app.state.services.db
        seed_incident(db, "inc-a")
        seed_incident(db, "inc-b")
        seed_incident(db, "inc-c", comuna=None)
        body = client.get("/api/opendata/scars.geojson").json()
    assert body["count"] == 1 and body["features"][0]["properties"]["n_incidentes"] == 2
    assert body["incidents_examined"] == 3
    assert body["sin_comuna"] == 1


def test_incidente_sin_pixeles_confiables_no_aparece_y_no_suma(make_client):
    with make_client() as client:
        db = client.app.state.services.db
        seed_incident(db, "sin-confianza", confidence="baja")
        result = season_scars(db, 90)
    assert result["features"] == []
    assert result["sin_comuna"] == 0  # tiene comuna: quedó fuera por píxeles, no por ubicación


def test_ventana_vacia_sin_comuna_es_cero(make_client):
    with make_client() as client:
        db = client.app.state.services.db
        result = season_scars(db, 90)
    assert result["features"] == []
    assert result["sin_comuna"] == 0


def test_truncamiento_sigue_funcionando_y_cuenta_los_sin_comuna(make_client):
    with make_client() as client:
        db = client.app.state.services.db
        for i in range(MAX_INCIDENTS + 1):
            seed_incident_sin_pixeles(db, f"extra-{i}", comuna=None)
        result = season_scars(db, 90)
    assert result["incidents_truncated"] is True
    assert result["incidents_examined"] == MAX_INCIDENTS
    assert result["sin_comuna"] == MAX_INCIDENTS


def test_la_respuesta_conserva_las_claves_que_lee_opendata(make_client):
    with make_client() as client:
        db = client.app.state.services.db
        seed_incident(db, "inc-a")
        result = season_scars(db, 90)
    for key in ("type", "features", "incidents_examined", "incidents_limit", "incidents_truncated", "sin_comuna"):
        assert key in result, key
    assert result["type"] == "FeatureCollection"
    assert isinstance(result["sin_comuna"], int)

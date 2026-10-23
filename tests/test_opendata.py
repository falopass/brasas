"""Datos abiertos en GeoJSON: forma del contrato, filtros y que no se filtre nada de personas.

La API pública de solo lectura (plan 3.3) tiene que ser aburrida de probar: tres conjuntos, la misma
forma, parámetros validados y ningún dato que identifique a alguien.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone

from backend.geo import territory
from backend.routes import opendata

STAMP = "%Y-%m-%dT%H:%M:%SZ"


def ago(hours: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime(STAMP)


def seed_incident(db, ident: str, status: str = "posible", fixed: int = 0, hours: int = 1, comuna_code: int | None = 5109) -> None:
    moment = ago(hours)
    db.execute(
        "INSERT OR REPLACE INTO incidents(id, status, status_changed_at, first_seen_at, last_seen_at, lat, lon, "
        "min_lat, max_lat, min_lon, max_lon, n_obs, n_reliable, sensors, max_frp, comuna_code, fixed_source, "
        "official_ref, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            ident,
            status,
            moment,
            moment,
            moment,
            -33.05,
            -71.55,
            -33.06,
            -33.04,
            -71.56,
            -71.54,
            3,
            2,
            "GOES19, VIIRS",
            42.5,
            comuna_code,
            fixed,
            None,
            moment,
        ),
    )


def seed_observation(
    db,
    ident: str,
    source: str = "VIIRS_NOAA20_NRT",
    hours: int = 1,
    lat: float = -33.05,
    lon: float = -71.55,
    comuna_code: int | None = 5109,
) -> None:
    db.execute(
        "INSERT OR REPLACE INTO observations(id, source, sensor, satellite, resolution_m, lat, lon, observed_at, "
        "frp_mw, brightness_k, confidence, confidence_raw, comuna_code, run_id, ingested_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (ident, source, "I4", "NOAA-20", 375, lat, lon, ago(hours), 12.0, 340.0, "nominal", "n", comuna_code, None, ago(0)),
    )


def seed_boton_rojo(db, date: str, code: int = 5109, hours: int = 6) -> None:
    db.execute(
        "INSERT OR REPLACE INTO boton_rojo(comuna_code, date, hours, area_ha, proportion, fetched_at) VALUES (?,?,?,?,?,?)",
        (code, date, hours, 1234.0, 0.42, ago(1)),
    )


def test_index_describes_every_dataset(make_client):
    with make_client() as client:
        body = client.get("/api/opendata").json()
    assert [d["id"] for d in body["datasets"]] == [
        "incidents",
        "observations",
        "risk",
        "lightning",
        "smoke",
        "scars",
        "response",
        "boton-rojo",
    ]
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


def test_observations_publish_only_chilean_points_unless_todo(make_client):
    """FUEGO-05: GOES también ve Argentina; por defecto el feed es solo Chile y lo avisa."""
    with make_client() as client:
        db = client.app.state.services.db
        seed_observation(db, "arg", lat=-31.35, lon=-69.42, comuna_code=None)  # San Juan, Argentina
        talca = territory().locate(-35.42, -71.65)
        seed_observation(db, "talca", lat=-35.42, lon=-71.65, comuna_code=talca.code if talca else 8101)
        body = client.get("/api/opendata/observations.geojson").json()
        assert body["count"] == 1 and body["outside_chile"] == 1
        assert "todo=1" in body["note"]
        assert body["features"][0]["properties"]["id"] == "talca"
        full = client.get("/api/opendata/observations.geojson?todo=1").json()
        assert full["count"] == 2 and full["outside_chile"] == 0


def test_incidents_without_a_chilean_comuna_stay_out_unless_todo(make_client):
    """Un incidente sin comuna no es un incendio de Chile: no se publica por defecto."""
    with make_client() as client:
        db = client.app.state.services.db
        seed_incident(db, "fuera", comuna_code=None)
        seed_incident(db, "dentro")
        body = client.get("/api/opendata/incidents.geojson").json()
        assert {f["properties"]["id"] for f in body["features"]} == {"dentro"}
        assert body["outside_chile"] == 1 and "todo=1" in body["note"]
        assert client.get("/api/opendata/incidents.geojson?todo=1").json()["count"] == 2


def test_observations_geojson_filters_by_source(make_client):
    with make_client() as client:
        db = client.app.state.services.db
        seed_observation(db, "obs-viirs")
        seed_observation(db, "obs-goes", source="GOES19_FDCF")
        assert client.get("/api/opendata/observations.geojson").json()["count"] == 2
        only_goes = client.get("/api/opendata/observations.geojson?source=GOES19_FDCF").json()
        assert only_goes["count"] == 1 and only_goes["features"][0]["properties"]["id"] == "obs-goes"


def test_observations_geojson_publishes_only_detections_in_chile(make_client):
    """FUEGO-13: el rectángulo de lectura del satélite también cubre países vecinos; el
    conjunto público es de Chile, así que una detección sin comuna nunca sale publicada."""
    with make_client() as client:
        db = client.app.state.services.db
        seed_observation(db, "obs-chile", lat=-33.4489, lon=-70.6693, comuna_code=13101)
        seed_observation(db, "obs-argentina", lat=-31.35488, lon=-69.42233, comuna_code=None)
        body = client.get("/api/opendata/observations.geojson?hours=24").json()
        assert body["count"] == 1 and len(body["features"]) == 1
        feature = body["features"][0]
        assert feature["properties"]["id"] == "obs-chile"
        assert feature["geometry"]["coordinates"] == [-70.6693, -33.4489]  # GeoJSON: [lon, lat]
        assert feature["properties"]["observed_at"].endswith("Z")
        assert all(f["properties"]["comuna"] for f in body["features"])


def test_index_declares_that_observations_covers_only_chile(make_client):
    """FUEGO-13: el índice tiene que advertir la restricción a Chile, para que quien baja
    el conjunto no lo lea como el barrido completo del satélite."""
    with make_client() as client:
        dataset = next(d for d in client.get("/api/opendata").json()["datasets"] if d["id"] == "observations")
    assert "comuna chilena" in dataset["note"] and "países vecinos" in dataset["note"]


def test_risk_geojson_uses_the_comuna_centroid(make_client):
    with make_client() as client:
        db = client.app.state.services.db
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        db.execute(
            "INSERT OR REPLACE INTO risk_daily(comuna_code, date, level, score, hours_3of3, hours_2of3, "
            "tmax, rhmin, windmax, gustmax, level_combined, computed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (5109, today, "alto", 80, 2, 4, 33.0, 22.0, 35.0, 55.0, "extremo", ago(1)),
        )
        body = client.get(f"/api/opendata/risk.geojson?day={today}").json()
        assert body["count"] == 1 and body["date"] == today
        props = body["features"][0]["properties"]
        assert props["comuna"] == "Viña del Mar" and props["level"] == "alto" and props["level_combined"] == "extremo"
        assert "peligro de propagación" in body["method"]


def test_boton_rojo_publishes_the_official_forecast(make_client):
    with make_client() as client:
        db = client.app.state.services.db
        seed_boton_rojo(db, "2026-10-20", hours=6)
        seed_boton_rojo(db, "2026-10-21", hours=3)
        response = client.get("/api/opendata/boton-rojo.json")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/json")
        body = response.json()
        assert body["type"] == "FeatureCollection" and body["count"] == 2
        assert body["source"] == "CONAF · Botón Rojo" and "no es una fuente oficial" in body["not_official"]
        feature = body["features"][0]
        assert feature["type"] == "Feature" and feature["geometry"]["type"] == "Point"
        props = feature["properties"]
        assert set(props) == {"comuna_code", "comuna", "region", "date", "hours", "area_ha", "proportion", "fetched_at"}
        assert props["comuna_code"] == 5109 and props["comuna"] == "Viña del Mar"
        assert props["date"] == "2026-10-20" and props["hours"] == 6


def test_boton_rojo_filters_by_day_and_keeps_the_most_recent_days(make_client):
    with make_client() as client:
        db = client.app.state.services.db
        for date in ("2026-10-19", "2026-10-20", "2026-10-21"):
            seed_boton_rojo(db, date)
        one = client.get("/api/opendata/boton-rojo.json?day=2026-10-20").json()
        assert one["count"] == 1 and one["date"] == "2026-10-20"
        two = client.get("/api/opendata/boton-rojo.json?days=2").json()
        assert two["count"] == 2
        assert {f["properties"]["date"] for f in two["features"]} == {"2026-10-20", "2026-10-21"}


def test_boton_rojo_empty_table_responds_200_with_zero(make_client):
    """Sin pronóstico descargado el conjunto responde vacío: nunca se inventa ni se rellena con otro día."""
    with make_client() as client:
        response = client.get("/api/opendata/boton-rojo.json")
        assert response.status_code == 200
        body = response.json()
        assert body["count"] == 0 and body["features"] == []


def test_parameters_are_validated(make_client):
    with make_client() as client:
        assert client.get("/api/opendata/incidents.geojson?hours=0").status_code == 422
        assert client.get("/api/opendata/incidents.geojson?hours=9999").status_code == 422
        assert client.get("/api/opendata/observations.geojson?hours=0").status_code == 422
        assert client.get("/api/opendata/risk.geojson?day=mañana").status_code == 422
        assert client.get("/api/opendata/lightning.geojson?hours=0").status_code == 422
        assert client.get("/api/opendata/lightning.geojson?hours=7").status_code == 422
        assert client.get("/api/opendata/boton-rojo.json?day=mañana").status_code == 422
        assert client.get("/api/opendata/boton-rojo.json?day=2026-02-30").status_code == 422
        assert client.get("/api/opendata/boton-rojo.json?days=0").status_code == 422
        assert client.get("/api/opendata/boton-rojo.json?days=15").status_code == 422


def test_the_public_datasets_carry_nothing_about_people(make_client):
    """Ni lugares guardados, ni dispositivos, ni reportes sin verificar."""
    with make_client() as client:
        db = client.app.state.services.db
        seed_incident(db, "inc-1")
        seed_observation(db, "obs-1")
        text = json.dumps([client.get("/api/opendata/incidents.geojson").json(), client.get("/api/opendata/observations.geojson").json()])
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


def seed_official_fire(
    db,
    ident: str,
    season: str = "2025-2026",
    detected: str | None = None,
    alerted: str | None = None,
    dispatched: str | None = None,
    comuna: str = "Quilpué",
    area_ha: float = 5.0,
) -> None:
    moment = ago(1)
    db.execute(
        "INSERT OR REPLACE INTO official_fires(id, name, status, status_raw, started_at, lat, lon, comuna, "
        "region, detected_at, alerted_at, dispatched_at, area_ha, season, first_fetched_at, fetched_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            ident,
            "(TEST) INCENDIO",
            "confirmado",
            "En combate",
            moment,
            -33.05,
            -71.42,
            comuna,
            "Valparaíso",
            detected,
            alerted,
            dispatched,
            area_ha,
            season,
            moment,
            moment,
        ),
    )


def test_response_json_contract(make_client):
    """El radar de respuesta oficial: un JSON (no GeoJSON) con medianas por temporada, caché y 200 vacío."""
    with make_client() as client:
        db = client.app.state.services.db
        detected = ago(3)
        alerted = ago(2)
        dispatched = ago(1)
        for i in range(3):
            seed_official_fire(db, f"fire-{i}", detected=detected, alerted=alerted, dispatched=dispatched)
        response = client.get("/api/opendata/response.json")
        assert response.status_code == 200
        assert "cache-control" in response.headers
        body = response.json()
        assert body["type"] == "response_times" and body["season"] == "2025-2026"
        assert body["count"] == 3 and body["limit"] and "truncated" in body
        for pair in ("detection_to_alert", "alert_to_dispatch", "detection_to_dispatch"):
            assert set(body["overall"][pair]) == {"median_min", "n", "same_minute", "same_hour", "over_hour", "min_usable_n"}
            assert body["overall"][pair]["n"] == 3
        assert body["comunas"] and body["buckets"] and body["excluded"] == 0
        assert client.get("/api/opendata/response.json?season=no-es-temporada").status_code == 422


def test_response_json_with_an_empty_table_is_a_200_with_zero(make_client):
    """Sin incendios con marcas publicadas el conjunto responde vacío: nunca 404 ni datos inventados."""
    with make_client() as client:
        response = client.get("/api/opendata/response.json")
        assert response.status_code == 200
        body = response.json()
        assert body["count"] == 0 and body["comunas"] == [] and body["buckets"] == []
        assert "note" in body


def test_smoke_geojson_contract(make_client, monkeypatch):
    """Polígonos de humo GOES-19: FeatureCollection con geometrías Polygon y `age_min` en minutos."""
    stamp = ago(1)
    polys = [
        {
            "observed_at": stamp,
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[-71.6, -33.1], [-71.5, -33.1], [-71.5, -33.0], [-71.6, -33.0], [-71.6, -33.1]]],
            },
            "cells": 4,
        }
    ]
    monkeypatch.setattr(opendata, "_SMOKE_CACHE", {1: (time.monotonic() + 60, polys)})
    with make_client() as client:
        response = client.get("/api/opendata/smoke.geojson")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/geo+json")
        body = response.json()
        assert body["type"] == "FeatureCollection"
        assert body["count"] == 1 and body["limit"] and body["truncated"] is False
        feature = body["features"][0]
        assert feature["type"] == "Feature" and feature["geometry"]["type"] == "Polygon"
        props = feature["properties"]
        assert props["observed_at"] == stamp and props["cells"] == 4
        assert isinstance(props["age_min"], int) and props["age_min"] >= 0  # la unidad va en el nombre
        assert client.get("/api/opendata/smoke.geojson?hours=0").status_code == 422
        assert client.get("/api/opendata/smoke.geojson?hours=7").status_code == 422


def test_index_and_routes_stay_in_sync(make_client):
    """Toda ruta GET del router aparece en el índice y todo lo listado existe: ni rutas invisibles
    ni conjuntos prometidos que no responden."""
    # `/api/opendata/catalog` es metadato (el catálogo de DAT-08), no un conjunto:
    # el índice lista conjuntos y no debe incluirla.
    route_paths = {
        route.path
        for route in opendata.router.routes
        if getattr(route, "methods", None) and "GET" in route.methods and route.path.rstrip("/") != "/api/opendata"
        and route.path != "/api/opendata/catalog"
    }
    with make_client() as client:
        listed = {d["url"] for d in client.get("/api/opendata").json()["datasets"]}
    assert listed == route_paths


def test_index_fields_dict_describe_cada_propiedad(make_client):
    """DAT-11: cada conjunto declara `fields` y todo nombre de `properties` está explicado."""
    with make_client() as client:
        datasets = client.get("/api/opendata").json()["datasets"]
    assert datasets
    for d in datasets:
        campos = d.get("fields") or []
        assert campos, f"{d['id']} sin fields"
        nombres = {f["name"] for f in campos}
        for prop in d["properties"]:
            assert prop in nombres, f"{d['id']}.{prop} sin descripción"
        for f in campos:
            assert f["description"] and f["description"].strip() != f["name"], f"{d['id']}.{f['name']}"
        assert all(isinstance(p, str) for p in d["properties"])  # compatibilidad


def test_index_fields_unidades_y_nulos(make_client):
    """frp_mw declara MW y `comuna` explica el null (mar o fuera de Chile)."""
    with make_client() as client:
        datasets = {d["id"]: d for d in client.get("/api/opendata").json()["datasets"]}
    obs = {f["name"]: f for f in datasets["observations"]["fields"]}
    assert obs["frp_mw"]["unit"] == "MW"
    assert "null" in obs["comuna"]["description"]


def test_observations_en_chile_y_meta(make_client):
    """DAT-10: cada feature declara en_chile y la colección explica el recorte."""
    with make_client() as client:
        db = client.app.state.services.db
        seed_observation(db, "arg", lat=-31.35, lon=-69.42, comuna_code=None)
        talca = territory().locate(-35.42, -71.65)
        seed_observation(db, "talca", lat=-35.42, lon=-71.65, comuna_code=talca.code if talca else 8101)
        body = client.get("/api/opendata/observations.geojson").json()
        assert body["meta"]["fuera_de_chile"] == 1 and body["meta"]["total"] == 2
        assert "recorte" in body["meta"] and "explicacion" in body["meta"]
        assert body["features"][0]["properties"]["en_chile"] is True
        full = client.get("/api/opendata/observations.geojson?todo=1").json()
        estados = {f["properties"]["id"]: f["properties"]["en_chile"] for f in full["features"]}
        assert estados == {"talca": True, "arg": False}


def test_index_menciona_los_puntos_fuera(make_client):
    with make_client() as client:
        obs = next(d for d in client.get("/api/opendata").json()["datasets"] if d["id"] == "observations")
    assert "fuera" in obs["note"]

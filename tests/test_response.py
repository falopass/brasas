"""Radar de respuesta oficial: medianas de detección → aviso → despacho publicadas por CONAF.

Las funciones puras viven en `backend/response.py` y el conjunto abierto en
`GET /api/opendata/response.json`. Se prueban los dos: el cálculo sobre filas y el contrato
del endpoint (temporada por defecto, temporada inexistente y la nota cuando no hay datos).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from backend import response

STAMP = "%Y-%m-%dT%H:%M:%SZ"
BASE = datetime(2026, 1, 10, 12, 0)


def iso(minutes_after: float) -> str:
    return (BASE + timedelta(minutes=minutes_after)).strftime(STAMP)


def row(detected=None, alerted=None, dispatched=None, comuna="Quilpué", area_ha=5.0):
    return {"detected_at": detected, "alerted_at": alerted, "dispatched_at": dispatched, "comuna": comuna, "area_ha": area_ha}


def seed_fire(db, ident, detected=None, alerted=None, dispatched=None, comuna="Quilpué", area_ha=5.0, season="2025-2026"):
    db.execute(
        "INSERT OR REPLACE INTO official_fires(id, name, status, status_raw, started_at, lat, lon, comuna, region, "
        "detected_at, alerted_at, dispatched_at, area_ha, season, first_fetched_at, fetched_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            ident,
            "(TEST) INCENDIO",
            "confirmado",
            "En combate",
            iso(-60),
            -33.05,
            -71.42,
            comuna,
            "Valparaíso",
            detected,
            alerted,
            dispatched,
            area_ha,
            season,
            iso(500),
            iso(500),
        ),
    )


def test_minutes_rejects_marks_that_cannot_be_right():
    assert response.minutes(iso(0), iso(15)) == 15
    assert response.minutes(None, iso(15)) is None  # marca faltante
    assert response.minutes(iso(0), "no es una fecha") is None  # marca ilegible
    assert response.minutes(iso(15), iso(0)) is None  # negativo: relojes desfasados
    assert response.minutes(iso(0), iso(8 * 24 * 60)) is None  # más de una semana
    assert response.minutes(iso(0), iso(7 * 24 * 60)) == 7 * 24 * 60


def test_median_is_exact_with_odd_and_even_counts():
    odd = response.aggregate([row(detected=iso(0), alerted=iso(m)) for m in (10, 30, 20)])
    assert odd["overall"]["detection_to_alert"]["median_min"] == 20.0
    assert odd["overall"]["detection_to_alert"]["n"] == 3
    even = response.aggregate([row(detected=iso(0), alerted=iso(m)) for m in (10, 20, 30, 41)])
    assert even["overall"]["detection_to_alert"]["median_min"] == 25.0
    assert even["overall"]["detection_to_alert"]["n"] == 4


def test_same_minute_pairs_are_flagged_so_they_are_not_read_as_a_delay():
    # Pares de 0–1 min: las dos marcas cayeron en el mismo minuto del archivo, y la página
    # las rotula «el mismo minuto» en vez de «1 min» (RESP-01). El backend entrega el conteo.
    rows = [row(detected=iso(0), alerted=iso(m)) for m in (0, 0.5, 1, 0.2, 0.9)]
    stat = response.aggregate(rows)["overall"]["detection_to_alert"]
    assert stat["median_min"] <= 1
    assert stat["same_minute"] == stat["n"] == 5
    assert stat["same_hour"] == stat["over_hour"] == 0


def test_the_minute_distribution_sums_n_for_every_pair():
    rows = [
        row(detected=iso(0), alerted=iso(0.5), dispatched=iso(90)),
        row(detected=iso(0), alerted=iso(45), dispatched=iso(200)),
        row(detected=iso(0), alerted=iso(30)),
    ]  # sin despacho: solo pares con aviso
    overall = response.aggregate(rows)["overall"]
    for key, _, _ in response.PAIRS:
        stat = overall[key]
        assert stat["same_minute"] + stat["same_hour"] + stat["over_hour"] == stat["n"]
    d2a = overall["detection_to_alert"]
    assert (d2a["same_minute"], d2a["same_hour"], d2a["over_hour"], d2a["n"]) == (1, 2, 0, 3)
    assert overall["detection_to_dispatch"]["over_hour"] == 2


def test_median_min_keeps_its_name_and_value_alongside_the_new_fields():
    rows = [row(detected=iso(0), alerted=iso(10 + i * 10)) for i in range(5)]
    stat = response.aggregate(rows)["overall"]["detection_to_alert"]
    assert stat["median_min"] == 30.0 and stat["n"] == 5
    assert stat["min_usable_n"] == response.MIN_USABLE_N


def test_a_bucket_with_too_few_pairs_is_marked_below_min_usable_n():
    rows = [row(detected=iso(0), alerted=iso(10), area_ha=50.0), row(detected=iso(0), alerted=iso(70), area_ha=50.0)]
    bucket = response.aggregate(rows)["buckets"][0]
    assert bucket["bucket"] == "10-100" and bucket["n_fires"] == 2
    stat = bucket["detection_to_alert"]
    assert stat["n"] == 2 and stat["n"] < stat["min_usable_n"]
    # La mediana se sigue entregando: el rótulo «pocos casos» es decisión de la página.
    assert stat["median_min"] == 40.0


def test_pairs_with_impossible_marks_are_dropped_one_by_one():
    rows = [
        row(detected=iso(0), alerted=iso(10), dispatched=iso(40)),  # válido
        row(detected=iso(0), alerted=iso(-5), dispatched=iso(20)),  # d→a negativo
        row(detected=iso(0), alerted=iso(10)),  # sin despacho
        row(detected=iso(0), alerted=iso(10), dispatched=iso(8 * 24 * 60)),  # despacho > 7 días
        row(detected=iso(0)),
    ]  # solo detección
    report = response.aggregate(rows)
    overall = report["overall"]
    assert overall["detection_to_alert"]["n"] == 3
    assert overall["alert_to_dispatch"]["n"] == 2
    assert overall["detection_to_dispatch"]["n"] == 2
    assert report["excluded"] == 1  # el de solo detección no aporta ningún par


def test_surface_buckets_and_fires_without_area():
    rows = [
        row(detected=iso(0), alerted=iso(10), area_ha=0.5),  # <1 ha
        row(detected=iso(0), alerted=iso(20), area_ha=1.0),  # 1-10 (borde bajo)
        row(detected=iso(0), alerted=iso(30), area_ha=100.0),  # 10-100 (borde alto)
        row(detected=iso(0), alerted=iso(40), area_ha=800.0),  # >100
        row(detected=iso(0), alerted=iso(50), area_ha=None),
    ]  # sin dato: fuera de los tramos
    buckets = {b["bucket"]: b for b in response.aggregate(rows)["buckets"]}
    assert buckets["<1 ha"]["detection_to_alert"]["median_min"] == 10.0
    assert buckets["1-10"]["detection_to_alert"]["median_min"] == 20.0
    assert buckets["10-100"]["detection_to_alert"]["median_min"] == 30.0
    assert buckets[">100"]["detection_to_alert"]["median_min"] == 40.0
    assert all(b["n_fires"] == 1 for b in buckets.values())


def test_a_comuna_needs_three_fires_with_data_to_appear():
    rows = [
        row(detected=iso(0), alerted=iso(10), comuna="Pica"),
        row(detected=iso(0), alerted=iso(20), comuna="Pica"),  # solo 2
        *[row(detected=iso(0), alerted=iso(10 + i * 10), comuna="Quilpué") for i in range(3)],
        row(detected=iso(0), comuna="Quilpué"),
    ]  # sin marcas: no cuenta para el mínimo
    comunas = {c["comuna"]: c for c in response.aggregate(rows)["comunas"]}
    assert "Pica" not in comunas
    assert comunas["Quilpué"]["n"] == 3
    assert comunas["Quilpué"]["detection_to_alert"]["median_min"] == 20.0


def test_response_endpoint_reports_the_latest_or_asked_season(make_client):
    """La forma general del conjunto vacío y el índice ya los cubre test_opendata.py;
    aquí queda la temporada pedida y su mediana."""
    with make_client() as client:
        db = client.app.state.services.db
        for i in range(3):
            seed_fire(db, f"f-{i}", detected=iso(0), alerted=iso(10 + i * 10), dispatched=iso(40 + i * 10))
        seed_fire(db, "vieja", detected=iso(0), alerted=iso(90), season="2024-2025")
        res = client.get("/api/opendata/response.json")
        assert res.status_code == 200
        assert res.headers["cache-control"] == "public, max-age=600"
        body = res.json()
        assert body["season"] == "2025-2026" and body["count"] == 3
        d2a = body["overall"]["detection_to_alert"]
        assert d2a["median_min"] == 20.0 and d2a["n"] == 3 and d2a["same_hour"] == 3
        assert body["comunas"][0]["comuna"] == "Quilpué" and body["comunas"][0]["n"] == 3
        asked = client.get("/api/opendata/response.json?season=2024-2025").json()
        assert asked["count"] == 1 and asked["overall"]["detection_to_alert"]["median_min"] == 90.0


def test_response_endpoint_exposes_the_minute_distribution(make_client):
    with make_client() as client:
        db = client.app.state.services.db
        seed_fire(db, "f-1", detected=iso(0), alerted=iso(0.5), dispatched=iso(90))
        body = client.get("/api/opendata/response.json").json()
        stat = body["overall"]["detection_to_alert"]
        assert stat["median_min"] == 0.5 and stat["same_minute"] == 1 and stat["n"] == 1
        assert stat["min_usable_n"] == response.MIN_USABLE_N


def test_response_endpoint_with_an_unknown_season_is_a_200_with_empty_lists(make_client):
    with make_client() as client:
        response_ = client.get("/api/opendata/response.json?season=1999-2000")
        assert response_.status_code == 200
        assert response_.headers["cache-control"] == "public, max-age=600"
        body = response_.json()
        assert body["count"] == 0 and body["comunas"] == [] and body["buckets"] == []
        assert "suficientes incendios" in body["note"]
        index = client.get("/api/opendata").json()
        assert "response" in [d["id"] for d in index["datasets"]]


def test_response_without_any_fire_row_is_a_200_with_a_note(make_client):
    with make_client() as client:
        body = client.get("/api/opendata/response.json").json()
        assert body["count"] == 0 and body["season"] is None and "note" in body

"""«La semana de tus lugares»: siete días de calor confiable alrededor de cada lugar guardado.

`GET /api/places/{id}/summary` gana un bloque aditivo `week` con los siete días del calendario de
Chile, el total de detecciones confiables a menos de 2× el radio, la más cercana y cuándo fue.
La ventana de 48 h de `nearby` no cambia: otras vistas y `/api/shared/{token}` dependen de ella.

Unidades: `nearest_km` va en kilómetros con dos decimales, igual que `nearby[].distance_km`.
Coordenadas: el lugar y las detecciones usan (lat, lon) en EPSG:4326; una detección con los ejes
invertidos queda a miles de kilómetros y no cuenta. Zona horaria: los días se cortan con la fecha
de `America/Santiago`, no con la de UTC ni con un offset fijo. Frescura: con la ingesta más vieja
que 48 h, `enough_data` es False y el resumen sigue respondiendo 200.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

CHILE_TZ = ZoneInfo("America/Santiago")
STAMP = "%Y-%m-%dT%H:%M:%SZ"
LAT, LON = -33.40, -70.70  # Santiago: 1° de longitud ≈ 92,9 km


def _east_deg(km: float) -> float:
    """Grados de longitud al este del lugar para una distancia en km a esta latitud."""
    return km / (111.32 * math.cos(math.radians(LAT)))


def _place(client, radius_km: float = 10) -> tuple[dict, str]:
    token = client.post("/api/subscribers").json()["token"]
    headers = {"X-Brasa-Token": token}
    place = client.post("/api/places", json={"name": "Casa", "lat": LAT, "lon": LON, "radius_km": radius_km}, headers=headers).json()
    return headers, place["id"]


def _obs(client, ident: str, lat: float, lon: float, when: datetime, confidence: str = "alta") -> None:
    moment = when.astimezone(timezone.utc).strftime(STAMP)
    client.app.state.services.db.execute(
        "INSERT INTO observations(id, source, sensor, satellite, resolution_m, lat, lon, observed_at, "
        "frp_mw, confidence, comuna_code, run_id, ingested_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL,?)",
        (ident, "firms", "VIIRS", "NOAA-21", 375, lat, lon, moment, 12.0, confidence, None, moment),
    )


def _fixed_obs(client, ident: str, lat: float, lon: float, when: datetime) -> None:
    """Una detección dentro de un incidente marcado como fuente fija (antorcha, industria)."""
    _obs(client, ident, lat, lon, when)
    moment = when.astimezone(timezone.utc).strftime(STAMP)
    db = client.app.state.services.db
    db.execute(
        "INSERT INTO incidents(id, status, status_changed_at, first_seen_at, last_seen_at, lat, lon, min_lat, "
        "max_lat, min_lon, max_lon, n_obs, n_reliable, sensors, comuna_code, fixed_source, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (f"inc-{ident}", "anomalia", moment, moment, moment, lat, lon, lat, lat, lon, lon, 1, 1, "VIIRS", None, 1, moment),
    )
    db.execute("INSERT INTO incident_observations(observation_id, incident_id) VALUES (?, ?)", (ident, f"inc-{ident}"))


def _fresh_ingest(client, hours_ago: float = 0.1) -> None:
    client.app.state.services.db.kv_set("last_ingest_at", (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).strftime(STAMP))


def _chile_noon(days_ago: int) -> datetime:
    """Mediodía de un día del calendario de Chile: siempre en el pasado y sin cruces de medianoche."""
    day = datetime.now(CHILE_TZ).date() - timedelta(days=days_ago)
    return datetime(day.year, day.month, day.day, 12, 0, tzinfo=CHILE_TZ)


def _week(client, headers: dict, place_id: str) -> dict:
    return client.get(f"/api/places/{place_id}/summary", headers=headers).json()["week"]


def test_week_tres_dias_con_calor_y_el_mas_cercano(make_client):
    now = datetime.now(timezone.utc)
    with make_client() as client:
        _fresh_ingest(client)
        headers, place_id = _place(client)
        # 4, 6 y 9 km al este, en tres días distintos del calendario de Chile.
        _obs(client, "cerca-4", LAT, LON + _east_deg(4), now)
        _obs(client, "cerca-6", LAT, LON + _east_deg(6), _chile_noon(1))
        _obs(client, "cerca-9", LAT, LON + _east_deg(9), _chile_noon(2))
        week = _week(client, headers, place_id)
    assert week["n"] == 3
    assert len(week["days"]) == 7
    assert [d["n"] for d in week["days"]] == [0, 0, 0, 0, 1, 1, 1]  # del más viejo al de hoy
    assert week["days"][-1]["date"] == datetime.now(CHILE_TZ).date().isoformat()
    assert week["nearest_km"] == 4.0  # km con dos decimales: no son 4 m ni 4.000 m
    assert week["nearest_at"] == now.strftime(STAMP)  # la detección de 4 km, no la de 6 ni la de 9
    assert week["enough_data"] is True
    assert week["data_as_of"] and week["data_as_of"].endswith("Z")


def test_week_una_deteccion_fuera_del_doble_del_radio_no_cuenta(make_client):
    with make_client() as client:
        _fresh_ingest(client)
        headers, place_id = _place(client)
        # 18 km al norte y 18 km al este: ~25,5 km. Dentro de la caja de precarga, fuera de 2× el radio.
        _obs(client, "lejos", LAT + 18 / 110.57, LON + _east_deg(18), datetime.now(timezone.utc))
        week = _week(client, headers, place_id)
    assert week["n"] == 0
    assert week["nearest_km"] is None and week["nearest_at"] is None


def test_week_una_fuente_fija_no_cuenta(make_client):
    with make_client() as client:
        _fresh_ingest(client)
        headers, place_id = _place(client)
        _fixed_obs(client, "antorcha", LAT, LON + _east_deg(4), datetime.now(timezone.utc))
        week = _week(client, headers, place_id)
    assert week["n"] == 0 and week["nearest_km"] is None


def test_week_con_datos_de_mas_de_48_horas_no_afirma_nada(make_client):
    with make_client() as client:
        _fresh_ingest(client, hours_ago=60)
        headers, place_id = _place(client)
        res = client.get(f"/api/places/{place_id}/summary", headers=headers)
    assert res.status_code == 200
    assert res.json()["week"]["enough_data"] is False


def test_week_corta_los_dias_por_la_fecha_de_chile(make_client):
    """Las 23:30 en Chile ya son las 02:30 del día siguiente en UTC: cuenta el día chileno."""
    with make_client() as client:
        _fresh_ingest(client)
        headers, place_id = _place(client)
        day = datetime.now(CHILE_TZ).date() - timedelta(days=2)
        moment = datetime(day.year, day.month, day.day, 23, 30, tzinfo=CHILE_TZ)
        assert moment.astimezone(timezone.utc).date() == day + timedelta(days=1)  # el caso que se prueba
        _obs(client, "nocturna", LAT, LON, moment)
        week = _week(client, headers, place_id)
    by_date = {d["date"]: d["n"] for d in week["days"]}
    assert by_date[day.isoformat()] == 1
    assert by_date[(day + timedelta(days=1)).isoformat()] == 0


def test_week_no_confunde_latitud_con_longitud(make_client):
    with make_client() as client:
        _fresh_ingest(client)
        headers, place_id = _place(client)
        _obs(client, "invertida", LON, LAT, datetime.now(timezone.utc))  # el mismo punto con los ejes cambiados
        week = _week(client, headers, place_id)
    assert week["n"] == 0


def test_week_una_marca_ilegible_no_tumba_el_resumen(make_client):
    with make_client() as client:
        _fresh_ingest(client)
        headers, place_id = _place(client)
        _obs(client, "rota", LAT, LON, datetime.now(timezone.utc))
        client.app.state.services.db.execute("UPDATE observations SET observed_at = 'sin-fecha' WHERE id = 'rota'")
        res = client.get(f"/api/places/{place_id}/summary", headers=headers)
    assert res.status_code == 200
    assert res.json()["week"]["n"] == 0

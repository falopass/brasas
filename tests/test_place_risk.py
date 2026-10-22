"""RISK-05 y DEBT-10: el 30-30-30 del lugar y lo que se comparte entre lugares.

`GET /api/places/{id}/summary` entrega `risk_point` usando el pronóstico de Open-Meteo
de la celda del lugar (lat/lon a un decimal): lugares de la misma celda comparten el
cálculo y un fallo del proveedor deja `risk_point` en null sin romper el resumen.
Las consultas que no dependen del lugar (`official_fires`, `dmc_alerts`) se hacen una
vez por pasada de «Mi zona», no una por lugar.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from backend import risk
from backend.db import Database
from backend.geo import territory
from tests.conftest import json_response

PUNTOS = [(-33.02, -71.55), (-33.025, -71.555), (-33.015, -71.545)]


def _hourly(now: datetime, hours: int = 60, t: float = 33.0, rh: float = 20.0, wind: float = 35.0) -> dict:
    """Pronóstico UTC que cubre completo el día de Chile en curso (~26 h antes y ~34 después)."""
    t0 = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=26)
    return {
        "time": [(t0 + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M") for i in range(hours)],
        "temperature_2m": [t] * hours,
        "relative_humidity_2m": [rh] * hours,
        "wind_speed_10m": [wind] * hours,
        "wind_gusts_10m": [wind + 10] * hours,
        "wind_direction_10m": [240] * hours,
    }


def _open_meteo(web, hourly: dict | None = None, fail_hourly: bool = False) -> None:
    """Open-Meteo simulado: `current` (el viento) siempre responde; `hourly` según lo pedido."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("hourly"):
            if fail_hourly:
                return httpx.Response(503, text="sin pronóstico")
            lats = request.url.params["latitude"].split(",")
            return json_response([{"hourly": hourly} for _ in lats])
        return json_response(
            {"current": {"wind_speed_10m": 12.0, "wind_direction_10m": 200.0, "time": "2027-01-15T15:00"}, "current_units": {}}
        )

    web.add(lambda r: "open-meteo" in r.url.host, handler)


def _forecast_calls(web) -> int:
    """Solo las peticiones de pronóstico horario, no las de `current` que hace `wind_at`."""
    return sum(1 for r in web.requests if "open-meteo" in r.url.host and r.url.params.get("hourly"))


def _setup(client, *points):
    """Un dispositivo con un lugar por cada (lat, lon); devuelve (headers, [place_id])."""
    token = client.post("/api/subscribers").json()["token"]
    headers = {"X-Brasa-Token": token}
    ids = [
        client.post("/api/places", json={"name": f"Lugar {i}", "lat": lat, "lon": lon, "radius_km": 10}, headers=headers).json()["id"]
        for i, (lat, lon) in enumerate(points)
    ]
    return headers, ids


def _contador(monkeypatch) -> dict[str, int]:
    cuenta = {"official_fires": 0, "dmc_alerts": 0}
    original = Database.query

    def contada(self, sql, params=()):
        for tabla in cuenta:
            if f"FROM {tabla}" in sql:
                cuenta[tabla] += 1
        return original(self, sql, params)

    monkeypatch.setattr(Database, "query", contada)
    return cuenta


def _comuna(db, place_id: str) -> int:
    return db.one("SELECT comuna_code FROM places WHERE id = ?", (place_id,))["comuna_code"]


def _incendio(db, fid: str, lat: float, lon: float) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    db.execute(
        "INSERT INTO official_fires(id, name, status, status_raw, started_at, lat, lon, first_fetched_at, fetched_at) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (fid, f"Incendio {fid}", "confirmado", "En combate", now, lat, lon, now, now),
    )


def _aviso_dmc(db, comunas: list[int]) -> None:
    """Una fila de `dmc_alerts` vigente, como la deja `ingest_dmc` (misma forma que test_alert_dmc)."""
    now = datetime.now(timezone.utc)
    db.execute(
        "INSERT INTO dmc_alerts(id, kind, event, headline, severity, urgency, onset, expires, web, areas, comunas, fetched_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "urn:oid:test:deb10",
            "viento",
            "Viento Normal a Moderado",
            "Viento Normal a Moderado en litoral de la región de Valparaíso",
            "Moderate",
            "Expected",
            (now - timedelta(hours=1)).isoformat(),
            (now + timedelta(hours=6)).isoformat(),
            "https://archivos.meteochile.gob.cl/portaldmc/AAA/doc/evento.html",
            "[]",
            json.dumps(comunas),
            now.isoformat(),
        ),
    )


@pytest.mark.parametrize(
    "points,reps,llamadas",
    [
        (((-33.05, -71.55),), 2, 1),  # dos llamadas al resumen = una sola petición
        (((-33.02, -71.52), (-33.04, -71.53)), 1, 1),  # misma celda (-33.0, -71.5): se comparte
        (((-33.02, -71.52), (-33.12, -71.52)), 1, 2),  # celdas distintas: cada una pide la suya
    ],
)
def test_la_cache_por_celda_agrupa_los_lugares(make_client, web, points, reps, llamadas):
    _open_meteo(web, hourly=_hourly(datetime.now(timezone.utc)))
    with make_client() as client:
        headers, ids = _setup(client, *points)
        cuerpos = [client.get(f"/api/places/{pid}/summary", headers=headers).json() for pid in ids for _ in range(reps)]
    assert _forecast_calls(web) == llamadas
    for body in cuerpos:
        assert body["risk_point"]["level"] == "extremo"
        assert body["risk_point"]["computed_at"]
        assert "calor 33" in body["risk_point"]["reasons"][0]
    if len(points) == 2 and llamadas == 1:
        assert cuerpos[0]["risk_point"] == cuerpos[1]["risk_point"]


def test_un_fallo_del_proveedor_deja_risk_point_null(make_client, web):
    _open_meteo(web, fail_hourly=True)
    with make_client() as client:
        headers, (place_id,) = _setup(client, (-33.05, -71.55))
        res = client.get(f"/api/places/{place_id}/summary", headers=headers)
        assert res.status_code == 200
        body = res.json()
        assert body["risk_point"] is None and body["status"]  # el resumen sigue igual que antes
        # El fallo se recuerda un rato (caché negativa): no se bombardea al proveedor.
        client.get(f"/api/places/{place_id}/summary", headers=headers)
        assert _forecast_calls(web) == 1


def test_un_punto_en_el_centro_de_la_comuna_da_el_nivel_de_evaluate(make_client, web):
    hourly = _hourly(datetime.now(timezone.utc))
    _open_meteo(web, hourly=hourly)
    with make_client() as client:
        comuna = territory().by_code[5109]  # Viña del Mar; center es (lon, lat)
        headers, (place_id,) = _setup(client, (comuna.center[1], comuna.center[0]))
        body = client.get(f"/api/places/{place_id}/summary", headers=headers).json()
    today = datetime.now(risk.CHILE_TZ).date().isoformat()
    expected = next(d["level"] for d in risk.evaluate(hourly)["days"] if d["date"] == today)
    assert body["risk_point"]["level"] == expected == risk.point_today(hourly)["level"]


def test_la_frase_nombra_lo_que_pasa_los_umbrales():
    point = risk.point_today(_hourly(datetime.now(timezone.utc), t=33.0, rh=20.0, wind=10.0))
    assert point == {"level": "alto", "reasons": ["calor 33 °C, aire seco 20 %, viento 10 km/h → peligro alto"]}


def test_sin_pronostico_para_hoy_no_hay_risk_point():
    assert risk.point_today({"time": []}) is None


def _add_observation(client, obs_id: str, lat: float, lon: float) -> None:
    """Una detección satelital reciente en la base del cliente de prueba."""
    svc = client.app.state.services
    moment = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    svc.db.execute(
        "INSERT INTO observations(id, source, sensor, satellite, resolution_m, lat, lon, observed_at, "
        "frp_mw, confidence, comuna_code, run_id, ingested_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL,?)",
        (obs_id, "firms", "VIIRS", "NOAA-21", 375, lat, lon, moment, 12.0, "alta", None, moment),
    )


@pytest.mark.parametrize(
    "lat,lon,obs_id,delta_lon",
    [(-53.2, -70.9, "sur-1", 0.28), (-33.4, -70.7, "centro-1", 0.20)],
)
def test_la_caja_de_precarga_cubre_el_doble_del_radio(make_client, web, lat, lon, obs_id, delta_lon):
    """FIX-62: la caja fija (±span·1,4) no alcanzaba a 53°S, donde un grado de longitud
    son ~67 km; la consulta descartaba focos que el filtro por distancia sí acepta.
    El control en Santiago (~33°S) comprueba que la escala por latitud no rompe el centro."""
    _open_meteo(web, hourly=_hourly(datetime.now(timezone.utc)))
    with make_client() as client:
        headers, (place_id,) = _setup(client, (lat, lon))  # radio 10 km
        _add_observation(client, obs_id, lat, lon + delta_lon)  # ~1,87 radios al este
        body = client.get(f"/api/places/{place_id}/summary", headers=headers).json()
    nearby = {o["id"]: o for o in body["nearby"]}
    assert obs_id in nearby and nearby[obs_id]["distance_km"] <= 20


def test_las_consultas_compartidas_se_hacen_una_vez_y_el_resumen_conserva_su_forma(make_client, web, monkeypatch):
    """Tres lugares de la misma comuna, tres resúmenes: una consulta por tabla, no tres;
    cada payload conserva sus claves y `official` sale de más cerca a más lejos."""
    _open_meteo(web, fail_hourly=True)
    cuenta = _contador(monkeypatch)
    with make_client(GOES_ENABLED="0") as client:
        headers, ids = _setup(client, *PUNTOS)
        db = client.app.state.services.db
        _aviso_dmc(db, [_comuna(db, ids[0])])
        _incendio(db, "F-cerca", PUNTOS[0][0] + 0.02, PUNTOS[0][1] + 0.02)
        _incendio(db, "F-lejos", PUNTOS[0][0] + 0.10, PUNTOS[0][1] + 0.10)
        cuerpos = [client.get(f"/api/places/{pid}/summary", headers=headers).json() for pid in ids]
    assert cuenta == {"official_fires": 1, "dmc_alerts": 1}
    claves = {
        "place",
        "comuna",
        "status",
        "cause",
        "wind",
        "official",
        "official_source",
        "dmc_alerts",
        "dmc_source",
        "nearby",
        "risk_days",
        "risk_point",
        "data_as_of",
    }
    for body in cuerpos:
        assert set(body) == claves
        assert [f["id"] for f in body["official"]] == ["F-cerca", "F-lejos"]
        assert [f["distance_km"] for f in body["official"]] == sorted(f["distance_km"] for f in body["official"])
        assert body["dmc_alerts"] and body["dmc_alerts"][0]["kind"] == "viento"

"""RISK-05: el 30-30-30 del lugar se calcula en su punto exacto, con caché por celda de 0,1°.

`GET /api/places/{id}/summary` entrega `risk_point` = {level, reasons, computed_at} usando el
pronóstico de Open-Meteo de la celda del lugar (lat/lon redondeados a un decimal). Lugares de
la misma celda comparten el cálculo — una sola petición de pronóstico — y si el proveedor
falla `risk_point` queda null sin romper el resumen.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx

from backend import risk
from backend.geo import territory
from tests.conftest import json_response


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


def test_la_cache_por_celda_evita_repetir_la_peticion(make_client, web):
    _open_meteo(web, hourly=_hourly(datetime.now(timezone.utc)))
    with make_client() as client:
        headers, (place_id,) = _setup(client, (-33.05, -71.55))
        for _ in range(2):  # dos llamadas al resumen = una sola petición de pronóstico
            body = client.get(f"/api/places/{place_id}/summary", headers=headers).json()
        assert _forecast_calls(web) == 1
        assert body["risk_point"]["level"] == "extremo"
        assert body["risk_point"]["computed_at"]
        assert "calor 33" in body["risk_point"]["reasons"][0]


def test_dos_lugares_de_la_misma_celda_comparten_el_calculo(make_client, web):
    _open_meteo(web, hourly=_hourly(datetime.now(timezone.utc)))
    with make_client() as client:
        # Ambos puntos caen en la celda (-33.0, -71.5) al redondear a un decimal.
        headers, (place_a, place_b) = _setup(client, (-33.02, -71.52), (-33.04, -71.53))
        a = client.get(f"/api/places/{place_a}/summary", headers=headers).json()
        b = client.get(f"/api/places/{place_b}/summary", headers=headers).json()
        assert _forecast_calls(web) == 1
        assert a["risk_point"] == b["risk_point"]


def test_un_lugar_en_otra_celda_pide_su_propio_pronostico(make_client, web):
    _open_meteo(web, hourly=_hourly(datetime.now(timezone.utc)))
    with make_client() as client:
        headers, (place_a, place_b) = _setup(client, (-33.02, -71.52), (-33.12, -71.52))
        client.get(f"/api/places/{place_a}/summary", headers=headers)
        client.get(f"/api/places/{place_b}/summary", headers=headers)
        assert _forecast_calls(web) == 2  # celdas (-33.0, -71.5) y (-33.1, -71.5): no se comparten


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


def test_la_caja_de_precarga_cubre_el_doble_del_radio_en_el_sur(make_client, web):
    """FIX-62: a 53°S un grado de longitud son ~67 km, no 111. La caja fija (±span·1,4)
    llegaba a ~1,68 radios al este/oeste y la consulta descartaba focos que el filtro
    por distancia sí acepta (hasta 2× el radio)."""
    _open_meteo(web, hourly=_hourly(datetime.now(timezone.utc)))
    with make_client() as client:
        headers, (place_id,) = _setup(client, (-53.2, -70.9))  # Punta Arenas, radio 10 km
        # ~18,7 km al este (~1,87 radios): fuera de la caja vieja, dentro de 2× el radio.
        _add_observation(client, "sur-1", -53.2, -70.9 + 0.28)
        body = client.get(f"/api/places/{place_id}/summary", headers=headers).json()
    nearby = {o["id"]: o for o in body["nearby"]}
    assert "sur-1" in nearby and nearby["sur-1"]["distance_km"] <= 20


def test_la_caja_sigue_incluyendo_focos_cercanos_en_la_zona_central(make_client, web):
    """Control del FIX-62: en Santiago (~33°S) la caja vieja ya alcanzaba; el foco a
    ~18,6 km al este debe seguir apareciendo con la escala por latitud."""
    _open_meteo(web, hourly=_hourly(datetime.now(timezone.utc)))
    with make_client() as client:
        headers, (place_id,) = _setup(client, (-33.4, -70.7))
        _add_observation(client, "centro-1", -33.4, -70.7 + 0.20)
        body = client.get(f"/api/places/{place_id}/summary", headers=headers).json()
    nearby = {o["id"]: o for o in body["nearby"]}
    assert "centro-1" in nearby and nearby["centro-1"]["distance_km"] <= 20

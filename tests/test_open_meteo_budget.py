"""REV-20: el cupo de Open-Meteo se mide en ubicaciones y la pasada de riesgo cabe en un tope.

RISK-04 evalúa cada comuna en varios puntos y el lote multi-ubicación no abre más peticiones,
pero cada punto descuenta cupo. Aquí se fija el presupuesto: los centros entran siempre, los
interiores se rotan entre pasadas y el total diario estimado queda bajo `DAILY_LOCATIONS_CAP`.
"""

from __future__ import annotations

import asyncio
import json
from datetime import date
from types import SimpleNamespace

import httpx
import pytest

from backend import geo, risk, services
from backend.geo import Comuna
from backend.providers import weather
from backend.settings import Settings
from tests.conftest import json_response


def _hourly() -> dict:
    """Un día de Chile con 12 horas válidas, suficiente para clasificar."""
    return {
        "time": [f"2027-01-15T{h:02d}:00" for h in range(12, 24)],
        "temperature_2m": [33.0] * 12,
        "relative_humidity_2m": [20.0] * 12,
        "wind_speed_10m": [35.0] * 12,
        "wind_gusts_10m": [45.0] * 12,
        "wind_direction_10m": [240] * 12,
    }


def _forecast(request: httpx.Request) -> httpx.Response:
    n = len(request.url.params["latitude"].split(","))
    return json_response([{"hourly": _hourly()} for _ in range(n)])


def _fake_territory(comunas: list[Comuna]):
    return SimpleNamespace(
        comunas=comunas,
        locate=lambda lat, lon, tol=0.01: next(
            (c for c in comunas if c.bbox[0] <= lon <= c.bbox[2] and c.bbox[1] <= lat <= c.bbox[3]), None
        ),
    )


def _comunas(n: int) -> list[Comuna]:
    """Comunas extensas (caja de 3° × 3°) sin traslape, con 5 puntos cada una."""
    comunas = []
    for code in range(1, n + 1):
        lon, lat = -70.0 - 3 * (code - 1), -35.0 - 3 * (code - 1)
        comunas.append(Comuna(code, f"Extensa {code}", "P", 1, "R", (lon, lat), (lon - 1.5, lat - 1.5, lon + 1.5, lat + 1.5)))
    return comunas


def test_el_gasto_diario_estimado_cabe_en_el_tope():
    """Con el intervalo por defecto (180 min), en enero y en mayo (12 tramos de archivo del FWI)."""
    comunas = geo.territory().comunas
    settings = Settings()
    passes = (24 * 60) // settings.risk_interval_min
    rain_daily = len(comunas) * 2 * max(1, 24 // services.RAIN_ANOMALY_EVERY_H) + settings.rain_normals_per_run * max(
        1, 24 // services.RAIN_EVERY_H
    )
    for day in (date(2027, 1, 15), date(2027, 5, 31)):
        budget = services.risk_points_per_pass(len(comunas), settings, day)
        fwi_daily = weather.fwi_locations(len(comunas), day) * max(1, 24 // services.FWI_EVERY_H)
        total = budget * passes + fwi_daily + rain_daily + services.OPEN_METEO_RESERVE
        assert budget >= len(comunas), "el presupuesto debe cubrir un punto por comuna"
        assert budget <= services.RISK_POINTS_PER_PASS
        assert total <= weather.DAILY_LOCATIONS_CAP, f"el {day} gasta {total} ubicaciones"


def test_budgeted_points_keeps_every_center_and_rotates_the_rest():
    per_comuna = [[(0.0, 0.0)], [(1.0, 1.0), (2.0, 2.0), (3.0, 3.0)], [(4.0, 4.0), (5.0, 5.0)]]
    first, offset = risk.budgeted_points(per_comuna, 5, 0)
    second, offset = risk.budgeted_points(per_comuna, 5, offset)

    for pass_ in (first, second):
        assert sum(len(points) for points in pass_) == 5
        assert [points[0] for points in pass_] == [(0.0, 0.0), (1.0, 1.0), (4.0, 4.0)]
        assert all(len(points) > 1 for points in pass_[1:]), "cada comuna extensa conserva un interior"
    seen = {point for pass_ in (first, second) for points in pass_ for point in points[1:]}
    assert seen == {(2.0, 2.0), (3.0, 3.0), (5.0, 5.0)}
    assert offset == 2, "el offset avanza para la próxima pasada"


def test_compute_risk_recorta_la_pasada_y_rota_los_interiores(make_client, web, monkeypatch):
    comunas = _comunas(10)
    monkeypatch.setattr(services, "territory", lambda: _fake_territory(comunas))
    monkeypatch.setattr(services, "RISK_POINTS_PER_PASS", 30)
    web.add(lambda r: "open-meteo" in r.url.host, _forecast)

    with make_client() as client:
        svc = client.app.state.services
        centers = {(c.center[1], c.center[0]) for c in comunas}
        all_points = {(p[0], p[1]) for c in comunas for p in risk.evaluation_points(c)}
        seen: set[tuple[float, float]] = set()
        for _ in range(3):
            web.requests.clear()
            asyncio.run(svc.compute_risk())
            requested = {
                (float(lat), float(lon))
                for request in web.requests
                for lat, lon in zip(request.url.params["latitude"].split(","), request.url.params["longitude"].split(","))
            }
            assert len(requested) == 30, "la pasada se recorta al presupuesto"
            assert centers <= requested, "el centro de cada comuna nunca se cae"
            seen |= requested
        assert seen == all_points, "en tres pasadas se evalúan todos los interiores"


def test_status_publica_ubicaciones_por_pasada_y_del_dia(make_client, web, monkeypatch):
    comunas = _comunas(2)
    monkeypatch.setattr(services, "territory", lambda: _fake_territory(comunas))
    web.add(lambda r: "open-meteo" in r.url.host, _forecast)

    with make_client() as client:
        svc = client.app.state.services
        asyncio.run(svc.compute_risk())
        om = client.get("/api/status").json()["open_meteo"]

    assert om["locations"] == 10 and om["by_endpoint_locations"] == {"forecast": 10}
    assert om["calls"] == 1 and om["by_endpoint"] == {"forecast": 1} and om["since"]
    assert om["daily_cap"] == weather.DAILY_LOCATIONS_CAP
    assert om["scheduled"]["tasks"]["risk"]["last"] == 10
    assert om["scheduled"]["tasks"]["risk"]["today"] == 10
    assert om["scheduled"]["total"] == 10


def test_fwi_se_calcula_una_vez_al_dia(make_client, monkeypatch):
    with make_client() as client:
        svc = client.app.state.services
        calls: list[int] = []

        async def fake_fwi() -> int:
            calls.append(1)
            svc.db.kv_set("fwi_computed_at", services.stamp())
            return 1

        async def fake_risk() -> int:
            return 0

        monkeypatch.setattr(svc, "compute_fwi", fake_fwi)
        monkeypatch.setattr(svc, "compute_risk", fake_risk)
        monkeypatch.setattr(svc, "capture_risk_snapshot", lambda: asyncio.sleep(0, result=0))
        asyncio.run(svc._risk_and_fwi())
        asyncio.run(svc._risk_and_fwi())
        assert calls == [1], "la segunda pasada del mismo día no vuelve a pedir el archivo"


def test_compute_fwi_registra_sus_ubicaciones(make_client, monkeypatch):
    with make_client() as client:
        svc = client.app.state.services

        async def fake_inputs(client_, points):
            weather._count(weather.ARCHIVE_URL, len(points))
            return [({}, {}) for _ in points]

        monkeypatch.setattr(weather, "fwi_inputs", fake_inputs)
        asyncio.run(svc.compute_fwi())
        day = json.loads(svc.db.kv_get("open_meteo_day"))
        assert day["tasks"]["fwi"]["last"] == len(geo.territory().comunas)
        assert day["total"] == len(geo.territory().comunas)


def test_fwi_deja_la_marca_de_intento_antes_de_pedir(make_client, monkeypatch):
    """Un fallo no puede reintentar el archivo de la temporada en cada ciclo del cron."""
    with make_client() as client:
        svc = client.app.state.services

        async def boom(client_, points):
            raise RuntimeError("429 Too Many Requests")

        monkeypatch.setattr(weather, "fwi_inputs", boom)
        with pytest.raises(RuntimeError):
            asyncio.run(svc.compute_fwi())
        assert svc.db.kv_get("fwi_try_at")


def test_la_anomalia_de_lluvia_se_calcula_una_vez_al_dia(make_client, monkeypatch):
    with make_client() as client:
        svc = client.app.state.services
        calls: list[str] = []

        async def fake_build(limit=None) -> int:
            return 0

        async def fake_anomaly() -> int:
            calls.append("anomalia")
            svc.db.kv_set("rain_anomaly_at", services.stamp())
            return 200

        monkeypatch.setattr(svc, "build_rain_normals", fake_build)
        monkeypatch.setattr(svc, "compute_rain_anomaly", fake_anomaly)
        assert asyncio.run(svc.rain_cycle())["rain_comunas"] == 200
        assert asyncio.run(svc.rain_cycle())["rain_comunas"] == 0
        assert calls == ["anomalia"], "la segunda vuelta del día no repite el archivo de la temporada"

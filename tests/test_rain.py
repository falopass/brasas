"""Pruebas de la anomalía de lluvia: ventana correcta, normal 1991-2020 y frases sin juicios falsos."""
from __future__ import annotations

from datetime import date

import pytest

from backend import rain


def test_season_window_only_covers_june_to_october():
    assert rain.season_window(date(2026, 5, 20)) == (date(2026, 6, 1), date(2026, 6, 1))  # aún no empieza
    assert rain.season_window(date(2026, 8, 15)) == (date(2026, 6, 1), date(2026, 8, 15))
    assert rain.season_window(date(2026, 11, 5)) == (date(2026, 6, 1), date(2026, 10, 31))


def fake_series(years: int, mm_per_day: float = 1.0, month_day: str = "07-10") -> dict[str, float]:
    """Serie diaria mínima: un solo día con lluvia por año, para poder contar exacto."""
    series = {}
    for year in range(1991, 1991 + years):
        series[f"{year}-{month_day}"] = mm_per_day
        series[f"{year}-06-01"] = 0.0
    return series


def test_normal_is_the_mean_of_the_same_day_over_30_years():
    normal = rain.build_normal(fake_series(30))
    assert normal["07-10"] == 1.0
    assert normal["06-01"] == 0.0


def test_normal_ignores_leap_day_and_sparse_days():
    series = fake_series(30)
    series["1992-02-29"] = 50.0
    series["2026-03-01"] = 99.0  # un solo año: no es normal
    normal = rain.build_normal(series)
    assert "02-29" not in normal
    assert "03-01" not in normal


def test_window_sums_only_the_same_days():
    normal = {"06-01": 2.0, "07-10": 1.0, "10-31": 5.0, "11-01": 7.0}
    assert rain.window_normal(normal, date(2026, 6, 1), date(2026, 7, 31)) == 3.0
    assert rain.window_normal(normal, date(2026, 6, 1), date(2026, 10, 31)) == 8.0
    series = {"2026-06-01": 4.0, "2026-07-10": 0.5, "2026-09-01": 9.9}
    assert rain.window_sum(series, date(2026, 6, 1), date(2026, 7, 31)) == 4.5


def test_levels_and_plain_text():
    assert rain.level(0.2) == "muy_seco" and rain.level(0.7) == "seco"
    assert rain.level(1.0) == "normal" and rain.level(1.3) == "humedo" and rain.level(2.0) == "muy_humedo"
    assert rain.level(1.5) == "muy_humedo", "el corte de 1,5 veces es el inicio de «muy por encima»"
    assert rain.level(None) is None
    wet = rain.evaluate(300.0, 200.0)
    assert wet["ratio"] == 1.5 and wet["percent"] == 50 and wet["level"] == "muy_humedo"
    assert "pasto" in wet["plain"], "más lluvia debe explicarse por el pasto que crecerá, no como alivio"
    dry = rain.evaluate(100.0, 200.0)
    assert dry["percent"] == -50 and "menos" in plain(dry)
    assert rain.evaluate(10.0, 0.0)["level"] is None, "sin normal no se inventa un nivel"


def plain(result: dict) -> str:
    return result["plain"]


def test_evaluate_without_data_says_so_and_never_looks_normal():
    empty = rain.evaluate(None, 100.0)
    assert empty["level"] is None and empty["ratio"] is None
    assert "Todavía no hay" in empty["plain"]
    assert rain.evaluate(50.0, None)["level"] is None


def test_rain_api_exposes_the_season(make_client):
    with make_client() as client:
        body = client.get("/api/risk").json()
    assert body["rain"] == {}
    assert "no es menos riesgo" in body["rain_source"]["note"]


def test_rain_cycle_builds_normals_with_a_budget_and_then_the_anomaly(make_client):
    """El ciclo avanza pocas celdas por vuelta y nunca deja la anomalía sin calcular."""
    import asyncio

    with make_client(RAIN_NORMALS_PER_RUN="3") as client:
        svc = client.app.state.services
        calls = []

        async def fake_build(limit=None):
            calls.append(("normales", limit))
            return 15

        async def fake_anomaly():
            calls.append(("anomalia", None))
            return 200

        svc.build_rain_normals = fake_build
        svc.compute_rain_anomaly = fake_anomaly
        assert asyncio.run(svc.rain_cycle()) == {"rain_normals": 15, "rain_comunas": 200}
        assert calls == [("normales", 3), ("anomalia", None)]


def test_rain_cycle_still_reports_the_anomaly_when_the_provider_rate_limits(make_client):
    """Un 429 en las normales no puede dejar sin dato la temporada ya calculada."""
    import asyncio

    from backend.providers.weather import WeatherRateLimited

    with make_client() as client:
        svc = client.app.state.services

        async def boom(limit=None):
            raise WeatherRateLimited("429")

        async def fake_anomaly():
            return 200

        svc.build_rain_normals = boom
        svc.compute_rain_anomaly = fake_anomaly
        assert asyncio.run(svc.rain_cycle()) == {"rain_normals": 0, "rain_comunas": 200}


def test_rain_cycle_can_be_frozen_with_zero(make_client):
    import asyncio

    with make_client(RAIN_NORMALS_PER_RUN="0") as client:
        svc = client.app.state.services
        built = []

        async def fake_build(limit=None):
            built.append(limit)
            return 1

        async def fake_anomaly():
            return 5

        svc.build_rain_normals = fake_build
        svc.compute_rain_anomaly = fake_anomaly
        assert asyncio.run(svc.rain_cycle()) == {"rain_normals": 0, "rain_comunas": 5}
        assert built == [], "con 0 no se pide nada al archivo"

"""Nivel de condiciones: 30-30-30 solo y combinado con el FWI.

Manda el índice más alto y, si los dos coinciden en «alto» o más, se sube un paso;
nunca se pasa de «extremo». También se cubren los umbrales hora a hora (`hour_flags`),
el puntaje continuo (`hour_score`), la clasificación del día (`classify_day`), el
recorte de días con pocas horas válidas (`evaluate`), la conversión UTC → día de Chile
(`local_day`) y RISK-04: varios puntos por comuna con el peor nivel del día
(`evaluation_points`, `evaluate_comuna`), sin multiplicar las peticiones a Open-Meteo.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest

from backend import risk
from backend.geo import Comuna
from tests.conftest import json_response


@pytest.mark.parametrize(
    "left,right,expected",
    [
        ("bajo", "moderado", "moderado"),
        ("alto", "bajo", "alto"),
        ("alto", "moderado", "alto"),
        ("bajo", "alto", "alto"),
        ("extremo", "extremo", "extremo"),
    ],
)
def test_combine_keeps_the_highest_and_never_passes_extremo(left, right, expected) -> None:
    assert risk.combine(left, right)[0] == expected


def test_combine_escalates_one_step_when_both_are_high_and_explains_both() -> None:
    level, reasons = risk.combine("alto", "alto")
    assert level == "extremo"
    assert reasons[0].startswith("30-30-30:") and reasons[1].startswith("FWI:")
    assert any("coinciden" in reason for reason in reasons)


def test_combine_without_fwi_keeps_the_3030_level_and_says_so() -> None:
    level, reasons = risk.combine("moderado", None)
    assert level == "moderado"
    assert any("sin dato" in reason for reason in reasons)


@pytest.mark.parametrize(
    "t,rh,wind,expected",
    [
        (30.0, 30.0, 30.0, (False, False, False)),
        (30.1, 29.9, 30.1, (True, True, True)),
        (None, None, None, (False, False, False)),
        (35.0, None, 40.0, (True, False, True)),
    ],
)
def test_hour_flags_uses_strict_thresholds_and_ignores_missing_values(t, rh, wind, expected) -> None:
    assert risk.hour_flags(t, rh, wind) == expected


def test_hour_score_is_zero_when_a_variable_is_missing() -> None:
    for args in ((None, 20.0, 40.0), (35.0, None, 40.0), (35.0, 20.0, None)):
        assert risk.hour_score(*args) == 0.0


def test_hour_score_grows_toward_the_thresholds_and_stays_within_0_and_100() -> None:
    assert risk.hour_score(20.0, 50.0, 10.0) < risk.hour_score(29.0, 31.0, 29.0) < risk.hour_score(33.0, 25.0, 35.0)
    assert risk.hour_score(18.0, 60.0, 8.0) < 30.0
    assert risk.hour_score(-10.0, 100.0, 0.0) == 0.0
    assert 0.0 <= risk.hour_score(45.0, 5.0, 120.0) <= 100.0


@pytest.mark.parametrize(
    "hours_3of3,hours_2of3,t,rh,wind,expected",
    [
        (1, 1, 34.0, 18.0, 95.0, "extremo"),
        (0, 3, 33.0, 35.0, 60.0, "alto"),
        (0, 1, 32.0, 45.0, 60.0, "moderado"),
        (0, 0, 27.0, 40.0, 20.0, "moderado"),
        (0, 0, 22.0, 55.0, 30.0, "bajo"),
        (2, 10, 40.0, 10.0, 100.0, "extremo"),
    ],
)
def test_classify_day_follows_the_3030_rule(hours_3of3, hours_2of3, t, rh, wind, expected) -> None:
    assert risk.classify_day(hours_3of3, hours_2of3, t, rh, wind) == expected


def _hourly(n: int, t: float = 33.0, rh: float = 20.0, wind: float = 35.0) -> dict[str, list]:
    """Un día de Chile con `n` horas (12-23 UTC: mediodía a 20 h en Chile, mismo día local)."""
    return {
        "time": [f"2027-01-15T{h:02d}:00" for h in range(12, 12 + n)],
        "temperature_2m": [t] * n,
        "relative_humidity_2m": [rh] * n,
        "wind_speed_10m": [wind] * n,
        "wind_gusts_10m": [wind + 10] * n,
        "wind_direction_10m": [240] * n,
    }


def test_evaluate_drops_days_with_too_few_valid_hours() -> None:
    # Un día incompleto tampoco se disfraza de «bajo»: sin horas suficientes no hay día.
    assert risk.evaluate(_hourly(risk.MIN_VALID_HOURS - 1))["days"] == []


def test_evaluate_full_day_appears_with_level_score_and_extremes() -> None:
    (day,) = risk.evaluate(_hourly(12))["days"]
    assert day["date"] == "2027-01-15"
    assert day["level"] == "extremo"
    assert day["score"] == int(round(day["max_score"]))
    assert day["tmax"] == 33.0
    assert day["rhmin"] == 20.0


def test_evaluate_hours_keep_order_and_z_suffix() -> None:
    stamps = [hour["time"] for hour in risk.evaluate(_hourly(8))["hours"]]
    assert stamps == sorted(stamps) and all(stamp.endswith("Z") for stamp in stamps)


@pytest.mark.parametrize(
    "stamp,expected",
    [
        ("2027-01-15T02:00", "2027-01-14"),
        ("2027-01-15T02:00Z", "2027-01-14"),
        ("2027-01-15T20:00", "2027-01-15"),
    ],
)
def test_local_day_uses_the_chilean_date(stamp, expected) -> None:
    assert risk.local_day(stamp) == expected


BIG = Comuna(1, "Extensa", "Prov", 1, "Región", (-70.0, -35.0), (-72.0, -37.0, -68.0, -33.0))
SMALL = Comuna(2, "Chica", "Prov", 1, "Región", (-73.0, -40.0), (-73.2, -40.2, -72.9, -40.1))


def test_evaluation_points_small_comuna_keeps_only_its_center() -> None:
    assert risk.evaluation_points(SMALL) == [(-40.0, -73.0)]


def test_evaluation_points_big_comuna_adds_inner_points_within_the_cap() -> None:
    points = risk.evaluation_points(BIG)
    assert points == [(-35.0, -70.0), (-36.0, -71.0), (-34.0, -71.0), (-36.0, -69.0), (-34.0, -69.0)]
    assert len(points) <= risk.MAX_POINTS


def test_evaluation_points_drops_the_ones_outside_the_polygon() -> None:
    points = risk.evaluation_points(BIG, inside=lambda lat, lon: lat < -35.0)
    assert points == [(-35.0, -70.0), (-36.0, -71.0), (-36.0, -69.0)]


def test_evaluate_comuna_keeps_the_worst_point_of_the_day() -> None:
    """El centro queda «sin 3-30» y un punto interior cumple el 30-30-30: manda el interior."""
    calm = _hourly(12, t=20.0, rh=60.0, wind=10.0)
    hot = _hourly(12, t=33.0, rh=20.0, wind=35.0)
    result = risk.evaluate_comuna([(-35.0, -70.0), (-36.0, -71.0)], [calm, hot])
    (day,) = result["days"]
    assert day["level"] == "extremo"
    assert result["points_used"] == 2 and result["points_used"] <= risk.MAX_POINTS
    assert result["worst_point"] == {"lat": -36.0, "lon": -71.0}
    # Las horas guardadas son las del peor punto y declaran su procedencia.
    assert len(result["hours"]) == 12 and result["hours"][0]["t"] == 33.0
    assert result["hours"][0]["points_used"] == 2 and result["hours"][0]["worst_point"] == result["worst_point"]
    # Con un solo punto se comporta como antes.
    one = risk.evaluate_comuna([(-35.0, -70.0)], [_hourly(12)])
    assert one["days"][0]["level"] == "extremo"
    assert one["points_used"] == 1 and one["worst_point"] == {"lat": -35.0, "lon": -70.0}


def test_compute_risk_multi_point_does_not_grow_http_requests(make_client, web, monkeypatch) -> None:
    """El lote multi-ubicación agrupa todos los puntos: 2 comunas con 1 o con 5 puntos
    gastan la misma petición. Además el nivel de la comuna sale del peor punto, no del centro."""
    from backend import services as services_mod

    def forecast(request: httpx.Request) -> httpx.Response:
        lats = request.url.params["latitude"].split(",")
        lons = request.url.params["longitude"].split(",")
        items = []
        for lat, lon in zip(lats, lons):
            # El centro de cada comuna (lon −70) queda «sin 3-30»; los puntos interiores lo cumplen.
            hot = float(lon) != -70.0
            items.append(
                {"hourly": _hourly(12, **({"t": 33.0, "rh": 20.0, "wind": 35.0} if hot else {"t": 20.0, "rh": 60.0, "wind": 10.0}))}
            )
        return json_response(items)

    web.add(lambda r: "open-meteo" in r.url.host, forecast)
    chicas = [SMALL, Comuna(3, "Chica 2", "P", 1, "R", (-72.0, -34.0), (-72.2, -34.2, -71.9, -34.1))]
    grandes = [BIG, Comuna(4, "Extensa 2", "P", 1, "R", (-70.0, -38.0), (-72.0, -40.0, -68.0, -36.0))]

    def fake_territory(comunas):
        return SimpleNamespace(
            comunas=comunas,
            locate=lambda lat, lon, tol=0.01: next(
                (c for c in comunas if c.bbox[0] <= lon <= c.bbox[2] and c.bbox[1] <= lat <= c.bbox[3]), None
            ),
        )

    with make_client() as client:
        svc = client.app.state.services
        monkeypatch.setattr(services_mod, "territory", lambda: fake_territory(chicas))
        assert asyncio.run(svc.compute_risk()) == 2
        assert sum("open-meteo" in r.url.host for r in web.requests) == 1  # 2 puntos en un solo lote
        web.requests.clear()
        monkeypatch.setattr(services_mod, "territory", lambda: fake_territory(grandes))
        assert asyncio.run(svc.compute_risk()) == 2
        assert sum("open-meteo" in r.url.host for r in web.requests) == 1  # 10 puntos, misma petición
        assert svc.db.one("SELECT level FROM risk_daily WHERE comuna_code = 1")["level"] == "extremo"
        payload = json.loads(svc.db.one("SELECT payload FROM risk_hourly WHERE comuna_code = 1")["payload"])
        assert payload[0]["points_used"] == 5 and payload[0]["worst_point"] == {"lat": -36.0, "lon": -71.0}

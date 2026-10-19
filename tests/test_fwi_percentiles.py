"""Percentiles locales del FWI: la regla de empates y el endpoint con su caché."""
from __future__ import annotations

from datetime import date, timedelta

from backend import fwi


def test_percentile_counts_below_plus_half_the_ties():
    """Regla: valores menores + la mitad de los empates (redondeo hacia arriba si son
    impares). En una serie sin repetidos equivale a la fracción «menor o igual»."""
    series = [float(i) for i in range(1, 11)]
    assert fwi.percentile(5, series) == 50
    assert fwi.percentile(10, series) == 100
    assert fwi.percentile(1, series) == 10


def test_percentile_without_enough_history_is_none():
    assert fwi.percentile(5.0, []) is None
    assert fwi.percentile(5.0, [float(i) for i in range(1, 10)]) is None  # 9 días < 10
    assert fwi.percentile(None, [1.0] * 20) is None


def test_percentile_all_ties_lands_in_the_middle():
    """Si la historia es toda igual, el valor no es ni el peor ni el mejor: queda en 50."""
    assert fwi.percentile(5.0, [5.0] * 4, minimum=4) == 50


def seed_fwi(db, code: int, values: list[float]) -> list[str]:
    """Una fila por valor, terminando hoy; devuelve las fechas en orden."""
    days = [(date.today() - timedelta(days=len(values) - 1 - i)).isoformat()
            for i in range(len(values))]
    for day, value in zip(days, values):
        db.execute(
            "INSERT INTO fwi_daily(comuna_code, date, ffmc, dmc, dc, isi, bui, fwi, level, computed_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (code, day, 80.0, 5.0, 10.0, 1.0, 10.0, value, fwi.level(value), "2026-10-01T00:00:00Z"))
    return days


def test_percentile_endpoint_404_without_history(make_client):
    with make_client() as client:
        response = client.get("/api/climate/fwi/percentile/999999")
    assert response.status_code == 404
    detail = response.json()["detail"]
    assert detail["code"] == "SIN_HISTORIAL" and "historial" in detail["message"]


def test_percentile_endpoint_with_few_days_says_so(make_client):
    with make_client() as client:
        days = seed_fwi(client.app.state.services.db, 13101, [3.0, 4.0, 5.0, 6.0, 7.0])
        body = client.get("/api/climate/fwi/percentile/13101").json()
    assert body["percentile"] is None and body["days"] == 5
    assert body["value"] == 7.0 and body["since"] == days[0]


def test_percentile_endpoint_compares_against_its_own_history(make_client):
    with make_client() as client:
        days = seed_fwi(client.app.state.services.db, 13101, [float(i) for i in range(1, 21)])
        body = client.get("/api/climate/fwi/percentile/13101").json()
    assert body["percentile"] == 100  # el 20 es el mayor de su propia historia
    assert body["days"] == 20 and body["since"] == days[0]
    assert body["value"] == 20.0 and body["level"] == "alto"
    assert body["source"] == "FWI de BRASA (Van Wagner)"


def test_percentile_endpoint_serves_the_cache(make_client, monkeypatch):
    with make_client() as client:
        svc = client.app.state.services
        seed_fwi(svc.db, 13101, [float(i) for i in range(1, 21)])
        first = client.get("/api/climate/fwi/percentile/13101").json()

        calls = []
        original = svc.db.query

        def counting(sql, params=()):
            calls.append(sql)
            return original(sql, params)

        monkeypatch.setattr(svc.db, "query", counting)
        second = client.get("/api/climate/fwi/percentile/13101").json()
        assert second == first
        assert not any("fwi_daily" in sql for sql in calls), "la segunda lectura debe salir de la caché"


def test_percentile_endpoint_rejects_a_non_numeric_code(make_client):
    with make_client() as client:
        assert client.get("/api/climate/fwi/percentile/abc").status_code == 422

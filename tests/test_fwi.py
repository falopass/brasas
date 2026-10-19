"""Pruebas del FWI contra el ejemplo publicado y contra los casos que no deben parecer «bajo»."""
from __future__ import annotations

import csv
from datetime import date, timedelta
from pathlib import Path

import pytest

from backend import fwi

REFERENCE = Path(__file__).parent / "data" / "fwi_reference.csv"
CODES = ("ffmc", "dmc", "dc", "isi", "bui", "fwi")


def reference_rows() -> list[dict[str, str]]:
    with REFERENCE.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_reference_series_matches_published_example():
    """48 días del ejemplo de Van Wagner (1987), tal como los reproduce el paquete cffdrs.

    Se arranca con los valores de primavera (FFMC 85, DMC 6, DC 15) y se avanza un día por fila.
    Una diferencia de más de dos centésimas en cualquier código significa que la cadena se desvió.
    """
    rows = reference_rows()
    assert len(rows) == 48
    out = fwi.series([{"date": r["date"], "temp": float(r["temp"]), "rh": float(r["rh"]),
                       "wind": float(r["wind"]), "rain": float(r["rain"])} for r in rows])
    assert [row["date"] for row in out] == [r["date"] for r in rows]
    worst = (0.0, "")
    for got, expected in zip(out, rows):
        for code in CODES:
            want = float(expected[code])
            delta = abs(got[code] - want)
            if delta > worst[0]:
                worst = (delta, f"{expected['date']} {code}: {got[code]} vs {want}")
            assert delta <= max(0.02, abs(want) * 1e-3), f"{expected['date']} {code}: {got[code]} vs {want}"
    assert out[-1]["fwi"] == pytest.approx(float(rows[-1]["fwi"]), abs=0.02), worst


def test_wet_day_collapses_fine_fuel_code():
    """Un día de lluvia intensa hunde el FFMC y con él el ISI: es el comportamiento del sistema."""
    dry = fwi.series([{"date": "2027-01-10", "temp": 30, "rh": 20, "wind": 25, "rain": 0}])[0]
    wet = fwi.series([{"date": "2027-01-10", "temp": 12, "rh": 95, "wind": 5, "rain": 20}])[0]
    assert dry["ffmc"] > 85 and wet["ffmc"] < 40
    assert dry["isi"] > wet["isi"] and dry["fwi"] > wet["fwi"]


def test_missing_observation_keeps_state_and_never_looks_low():
    rows = fwi.series([
        {"date": "2027-01-10", "temp": 30, "rh": 20, "wind": 25, "rain": 0},
        {"date": "2027-01-11", "temp": None, "rh": None, "wind": None, "rain": 0},
    ])
    first, second = rows
    assert second["missing"] is True
    assert (second["ffmc"], second["dmc"], second["dc"], second["fwi"]) == (
        first["ffmc"], first["dmc"], first["dc"], first["fwi"])


def test_levels_follow_cffdrs_thresholds():
    assert [fwi.level(v) for v in (0, 8.9, 9, 17.9, 18, 34.9, 35, 60)] == [
        "bajo", "bajo", "moderado", "moderado", "alto", "alto", "extremo", "extremo"]
    assert fwi.level(None) is None
    assert fwi.LEVEL_LABELS["extremo"] == "Extremo"


def test_summary_skips_days_without_data():
    rows = fwi.series([
        {"date": "2027-01-10", "temp": 30, "rh": 20, "wind": 25, "rain": 0},
        {"date": "2027-01-11", "temp": None, "rh": None, "wind": None, "rain": 0},
        {"date": "2027-01-12", "temp": 31, "rh": 18, "wind": 30, "rain": 0},
    ])
    assert [r["date"] for r in fwi.summary(rows, days=2)] == ["2027-01-10", "2027-01-12"]


def test_startup_matches_documented_spring_values():
    state = fwi.startup()
    assert (state.ffmc, state.dmc, state.dc) == (85.0, 6.0, 15.0)


def test_southern_hemisphere_uses_its_own_day_length_tables():
    """Enero es verano en Chile: el factor de secado debe ser alto, no el invernal del norte."""
    assert [fwi.day_length_factor(-33.0, m) for m in (1, 4, 7)] == [11.5, 7.9, 6.5]
    assert [fwi.day_length_factor(40.0, m) for m in (1, 4, 7)] == [6.5, 12.8, 12.4]
    assert fwi.day_length_factor(0.0, 1) == 9.0
    assert fwi.day_length_factor(None, 4) == 12.8  # sin latitud: tabla publicada de referencia
    assert [fwi.drought_factor(-33.0, m) for m in (1, 7)] == [6.4, -1.6]
    assert fwi.drought_factor(0.0, 1) == 1.4
    assert fwi.drought_factor(40.0, 1) == -1.6


def test_chile_in_january_dries_faster_than_the_northern_reference_table():
    """El mismo día seco acumula más humus perdido en enero del sur que con la tabla del norte."""
    south = fwi.series([{"date": "2027-01-15", "temp": 30, "rh": 20, "wind": 15, "rain": 0}], lat=-33.0)
    north = fwi.series([{"date": "2027-01-15", "temp": 30, "rh": 20, "wind": 15, "rain": 0}])
    assert south[0]["dmc"] > north[0]["dmc"]


def dry_season_rows() -> list[dict]:
    """Una temporada seca de la zona central: junio 2026 → 15 de enero 2027.

    Dos frentes débiles de invierno y nada después: un año «seco» sin ser un desierto absoluto.
    """
    temp_by_month = {6: 13.0, 7: 12.0, 8: 14.0, 9: 17.0, 10: 21.0, 11: 25.0, 12: 28.0, 1: 30.0}
    fronts = {date(2026, 7, 8): 12.0, date(2026, 8, 19): 6.0}
    rows = []
    day, end = date(2026, 6, 1), date(2027, 1, 15)
    while day <= end:
        rows.append({"date": day.isoformat(), "temp": temp_by_month[day.month],
                     "rh": 45.0, "wind": 12.0, "rain": fronts.get(day, 0.0)})
        day += timedelta(days=1)
    return rows


def test_dc_carried_from_june_beats_the_60_day_window():
    """La sequía profunda se arrastra desde el inicio de la temporada, no de 60 días atrás.

    Con la temporada seca sintética, el DC del 15 de enero arrastrado desde el 1 de junio queda
    muy por encima del que da una ventana de 60 días, que arranca en noviembre del valor de
    primavera canadiense (DC 15) como si recién saliera el invierno.
    """
    rows = dry_season_rows()
    carried = fwi.series(rows, lat=-33.0)
    windowed = fwi.series(rows[-60:], lat=-33.0)
    assert carried[-1]["date"] == windowed[-1]["date"] == "2027-01-15"
    assert carried[-1]["dc"] > windowed[-1]["dc"]
    # el año sintético es de verdad seco: hasta la ventana corta termina muy por sobre el arranque
    assert windowed[-1]["dc"] > fwi.INIT_DC


def fake_hours(days: int, rain_hour: int = 3) -> dict[str, list]:
    """Serie horaria sintética en hora local, con 1 mm de lluvia a las `rain_hour`."""
    hourly: dict[str, list] = {"time": [], "temperature_2m": [], "relative_humidity_2m": [],
                               "wind_speed_10m": [], "precipitation": []}
    for d in range(1, days + 1):
        for h in range(24):
            hourly["time"].append(f"2027-01-{d:02d}T{h:02d}:00")
            hourly["temperature_2m"].append(20.0 + h)
            hourly["relative_humidity_2m"].append(50.0)
            hourly["wind_speed_10m"].append(10.0)
            hourly["precipitation"].append(1.0 if h == rain_hour else 0.0)
    return hourly


def test_hourly_to_daily_takes_the_13h_observation_and_its_24h_rain():
    rows = fwi.hourly_to_daily(fake_hours(3))
    assert [r["date"] for r in rows] == ["2027-01-02", "2027-01-03"]  # el día 1 no tiene ventana completa
    assert rows[0]["temp"] == 33.0  # 20 + 13 h
    assert rows[0]["rain"] == 1.0   # la lluvia de las 03:00 del mismo día entra en la ventana


def test_hourly_to_daily_drops_days_without_the_observation():
    hourly = fake_hours(2)
    hourly["time"] = [t.replace("T13:00", "T12:00") for t in hourly["time"]]  # sin hora 13
    assert fwi.hourly_to_daily(hourly) == []


def test_merge_prefers_archive_and_completes_with_forecast():
    archive = [{"date": "2027-01-01", "temp": 10, "rh": 50, "wind": 5, "rain": 0},
               {"date": "2027-01-02", "temp": None, "rh": None, "wind": None, "rain": None}]
    forecast = [{"date": "2027-01-02", "temp": 12, "rh": 40, "wind": 8, "rain": 2},
                {"date": "2027-01-03", "temp": 14, "rh": 30, "wind": 9, "rain": 0}]
    merged = fwi.merge_days(archive, forecast)
    assert [r["date"] for r in merged] == ["2027-01-01", "2027-01-02", "2027-01-03"]
    assert merged[0]["temp"] == 10   # el archivo manda donde tiene datos
    assert merged[1]["temp"] == 12   # el hueco del archivo se rellena con el pronóstico
    assert merged[2]["temp"] == 14

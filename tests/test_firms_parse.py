"""FIXTURES-01: CSV real de VIIRS, sin red.

Fija el orden latitude/longitude, la interpretación UTC de ``acq_date`` + ``acq_time``, la
conversión a America/Santiago (UTC-4 en julio, UTC-3 en enero) y la frescura basada en la hora
de adquisición. La fixture es una muestra real de NASA FIRMS; ver ``tests/data/README.md``.
"""

from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend import alerts, freshness
from backend.geo import territory
from backend.providers import firms

SAMPLE = Path(__file__).parent / "data" / "firms_viirs_sample.csv"
CHILE = [-76.0, -56.0, -66.0, -17.0]
TALCA = (-35.42191, -71.63636)
HEADER = [
    "latitude",
    "longitude",
    "bright_ti4",
    "scan",
    "track",
    "acq_date",
    "acq_time",
    "satellite",
    "confidence",
    "version",
    "bright_ti5",
    "frp",
    "daynight",
]


def parse_sample() -> list[dict]:
    return firms.csv_hotspots(SAMPLE.read_text(encoding="utf-8"), "VIIRS_SNPP_NRT", CHILE)


def test_fixture_keeps_the_real_viirs_header_and_20_to_30_rows():
    with SAMPLE.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        assert reader.fieldnames == HEADER
        rows = list(reader)
    assert 20 <= len(rows) <= 30


def test_lat_lon_order_and_talca_is_in_maule():
    points = parse_sample()
    assert len(points) == 25
    point = next(p for p in points if (p["lat"], p["lon"]) == TALCA)
    comuna = territory().locate(point["lat"], point["lon"])
    assert comuna is not None and comuna.name == "Talca" and comuna.region == "Maule"
    # Si el parser invirtiera el orden, -71.63 como latitud cae fuera de Chile.
    assert territory().locate(point["lon"], point["lat"]) is None


def test_acq_date_and_time_are_utc_not_chile_local():
    point = next(p for p in parse_sample() if (p["lat"], p["lon"]) == TALCA)
    assert point["date"] == "2026-10-17"
    assert point["observed_at"] == "2026-10-17T18:24:00Z"
    assert datetime.fromisoformat(point["observed_at"].replace("Z", "+00:00")) == datetime(2026, 10, 17, 18, 24, tzinfo=timezone.utc)


def _two_dates_csv() -> str:
    rows = (
        "-35.42191,-71.63636,300.0,0.4,0.4,2026-07-15,1200,N,nominal,2.0NRT,280.0,1.0,N\n"
        "-35.42191,-71.63636,300.0,0.4,0.4,2027-01-15,1200,N,nominal,2.0NRT,280.0,1.0,N\n"
    )
    return ",".join(HEADER) + "\n" + rows


def test_chile_time_uses_the_real_zone_and_handles_both_offsets():
    assert alerts.CHILE_TZ.key == "America/Santiago"
    points = firms.csv_hotspots(_two_dates_csv(), "VIIRS_SNPP_NRT", CHILE)
    place = {"id": "casa", "name": "Casa", "lat": -35.42191, "lon": -71.63636, "older_adult": False}
    by_date = {p["date"]: p for p in points}
    july = alerts.compose(place, by_date["2026-07-15"], 0.1, 0, False, "aviso", None, 0)
    january = alerts.compose(place, by_date["2027-01-15"], 0.1, 0, False, "aviso", None, 0)
    assert "15-07 08:00 hora de Chile" in july["body"]  # UTC-4 en invierno
    assert "15-01 09:00 hora de Chile" in january["body"]  # UTC-3 en verano


def test_observed_at_is_the_acquisition_time_used_by_freshness():
    point = next(p for p in parse_sample() if (p["lat"], p["lon"]) == TALCA)
    observed = datetime.fromisoformat(point["observed_at"].replace("Z", "+00:00"))
    assert freshness.age_seconds(point["observed_at"], observed + timedelta(minutes=29)) == 29 * 60
    assert freshness.status(point["observed_at"], observed + timedelta(minutes=29))["stale"] is False
    assert freshness.status(point["observed_at"], observed + timedelta(minutes=31))["stale"] is True

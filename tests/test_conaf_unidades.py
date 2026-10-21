"""FIXTURES-01: unidades de CONAF (hectáreas, no metros cuadrados) con reportes reales.

Fija el contrato de ``sup_total`` → ``area_ha``: coma decimal española, punto de miles y el caso
``"0.500"`` = 0,5 ha (no 500). También cubre la superficie del Botón Rojo (``SUM_br_ha``).
La fixture es una transcripción real del reporte público de CONAF; ver ``tests/data/README.md``.
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import pytest

from backend.providers import conaf
from tests.test_conaf import CSV_HEAD, fire_row

REPORTS = Path(__file__).parent / "data" / "conaf_reportes_sample.json"


def test_fixture_has_real_reports_with_comma_decimals_and_an_integer():
    reports = json.loads(REPORTS.read_text(encoding="utf-8"))
    assert 3 <= len(reports) <= 5
    assert sum(isinstance(r["sup_total"], str) and "," in r["sup_total"] for r in reports) >= 3
    assert any(isinstance(r["sup_total"], int) for r in reports)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("0.500", 0.5),  # punto decimal con parte entera cero: media hectárea
        ("0,500", 0.5),  # coma decimal con parte entera cero
        ("1.234,5", 1234.5),  # formato español: punto de miles y coma decimal
        ("1.234", 1234.0),  # un solo punto con 3 dígitos: miles
        ("1234.5", 1234.5),  # punto decimal con 1 dígito: no es miles
        ("12", 12.0),  # entero simple
        (1, 1.0),  # entero JSON
    ],
)
def test_hectares_are_decided_per_row(raw, expected):
    assert conaf._number(raw) == expected


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("0.500", 0.5),
        ("1.234,5", 1234.5),
        ("12", 12.0),
    ],
)
def test_parse_fires_exposes_area_ha_in_hectares(raw, expected):
    [fire] = conaf.parse_fires(CSV_HEAD + fire_row("1", "EL BELLOTO", "En combate", "2027-01-20 15:30", -33.06, -71.40, raw))
    assert fire["area_ha"] == expected
    assert "area_ha" in fire and "area_m2" not in fire


def test_the_real_reports_keep_their_units():
    reports = json.loads(REPORTS.read_text(encoding="utf-8"))
    expected = {"892987017": 0.01, "882190717": 2.0, "889675553": 2.4, "898725420": 23.9, "893419859": 1.0}
    assert {r["id"]: conaf._number(r["sup_total"]) for r in reports} == expected


def test_the_real_reports_round_trip_through_parse_fires():
    reports = json.loads(REPORTS.read_text(encoding="utf-8"))
    fields = CSV_HEAD.strip().split(",")
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for report in reports:
        row = {field: "" for field in fields}
        row.update(
            {key: report[key] for key in ("id", "temporada", "nombre", "estado", "f_inicio", "sup_total", "lat", "lon", "comuna", "region")}
        )
        writer.writerow(row)
    fires = {fire["id"]: fire for fire in conaf.parse_fires(buffer.getvalue())}
    assert set(fires) == {report["id"] for report in reports}
    assert fires["892987017"] == {
        "id": "892987017",
        "name": "LAS LOMAS HJ.B",
        "status_raw": "Extinguido",
        "status": "extinguido",
        "started_at": "2026-07-10T00:59:00Z",
        "controlled_at": None,
        "extinguished_at": None,
        "detected_at": None,
        "alerted_at": None,
        "dispatched_at": None,
        "season": "2026",
        "area_ha": 0.01,
        "lat": -35.46083450317383,
        "lon": -71.14138793945312,
        "comuna": "San Clemente",
        "region": "Maule",
        "ambito": None,
        "fuel": None,
    }
    assert fires["898725420"]["started_at"] == "2026-09-26T19:57:00Z"  # UTC-3
    assert fires["893419859"]["area_ha"] == 1.0


def test_conaf_local_time_uses_the_real_zone():
    assert conaf.CHILE_TZ.key == "America/Santiago"
    assert conaf._local("2026-07-06 14:35") == "2026-07-06T18:35:00Z"  # UTC-4 en invierno
    assert conaf._local("2026-09-26 16:57") == "2026-09-26T19:57:00Z"  # UTC-3 en verano


def test_boton_rojo_area_is_hectares_not_square_metres():
    [day] = conaf.summarize([{"date": "2027-01-20", "com_id": 5109, "horas": 3, "SUM_br_ha": 2001.0, "proportion": 0.17}])
    assert day["area_ha"] == 2001  # 2001 ha; en m² serían 20.010.000

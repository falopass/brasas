"""Pruebas del índice ONI de la NOAA CPC (RISK-06): parseo, umbrales y «sin dato».

El fixture `ONI_TAIL` es real: encabezado y últimas 10 líneas de
https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt capturadas el 19-10-2026.
"""
from __future__ import annotations

import json

import httpx
import pytest

from backend.providers import noaa

ONI_TAIL = """ SEAS  YR   TOTAL   ANOM
  OND 2025  26.04  -0.61
  NDJ 2025  25.96  -0.60
  DJF 2026  26.15  -0.39
  JFM 2026  26.57  -0.21
  FMA 2026  27.34   0.11
  MAM 2026  28.09   0.46
  AMJ 2026  28.74   0.95
  MJJ 2026  29.02   1.39
  JJA 2026  29.09   1.80
  JAS 2026  29.12   2.16
"""


def test_parse_oni_reads_the_last_row():
    reading = noaa.parse_oni(ONI_TAIL)
    assert (reading.season, reading.year) == ("JAS", 2026)
    assert reading.sst == 29.12 and reading.oni == 2.16


def test_parse_oni_rejects_garbage():
    with pytest.raises(noaa.NoaaError):
        noaa.parse_oni("<html>404 no encontrado</html>")


def test_phase_thresholds():
    assert noaa.phase_of(2.16) == "nino"
    assert noaa.phase_of(0.5) == "nino"     # el límite mismo ya es El Niño
    assert noaa.phase_of(0.49) == "neutral"
    assert noaa.phase_of(0.0) == "neutral"
    assert noaa.phase_of(-0.49) == "neutral"
    assert noaa.phase_of(-0.5) == "nina"    # el límite mismo ya es La Niña
    assert noaa.phase_of(-1.3) == "nina"


def test_enso_endpoint_returns_the_reading(make_client, web):
    web.add(lambda r: r.url.host == "www.cpc.ncep.noaa.gov",
            lambda r: httpx.Response(200, text=ONI_TAIL))
    with make_client() as client:
        body = client.get("/api/climate/enso").json()
    assert body["phase"] == "nino" and body["oni"] == 2.16
    assert (body["season"], body["year"]) == ("JAS", 2026)
    assert body["updated_at"] and "NOAA" in body["source"] and body["source_url"].startswith("https://")


def test_enso_endpoint_says_no_data_when_noaa_is_down(make_client):
    # Sin ruta simulada la web falsa responde 503: la API no inventa un valor.
    with make_client() as client:
        body = client.get("/api/climate/enso").json()
    assert body["phase"] is None and body["oni"] is None and body["updated_at"] is None
    assert "NOAA" in body["source"] and body["source_url"]


def test_enso_endpoint_falls_back_to_last_saved(make_client):
    saved = {"phase": "nina", "oni": -0.9, "season": "DJF", "year": 2026,
             "updated_at": "2026-01-15T00:00:00Z", "source": noaa.SOURCE, "source_url": noaa.SOURCE_URL}
    with make_client() as client:
        client.app.state.services.db.kv_set("enso_last", json.dumps(saved))
        body = client.get("/api/climate/enso").json()  # el origen responde 503
    assert body["phase"] == "nina" and body["oni"] == -0.9
    assert body["updated_at"] == "2026-01-15T00:00:00Z"  # conserva la fecha original del dato

import asyncio
import csv
import json
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

from backend import alerts, freshness
from backend.geo import territory
from backend.providers import _retry, firms
from tests.conftest import json_response

CSV = """latitude,longitude,bright_ti4,acq_date,acq_time,frp,confidence,daynight
-35.43,-71.66,330.1,2026-10-16,0140,21.5,n,N
-35.43,-65.00,330.1,2026-10-16,0140,10.1,n,N
malformed,-71.66,330.1,2026-10-16,0140,21.5,n,N
-35.40,-71.60,331.0,2026-10-16,140,,h,D
-35.41,-71.61,331.0,2026-10-16,0975,3.0,h,D
"""
MAULE = [-72.85, -36.25, -70.25, -34.65]


def test_csv_normalizes_bounds_and_metadata():
    rows = firms.csv_hotspots(CSV, "VIIRS_NOAA21_NRT", MAULE)
    assert len(rows) == 2
    first = rows[0]
    assert first["observed_at"] == "2026-10-16T01:40:00Z"
    assert first["frp_mw"] == 21.5
    assert first["confidence"] == "nominal" and first["confidence_raw"] == "n"
    assert first["sensor"] == "VIIRS" and first["satellite"] == "NOAA-21" and first["resolution_m"] == 375
    # "140" se completa a 01:40; "0975" (minuto 75) se descarta; FRP vacío queda como None.
    assert rows[1]["observed_at"] == "2026-10-16T01:40:00Z"
    assert rows[1]["frp_mw"] is None and rows[1]["confidence"] == "alta"


def _csv_of(points):
    header = "latitude,longitude,bright_ti4,acq_date,acq_time,frp,confidence,daynight\n"
    return header + "".join(f"{lat},{lon},330.0,2026-10-16,0140,10.0,n,N\n" for lat, lon in points)


# Un rectángulo amplio a propósito: el filtro territorial (no el bbox) decide qué pasa.
SOUTH_AMERICA = [-90.0, -60.0, -60.0, -10.0]


def test_hotspots_outside_chilean_territory_are_dropped():
    rows = firms.csv_hotspots(_csv_of([
        (-32.89, -68.84),  # Mendoza, Argentina
        (-16.50, -68.15),  # La Paz, Bolivia
        (-16.40, -71.54),  # Arequipa, Perú
        (-35.43, -71.66),  # Talca
        (-53.16, -70.91),  # Punta Arenas
        (-42.48, -73.77),  # Castro, Chiloé
    ]), "VIIRS_NOAA21_NRT", SOUTH_AMERICA)
    assert sorted((r["lat"], r["lon"]) for r in rows) == [
        (-53.16, -70.91), (-42.48, -73.77), (-35.43, -71.66)]


def test_coastal_hotspot_within_tolerance_is_kept():
    # ~1 km frente a Valparaíso: fuera del polígono comunal, dentro de la tolerancia
    # costera (los bordes generalizados recortan islas, fiordos y costa).
    rows = firms.csv_hotspots(_csv_of([(-33.05, -71.6723)]), "VIIRS_NOAA21_NRT", SOUTH_AMERICA)
    assert len(rows) == 1


@pytest.mark.parametrize("body", ["<html>bad</html>", "Invalid MAP_KEY.", "foo,bar\n1,2\n"])
def test_malformed_upstream_is_rejected(body):
    with pytest.raises(firms.UpstreamError):
        firms.csv_hotspots(body, "x", MAULE)


def test_confidence_normalization():
    assert firms.normalize_confidence("h", "VIIRS") == "alta"
    assert firms.normalize_confidence("l", "VIIRS") == "baja"
    assert firms.normalize_confidence("85", "MODIS") == "alta"
    assert firms.normalize_confidence("50", "MODIS") == "nominal"
    assert firms.normalize_confidence("10", "MODIS") == "baja"
    assert firms.normalize_confidence("", "MODIS") is None


def test_split_window_respects_api_limit():
    chunks = firms.split_window(date(2024, 2, 1), date(2024, 2, 12))
    assert chunks == [(date(2024, 2, 1), 5), (date(2024, 2, 6), 5), (date(2024, 2, 11), 2)]


def test_partial_failure_is_a_notice_and_key_never_leaks():
    secret = "SUPER-SECRET-KEY-123"

    def handler(request: httpx.Request) -> httpx.Response:
        if "NOAA20" in request.url.path:
            return httpx.Response(500, text="boom")
        return httpx.Response(200, text=CSV)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await firms.fetch_hotspots(secret, MAULE, ("VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT"), client=client)

    points, notices = asyncio.run(run())
    assert len(points) == 2
    assert len(notices) == 1 and "VIIRS_NOAA20_NRT" in notices[0]
    assert secret not in " ".join(notices)


@pytest.mark.parametrize("status, attempts", [(500, 3), (404, 1)])
def test_a_permanent_failure_raises_without_the_key(status, attempts, monkeypatch):
    """El 500 se reintenta y el 404 no; en ambos casos la clave no viaja en el error."""
    monkeypatch.setattr(_retry, "RETRY_DELAYS", (0, 0))
    secret = "SUPER-SECRET-KEY-123"
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(status)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await firms.fetch_hotspots(secret, MAULE, ("VIIRS_NOAA21_NRT",), client=client)

    with pytest.raises(firms.UpstreamError) as exc:
        asyncio.run(run())
    assert len(calls) == attempts and secret not in str(exc.value)
    assert exc.value.__cause__ is None  # la excepción original (con la URL) no se encadena


@pytest.mark.parametrize("failures", [[503, 503], [429]])
def test_transient_errors_are_retried_until_success(failures, monkeypatch):
    monkeypatch.setattr(_retry, "RETRY_DELAYS", (0, 0))
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(failures[len(calls) - 1] if len(calls) <= len(failures) else 200, text=CSV)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await firms.fetch_hotspots("k", MAULE, ("VIIRS_NOAA21_NRT",), client=client)

    points, notices = asyncio.run(run())
    assert len(calls) == len(failures) + 1 and notices == [] and len(points) == 2


def test_historical_window_is_chunked():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return httpx.Response(200, text="latitude,longitude,acq_date\n")

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await firms.fetch_hotspots("k", MAULE, ("MODIS_SP",), start=date(2017, 1, 18), end=date(2017, 1, 29), client=client)

    asyncio.run(run())
    assert sorted(p.rsplit("/", 2)[-2:][0] + "/" + p.rsplit("/", 1)[-1] for p in seen) == ["2/2017-01-28", "5/2017-01-18", "5/2017-01-23"]


QUOTA = {"transaction_limit": 5000, "current_transactions": 46, "transaction_interval": "10 minutes"}


def test_status_reports_firms_quota_and_hides_the_key(make_client, web):
    web.add(lambda r: "mapkey_status" in r.url.path, lambda r: json_response(QUOTA))
    with make_client(FIRMS_MAP_KEY="map-key-secreta-123") as client:
        r = client.get("/api/status")
        assert r.status_code == 200
        quota = r.json()["firms_quota"]
        # ROB-01: la consulta a FIRMS va en segundo plano; la primera lectura solo la dispara
        # y el cupo aparece en cuanto la tarea lo guarda en `kv`.
        deadline = time.monotonic() + 10
        while quota["error"] and time.monotonic() < deadline:
            time.sleep(0.05)
            r = client.get("/api/status")
            quota = r.json()["firms_quota"]
        assert quota["limit"] == 5000 and quota["used"] == 46 and quota["error"] is False
        assert quota["checked_at"]
        # La segunda lectura sale del caché en `kv`: no gasta otra transacción de la clave.
        calls = len(web.requests)
        client.get("/api/status")
        assert len(web.requests) == calls
    assert "map-key-secreta-123" not in r.text


def test_status_quota_error_serves_the_last_known_value(make_client, web):
    web.add(lambda r: "mapkey_status" in r.url.path, lambda r: httpx.Response(500))
    with make_client(FIRMS_MAP_KEY="map-key-secreta-123") as client:
        r = client.get("/api/status")
        assert r.status_code == 200
        assert r.json()["firms_quota"] == {"limit": None, "used": None, "checked_at": None, "error": True}
        assert "map-key-secreta-123" not in r.text
        # Con una lectura anterior en `kv`, el bloque conserva los números y solo marca el error.
        svc = client.app.state.services
        svc.db.kv_set("firms_quota", json.dumps({"limit": 5000, "used": 12, "checked_at": "2020-01-01T00:00:00Z"}))
        assert client.get("/api/status").json()["firms_quota"] == {
            "limit": 5000, "used": 12, "checked_at": "2020-01-01T00:00:00Z", "error": True}


def test_status_quota_without_key_does_not_ask_firms(make_client, web):
    with make_client() as client:
        r = client.get("/api/status")
        assert r.status_code == 200 and r.json()["firms_quota"]["error"] is True
        assert not any("mapkey_status" in q.url.path for q in web.requests)


@pytest.mark.parametrize("status", [500, 429])
def test_retries_are_exhausted_after_three_attempts(status, monkeypatch):
    monkeypatch.setattr(_retry, "RETRY_DELAYS", (0, 0))
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(status)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await firms.fetch_hotspots("k", MAULE, ("VIIRS_NOAA21_NRT",), client=client)

    with pytest.raises(firms.UpstreamError):
        asyncio.run(run())
    assert len(calls) == 3


SP = ("VIIRS_NOAA20_SP", "VIIRS_SNPP_SP", "MODIS_SP")


@pytest.mark.parametrize("start, end, expected", [
    # Ventana que termina 2027-10-15: ya no cubren VIIRS_SNPP_SP ni MODIS_SP.
    (date(2027, 10, 1), date(2027, 10, 15), ("VIIRS_NOAA20_SP",)),
    (date(2026, 1, 1), date(2026, 1, 31), SP),
    (date(2026, 2, 10), date(2026, 2, 1), ()),   # ventana inválida
    (None, date(2026, 2, 1), ()),
])
def test_sources_for_drops_the_retired_products(start, end, expected):
    assert firms.sources_for(SP, start, end) == expected


@pytest.mark.parametrize("start, end", [(date(2020, 1, 1), date(2020, 1, 31)), (date(2035, 1, 1), date(2035, 12, 31))])
def test_sources_for_nrt_never_filtered(start, end):
    nrt = ("VIIRS_SNPP_NRT", "MODIS_NRT")
    assert firms.sources_for(nrt, start, end) == nrt


# ---------------------------------------------------------------- FIXTURES-01: CSV real de VIIRS
# Fija el orden latitude/longitude, la interpretación UTC de ``acq_date`` + ``acq_time``, la
# conversión a America/Santiago (UTC-4 en julio, UTC-3 en enero) y la frescura basada en la hora
# de adquisición. La fixture es una muestra real de NASA FIRMS; ver ``tests/data/README.md``.

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
    assert "15-07 08:00 hora de Chile continental" in july["body"]  # UTC-4 en invierno
    assert "15-01 09:00 hora de Chile continental" in january["body"]  # UTC-3 en verano


def test_observed_at_is_the_acquisition_time_used_by_freshness():
    point = next(p for p in parse_sample() if (p["lat"], p["lon"]) == TALCA)
    observed = datetime.fromisoformat(point["observed_at"].replace("Z", "+00:00"))
    assert freshness.age_seconds(point["observed_at"], observed + timedelta(minutes=29)) == 29 * 60
    assert freshness.status(point["observed_at"], observed + timedelta(minutes=29))["stale"] is False
    assert freshness.status(point["observed_at"], observed + timedelta(minutes=31))["stale"] is True

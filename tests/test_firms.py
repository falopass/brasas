import asyncio
import json
from datetime import date

import httpx

from backend.providers import firms
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


def test_malformed_upstream_is_rejected():
    for body in ("<html>bad</html>", "Invalid MAP_KEY.", "foo,bar\n1,2\n"):
        try:
            firms.csv_hotspots(body, "x", MAULE)
        except firms.UpstreamError:
            continue
        raise AssertionError(f"Se esperaba UpstreamError para {body!r}")


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


def test_total_failure_raises_without_key():
    secret = "SUPER-SECRET-KEY-123"

    async def run():
        transport = httpx.MockTransport(lambda r: httpx.Response(500))
        async with httpx.AsyncClient(transport=transport) as client:
            return await firms.fetch_hotspots(secret, MAULE, ("VIIRS_NOAA20_NRT",), client=client)

    try:
        asyncio.run(run())
    except firms.UpstreamError as exc:
        assert secret not in str(exc)
        assert exc.__cause__ is None  # la excepción original (con la URL) no se encadena
    else:
        raise AssertionError("Se esperaba UpstreamError")


def test_transient_503_is_retried_until_success():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(503) if len(calls) < 3 else httpx.Response(200, text=CSV)

    async def run():
        start = asyncio.get_event_loop().time()
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            points, notices = await firms.fetch_hotspots("k", MAULE, ("VIIRS_NOAA21_NRT",), client=client)
        return points, notices, asyncio.get_event_loop().time() - start

    points, notices, elapsed = asyncio.run(run())
    assert len(calls) == 3 and notices == [] and len(points) == 2
    assert elapsed < 2.0 + 1.0  # 0,5 s + 1,5 s de espera más margen holgado


def test_429_is_retried_once():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(429) if len(calls) == 1 else httpx.Response(200, text=CSV)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await firms.fetch_hotspots("k", MAULE, ("VIIRS_NOAA21_NRT",), client=client)

    points, notices = asyncio.run(run())
    assert len(calls) == 2 and notices == [] and len(points) == 2


def test_404_is_not_retried_and_key_never_leaks():
    secret = "SUPER-SECRET-KEY-123"
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(404)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await firms.fetch_hotspots(secret, MAULE, ("VIIRS_NOAA21_NRT",), client=client)

    try:
        asyncio.run(run())
    except firms.UpstreamError as exc:
        assert len(calls) == 1 and secret not in str(exc)
    else:
        raise AssertionError("Se esperaba UpstreamError")


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


def test_500_is_retried_three_times_then_fails():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(500)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await firms.fetch_hotspots("k", MAULE, ("VIIRS_NOAA21_NRT",), client=client)

    try:
        asyncio.run(run())
    except firms.UpstreamError:
        assert len(calls) == 3
    else:
        raise AssertionError("Se esperaba UpstreamError")


def test_429_is_retried_three_times_then_fails():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(429)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await firms.fetch_hotspots("k", MAULE, ("VIIRS_NOAA21_NRT",), client=client)

    try:
        asyncio.run(run())
    except firms.UpstreamError:
        assert len(calls) == 3
    else:
        raise AssertionError("Se esperaba UpstreamError")


SP = ("VIIRS_NOAA20_SP", "VIIRS_SNPP_SP", "MODIS_SP")


def test_sources_for_window_after_retirements():
    # Ventana que termina 2027-10-15: ya no cubren VIIRS_SNPP_SP ni MODIS_SP.
    assert firms.sources_for(SP, date(2027, 10, 1), date(2027, 10, 15)) == ("VIIRS_NOAA20_SP",)


def test_sources_for_window_january_2026():
    assert firms.sources_for(SP, date(2026, 1, 1), date(2026, 1, 31)) == SP


def test_sources_for_nrt_never_filtered():
    nrt = ("VIIRS_SNPP_NRT", "MODIS_NRT")
    for start, end in ((date(2020, 1, 1), date(2020, 1, 31)), (date(2035, 1, 1), date(2035, 12, 31))):
        assert firms.sources_for(nrt, start, end) == nrt


def test_sources_for_invalid_window_returns_empty():
    assert firms.sources_for(SP, date(2026, 2, 10), date(2026, 2, 1)) == ()
    assert firms.sources_for(SP, None, date(2026, 2, 1)) == ()

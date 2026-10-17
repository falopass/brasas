from backend.providers import csv_hotspots, REGIONS, UpstreamError

CSV = """latitude,longitude,bright_ti4,acq_date,acq_time,frp,confidence
-35.43,-71.66,330.1,2026-10-16,0140,21.5,n
-35.43,-65.00,330.1,2026-10-16,0140,10.1,n
malformed,-71.66,330.1,2026-10-16,0140,21.5,n
"""


def test_csv_normalizes_and_bounds():
    rows = csv_hotspots(CSV, "VIIRS_NOAA21_NRT", REGIONS["maule"]["bbox"])
    assert len(rows) == 1
    assert rows[0]["date"] == "2026-10-16"
    assert rows[0]["observed_at"] == "2026-10-16T01:40:00Z"
    assert rows[0]["frp_mw"] == 21.5


def test_malformed_upstream_is_rejected():
    try:
        csv_hotspots("<html>bad</html>", "x", REGIONS["maule"]["bbox"])
    except UpstreamError:
        pass
    else:
        raise AssertionError("Expected UpstreamError")


def test_http_config_does_not_expose_firms_key(monkeypatch):
    from fastapi.testclient import TestClient
    from backend.main import app
    monkeypatch.setenv('FIRMS_MAP_KEY','never-leak-this-secret')
    response = TestClient(app).get('/api/config')
    assert response.status_code == 200
    assert response.json()['firms_configured'] is True
    assert 'never-leak-this-secret' not in response.text


def test_no_firms_key_is_explicit_failure(monkeypatch):
    from fastapi.testclient import TestClient
    from backend.main import app
    monkeypatch.delenv('FIRMS_MAP_KEY', raising=False)
    response = TestClient(app).get('/api/hotspots?region=maule&days=3')
    assert response.status_code == 503
    assert response.json()['detail']['code'] == 'FIRMS_KEY_MISSING'


def test_historical_requires_start_date():
    from fastapi.testclient import TestClient
    from backend.main import app
    response = TestClient(app).get('/api/hotspots?region=maule&mode=historical')
    assert response.status_code == 422

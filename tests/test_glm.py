"""DET-03: rayos GLM de GOES-19 como conjunto abierto (`/api/opendata/lightning.geojson`).

El fixture `tests/data/glm_lcfa_sample.nc` se regenera con `tests/data/build_glm_sample.py`
y tiene cuatro destellos con valores conocidos: dos buenos dentro de la ventana de Chile,
uno bueno fuera y uno degradado. Ninguna prueba toca la red.
"""
from __future__ import annotations

import asyncio
import io
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

from backend.providers import _retry, glm, goes
from backend.routes import opendata

SAMPLE = Path(__file__).parent / "data" / "glm_lcfa_sample.nc"
KEY = ("GLM-L2-LCFA/2025/291/15/OR_GLM-L2-LCFA_G19_s20252911500000"
       "_e20252911500200_c20252911500300.nc")


# -------------------------------------------------------------------- parseo del producto

def test_parse_keeps_only_good_flashes_inside_the_window():
    flashes = glm.parse_lcfa(SAMPLE.read_bytes(), "G19", KEY)
    assert [f["id"] for f in flashes] == ["GOES19_GLM:202510181500:0", "GOES19_GLM:202510181500:1"]
    first = flashes[0]
    assert abs(first["lat"] + 33.05) < 0.01 and abs(first["lon"] + 71.55) < 0.01
    # El instante es la fecha del nombre del archivo más el offset del destello (12,5 s).
    assert first["observed_at"] == "2025-10-18T15:00:12Z"
    assert first["energy_j"] == 520.0 and first["area_km2"] == 48.0
    assert first["satellite"] == "GOES-19" and first["sensor"] == "GLM" and first["source"] == "GOES19_GLM"


def test_parse_respects_a_narrower_window():
    narrow = glm.parse_lcfa(SAMPLE.read_bytes(), "G19", KEY, window=(-72.0, -34.0, -71.0, -33.0))
    assert [f["id"] for f in narrow] == ["GOES19_GLM:202510181500:0"], "Concepción queda fuera"


def test_ids_are_stable_between_parses():
    a = [f["id"] for f in glm.parse_lcfa(SAMPLE.read_bytes(), "G19", KEY)]
    b = [f["id"] for f in glm.parse_lcfa(SAMPLE.read_bytes(), "G19", KEY)]
    assert a == b


def test_invalid_file_raises():
    with pytest.raises(goes.GoesError):
        glm.parse_lcfa(b"no es un HDF5", "G19", KEY)


def test_key_without_date_raises():
    with pytest.raises(goes.GoesError):
        glm.parse_lcfa(SAMPLE.read_bytes(), "G19", "GLM-L2-LCFA/2025/291/15/sin-fecha.nc")


def test_a_file_without_quality_flag_is_discarded():
    import h5py

    buf = io.BytesIO()
    with h5py.File(buf, "w") as f:
        f["flash_lat"] = [-33.0]
    assert glm.parse_lcfa(buf.getvalue(), "G19", KEY) == []


# -------------------------------------------------------------------- claves raras del listado

def _listing(*keys: str) -> httpx.Response:
    body = "".join(f"<Contents><Key>{k}</Key></Contents>" for k in keys)
    return httpx.Response(200, text=f"<ListBucketResult>{body}</ListBucketResult>")


def _fetch(web) -> list[dict]:
    """Corre `fetch_flashes` contra el S3 simulado de `web`."""
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(web.handler)) as client:
            return await glm.fetch_flashes(client)
    return asyncio.run(run())


def test_a_key_without_date_is_not_downloaded(web):
    web.add(lambda r: "list-type" in r.url.params,
            lambda r: _listing("GLM-L2-LCFA/2025/291/15/OR_GLM-L2-LCFA_G19.nc"))  # sin _sAAAADDD...
    assert _fetch(web) == []
    assert web.requests and all("list-type" in r.url.params for r in web.requests)


def test_a_key_that_fails_is_skipped_and_the_rest_is_returned(web, caplog):
    good = key_for(datetime.now(timezone.utc))
    bad = good + ".tmp"  # fecha válida en el nombre, pero el contenido no es un LCFA legible
    web.add(lambda r: "list-type" in r.url.params, lambda r: _listing(good, bad))
    web.add(lambda r: r.url.path.endswith(".tmp"),
            lambda r: httpx.Response(200, content=b"no es un HDF5"))
    web.add(lambda r: r.url.path.endswith(".nc"),
            lambda r: httpx.Response(200, content=SAMPLE.read_bytes()))
    with caplog.at_level("WARNING", logger="brasa.glm"):
        flashes = _fetch(web)
    assert len(flashes) == 2 and all(f["id"].startswith("GOES19_GLM:") for f in flashes)
    assert any(bad in r.getMessage() for r in caplog.records)


def test_a_full_window_downloads_only_the_newest_files(web, caplog):
    """Más de `MAX_FILES` claves en la ventana: se descargan solo las más recientes."""
    now = datetime.now(timezone.utc)
    keys = [key_for(now - timedelta(seconds=14 * i)) for i in range(glm.MAX_FILES + 5)]
    web.add(lambda r: "list-type" in r.url.params, lambda r: _listing(*keys))
    web.add(lambda r: r.url.path.endswith(".nc"),
            lambda r: httpx.Response(200, content=SAMPLE.read_bytes()))
    with caplog.at_level("WARNING", logger="brasa.glm"):
        flashes = _fetch(web)
    downloaded = {r.url.path.lstrip("/") for r in web.requests if "list-type" not in r.url.params}
    assert downloaded == set(keys[:glm.MAX_FILES]), "las 5 más viejas no se descargan"
    assert len(flashes) == glm.MAX_FILES * 2
    assert any("más recientes" in r.getMessage() for r in caplog.records)


def test_when_every_key_fails_the_error_propagates(web):
    web.add(lambda r: "list-type" in r.url.params,
            lambda r: _listing(key_for(datetime.now(timezone.utc))))
    web.add(lambda r: r.url.path.endswith(".nc"), lambda r: httpx.Response(500))
    with pytest.raises(goes.GoesError):
        _fetch(web)


# -------------------------------------------------------------------- reintentos de red

def test_listing_retries_a_transient_429(web, monkeypatch):
    monkeypatch.setattr(_retry, "RETRY_DELAYS", (0, 0))
    key = key_for(datetime.now(timezone.utc))
    answers = iter([httpx.Response(429), _listing(key)])
    web.add(lambda r: "list-type" in r.url.params, lambda r: next(answers))

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(web.handler)) as client:
            return await glm.list_keys(client, "G19", datetime.now(timezone.utc))
    assert asyncio.run(run()) == [key]
    assert len(web.requests) == 2


def test_a_download_404_is_not_retried(web, monkeypatch):
    monkeypatch.setattr(_retry, "RETRY_DELAYS", (0, 0))
    web.add(lambda r: True, lambda r: httpx.Response(404))

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(web.handler)) as client:
            await glm.download(client, "G19", KEY)
    with pytest.raises(goes.GoesError, match=r"tras 1 intento\)"):
        asyncio.run(run())
    assert len(web.requests) == 1


def test_three_500s_raise_mentioning_three_attempts(web, monkeypatch):
    monkeypatch.setattr(_retry, "RETRY_DELAYS", (0, 0))
    web.add(lambda r: True, lambda r: httpx.Response(500))

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(web.handler)) as client:
            await glm.download(client, "G19", KEY)
    with pytest.raises(goes.GoesError, match="tras 3 intentos"):
        asyncio.run(run())
    assert len(web.requests) == 3


# -------------------------------------------------------------------- el conjunto abierto

def key_for(moment: datetime) -> str:
    """Clave S3 GLM con el formato real (`_sAAAADDDHHMMSS`) calculada al momento del pedido."""
    doy = moment.timetuple().tm_yday
    return (f"GLM-L2-LCFA/{moment:%Y}/{doy:03d}/{moment:%H}/"
            f"OR_GLM-L2-LCFA_G19_s{moment.year}{doy:03d}{moment:%H%M%S}0_e.nc")


@pytest.fixture
def web_glm(web, monkeypatch):
    """S3 simulado: todo listado devuelve un archivo reciente y toda descarga, el fixture."""
    monkeypatch.setattr(opendata, "_LIGHTNING_CACHE", {})
    web.add(lambda r: "list-type" in r.url.params,
            lambda r: httpx.Response(
                200, text=f"<ListBucketResult><Contents><Key>{key_for(datetime.now(timezone.utc))}"
                          "</Key></Contents></ListBucketResult>"))
    web.add(lambda r: r.url.path.endswith(".nc"),
            lambda r: httpx.Response(200, content=SAMPLE.read_bytes()))
    return web


def test_lightning_geojson_has_the_expected_shape(make_client, web_glm):
    with make_client() as client:
        response = client.get("/api/opendata/lightning.geojson")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/geo+json")
        assert response.headers["cache-control"] == "public, max-age=60"
        body = response.json()
    assert body["type"] == "FeatureCollection" and body["count"] == 2
    assert body["source"] == "NOAA GOES-19 GLM (dominio público)" and body["hours"] == 1
    feature = body["features"][0]
    assert feature["geometry"]["type"] == "Point" and len(feature["geometry"]["coordinates"]) == 2
    props = feature["properties"]
    assert props["id"].startswith("GOES19_GLM:") and props["observed_at"].endswith("Z")
    assert props["age_s"] >= 0 and props["energy_j"] == 520.0 and props["area_km2"] == 48.0


def test_hours_is_validated(make_client, web_glm):
    with make_client() as client:
        assert client.get("/api/opendata/lightning.geojson?hours=0").status_code == 422
        assert client.get("/api/opendata/lightning.geojson?hours=7").status_code == 422
        assert client.get("/api/opendata/lightning.geojson?hours=6").status_code == 200


def test_the_window_is_cached_for_five_minutes(make_client, web_glm):
    with make_client() as client:
        client.get("/api/opendata/lightning.geojson")
        asked = len(web_glm.requests)
        client.get("/api/opendata/lightning.geojson")
        assert len(web_glm.requests) == asked, "la misma ventana no vuelve a S3 en menos de 5 min"
        client.get("/api/opendata/lightning.geojson?hours=2")
        assert len(web_glm.requests) > asked, "otra ventana sí vuelve a pedir"


def test_a_fallen_s3_responds_503_without_breaking_the_index(make_client, web, monkeypatch):
    monkeypatch.setattr(opendata, "_LIGHTNING_CACHE", {})
    web.add(lambda r: True, lambda r: httpx.Response(500))
    with make_client() as client:
        response = client.get("/api/opendata/lightning.geojson")
        assert response.status_code == 503
        assert "no están disponibles" in response.json()["detail"]
        assert client.get("/api/opendata").status_code == 200


def test_the_index_lists_the_lightning_dataset(make_client):
    with make_client() as client:
        datasets = client.get("/api/opendata").json()["datasets"]
    lightning = next(d for d in datasets if d["id"] == "lightning")
    assert lightning["url"] == "/api/opendata/lightning.geojson"
    assert "hours" in lightning["params"] and "age_s" in lightning["properties"]

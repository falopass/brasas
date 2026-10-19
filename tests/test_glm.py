"""DET-03: rayos GLM de GOES-19 como conjunto abierto (`/api/opendata/lightning.geojson`).

El fixture `tests/data/glm_lcfa_sample.nc` se regenera con `tests/data/build_glm_sample.py`
y tiene cuatro destellos con valores conocidos: dos buenos dentro de la ventana de Chile,
uno bueno fuera y uno degradado. Ninguna prueba toca la red.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from backend.providers import glm, goes
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
        assert client.get("/api/opendata/lightning.geojson?hours=25").status_code == 422
        assert client.get("/api/opendata/lightning.geojson?hours=24").status_code == 200


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

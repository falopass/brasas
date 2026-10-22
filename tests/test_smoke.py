"""DET-04: humo de GOES-19 (ABI-L2-ADPF) como conjunto abierto (`/api/opendata/smoke.geojson`).

El fixture se construye en memoria con `h5py`, con los mismos nombres de dataset del producto
real (`Smoke`, `DQF`, `Dust`, `Cloud`, `SnowIce`, `x`, `y`, `goes_imager_projection`) y valores
conocidos: dos puntos de humo válidos dentro de la ventana, uno fuera, uno con calidad mala y
un parche 3×3 para el agrupado. Ninguna prueba toca la red.
"""

from __future__ import annotations

import asyncio
import io
from datetime import datetime, timedelta, timezone

import h5py
import httpx
import numpy as np
import pytest

from backend.providers import goes, smoke
from backend.routes import opendata

PROJ = goes.Projection(lon0=-75.0, h=35786023.0 + 6378137.0, r_eq=6378137.0, r_pol=6356752.31414)
KEY = "ABI-L2-ADPF/2026/292/04/OR_ABI-L2-ADPF-M6_G19_s20262920400208_e20262920409517_c20262920414009.nc"
WINDOW = (-75.0, -38.0, -68.0, -30.0)


def synthetic_adp(smokes: list[tuple[float, float, int, bool]], size: int = 240) -> bytes:
    """ADPF mínimo con la misma estructura que el producto real, cubriendo Chile central.

    `smokes` es una lista de (lat, lon, qf, block): la calidad va a los bits 2-3 del DQF
    (0 alta, 4 media, 8 baja, 12 malo) y `block` marca un parche 3×3 en vez de un píxel.
    """
    x_w, y_s = goes.latlon_to_scan(PROJ, -40.0, -76.0)
    x_e, y_n = goes.latlon_to_scan(PROJ, -28.0, -66.0)
    xs = (x_e - x_w) / (size - 1)
    ys = -(y_n - y_s) / (size - 1)
    mask = np.zeros((size, size), dtype="int8")
    dqf = np.zeros((size, size), dtype="uint16")
    for lat, lon, qf, block in smokes:
        x, y = goes.latlon_to_scan(PROJ, lat, lon)
        col, row = int(round((x - x_w) / xs)), int(round((y - y_n) / ys))
        if block:
            mask[row - 1 : row + 2, col - 1 : col + 2] = 1
            dqf[row - 1 : row + 2, col - 1 : col + 2] = qf
        else:
            mask[row, col] = 1
            dqf[row, col] = qf
    buf = io.BytesIO()
    with h5py.File(buf, "w") as f:
        f.attrs["time_coverage_start"] = np.bytes_(b"2026-10-19T04:00:20.8Z")
        gp = f.create_dataset("goes_imager_projection", data=np.int32(0))
        gp.attrs["longitude_of_projection_origin"] = np.array([-75.0])
        gp.attrs["perspective_point_height"] = np.array([35786023.0])
        gp.attrs["semi_major_axis"] = np.array([6378137.0])
        gp.attrs["semi_minor_axis"] = np.array([6356752.31414])
        xd = f.create_dataset("x", data=np.arange(size, dtype="int16"))
        xd.attrs["scale_factor"], xd.attrs["add_offset"] = np.array([xs], "float32"), np.array([x_w], "float32")
        yd = f.create_dataset("y", data=np.arange(size, dtype="int16"))
        yd.attrs["scale_factor"], yd.attrs["add_offset"] = np.array([ys], "float32"), np.array([y_n], "float32")
        f.create_dataset("Smoke", data=mask).attrs["_FillValue"] = np.array([-128], "int8")
        f.create_dataset("Dust", data=np.zeros((size, size), dtype="int8")).attrs["_FillValue"] = np.array([-128], "int8")
        f.create_dataset("Cloud", data=np.zeros((size, size), dtype="int8")).attrs["_FillValue"] = np.array([-128], "int8")
        f.create_dataset("SnowIce", data=np.zeros((size, size), dtype="int8")).attrs["_FillValue"] = np.array([-128], "int8")
        f.create_dataset("DQF", data=dqf).attrs["_FillValue"] = np.array([65535], "uint16")
    return buf.getvalue()


# -------------------------------------------------------------------- parseo del producto


def test_parse_extracts_only_valid_smoke_inside_the_window():
    content = synthetic_adp(
        [
            (-33.1, -71.5, 0, False),  # humo, confianza alta
            (-36.6, -72.1, 4, False),  # humo, confianza media
            (-29.0, -67.0, 0, False),  # humo, fuera de la ventana
            (-35.0, -70.0, 12, False),  # humo marcado pero dato malo/faltante: se descarta
        ]
    )
    cells = smoke.parse_adp(content, KEY, window=WINDOW)
    assert len(cells) == 2
    vina = min(cells, key=lambda c: c["lat"])
    assert abs(vina["lat"] + 36.6) < 0.08 and abs(vina["lon"] + 72.1) < 0.08
    assert vina["observed_at"] == "2026-10-19T04:00:20Z"
    assert vina["min_lat"] <= vina["lat"] <= vina["max_lat"]
    assert vina["min_lon"] <= vina["lon"] <= vina["max_lon"]


@pytest.mark.parametrize(
    ("content", "key"), [(b"no es un HDF5", KEY), (None, "ABI-L2-ADPF/2026/292/04/sin-fecha.nc")], ids=["hdf5-invalido", "clave-sin-fecha"]
)
def test_archivo_o_clave_invalida_lanza(content, key):
    with pytest.raises(goes.GoesError):
        smoke.parse_adp(synthetic_adp([]) if content is None else content, key)


# -------------------------------------------------------------------- agrupado en polígonos


def test_polygons_merges_adjacent_cells_and_counts_pixels():
    content = synthetic_adp([(-33.1, -71.5, 0, True), (-36.6, -72.1, 0, False)])
    cells = smoke.parse_adp(content, KEY, window=WINDOW)
    assert len(cells) == 10  # parche 3×3 + píxel suelto
    polys = smoke.polygons(cells)
    assert len(polys) == 2, "el parche es una mancha y el píxel suelto, otra"
    by_cells = {p["cells"]: p for p in polys}
    assert 9 in by_cells and 1 in by_cells
    assert all(p["observed_at"] == "2026-10-19T04:00:20Z" for p in polys)
    assert all(p["geometry"]["type"] == "Polygon" for p in polys)


def test_polygons_separates_scans_and_empty_input():
    cells = smoke.parse_adp(synthetic_adp([(-33.1, -71.5, 0, False)]), KEY, window=WINDOW)
    later = [dict(c, observed_at="2026-10-19T04:10:20Z") for c in cells]
    polys = smoke.polygons(cells + later)
    assert {p["observed_at"] for p in polys} == {"2026-10-19T04:00:20Z", "2026-10-19T04:10:20Z"}
    assert smoke.polygons([]) == []


# -------------------------------------------------------------------- claves raras del listado


def _listing(*keys: str) -> httpx.Response:
    body = "".join(f"<Contents><Key>{k}</Key></Contents>" for k in keys)
    return httpx.Response(200, text=f"<ListBucketResult>{body}</ListBucketResult>")


def _fetch(web) -> list[dict]:
    """Corre `fetch_smoke` contra el S3 simulado de `web`."""

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(web.handler)) as client:
            return await smoke.fetch_smoke(client)

    return asyncio.run(run())


def test_a_key_without_date_is_not_downloaded(web):
    web.add(
        lambda r: "list-type" in r.url.params, lambda r: _listing("ABI-L2-ADPF/2026/292/04/OR_ABI-L2-ADPF-M6_G19.nc")
    )  # sin _sAAAADDD...
    with pytest.raises(goes.GoesError):  # sin claves legibles es como un bucket vacío
        _fetch(web)
    assert web.requests and all("list-type" in r.url.params for r in web.requests)


def test_a_key_that_fails_is_skipped_and_the_rest_is_returned(web, caplog):
    now = datetime.now(timezone.utc)
    good = [key_for(now), key_for(now - timedelta(minutes=20))]
    bad = key_for(now - timedelta(minutes=10)) + ".tmp"  # fecha válida en el nombre, contenido ilegible
    web.add(lambda r: "list-type" in r.url.params, lambda r: _listing(*good, bad))
    web.add(lambda r: r.url.path.endswith(".tmp"), lambda r: httpx.Response(200, content=b"no es un HDF5"))
    web.add(lambda r: r.url.path.endswith(".nc"), lambda r: httpx.Response(200, content=sample_file()))
    with caplog.at_level("WARNING", logger="brasa.smoke"):
        cells = _fetch(web)
    assert len(cells) == 20, "dos archivos × (parche 3×3 + píxel suelto)"
    assert any(bad in r.getMessage() for r in caplog.records)


def test_when_every_key_fails_the_error_propagates(web):
    web.add(lambda r: "list-type" in r.url.params, lambda r: _listing(key_for(datetime.now(timezone.utc))))
    web.add(lambda r: r.url.path.endswith(".nc"), lambda r: httpx.Response(500))
    with pytest.raises(goes.GoesError):
        _fetch(web)


# -------------------------------------------------------------------- el conjunto abierto


def key_for(moment: datetime) -> str:
    """Clave S3 ADPF con el formato real (`_sAAAADDDHHMMSS`) calculada al momento del pedido."""
    doy = moment.timetuple().tm_yday
    return f"ABI-L2-ADPF/{moment:%Y}/{doy:03d}/{moment:%H}/OR_ABI-L2-ADPF-M6_G19_s{moment.year}{doy:03d}{moment:%H%M%S}0_e.nc"


def sample_file() -> bytes:
    return synthetic_adp([(-33.1, -71.5, 0, True), (-36.6, -72.1, 0, False)])


@pytest.fixture
def web_adp(web, monkeypatch):
    """S3 simulado: todo listado devuelve un archivo reciente y toda descarga, el fixture."""
    monkeypatch.setattr(opendata, "_SMOKE_CACHE", {})
    web.add(
        lambda r: "list-type" in r.url.params,
        lambda r: httpx.Response(
            200, text=f"<ListBucketResult><Contents><Key>{key_for(datetime.now(timezone.utc))}</Key></Contents></ListBucketResult>"
        ),
    )
    web.add(lambda r: r.url.path.endswith(".nc"), lambda r: httpx.Response(200, content=sample_file()))
    return web


def test_smoke_geojson_has_the_expected_shape(make_client, web_adp):
    with make_client() as client:
        response = client.get("/api/opendata/smoke.geojson")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/geo+json")
        assert response.headers["cache-control"] == "public, max-age=60"
        body = response.json()
    assert body["type"] == "FeatureCollection" and body["count"] == 2
    assert body["source"] == "NOAA GOES-19 ABI-L2-ADPF (dominio público)" and body["hours"] == 1
    feature = max(body["features"], key=lambda f: f["properties"]["cells"])
    assert feature["type"] == "Feature" and feature["geometry"]["type"] == "Polygon"
    props = feature["properties"]
    assert props["observed_at"].endswith("Z") and props["age_min"] >= 0 and props["cells"] == 9


def test_hours_is_validated(make_client, web_adp):
    with make_client() as client:
        assert client.get("/api/opendata/smoke.geojson?hours=0").status_code == 422
        assert client.get("/api/opendata/smoke.geojson?hours=7").status_code == 422
        assert client.get("/api/opendata/smoke.geojson?hours=6").status_code == 200


def test_the_window_is_cached_for_five_minutes(make_client, web_adp):
    with make_client() as client:
        client.get("/api/opendata/smoke.geojson")
        asked = len(web_adp.requests)
        client.get("/api/opendata/smoke.geojson")
        assert len(web_adp.requests) == asked, "la misma ventana no vuelve a S3 en menos de 5 min"
        client.get("/api/opendata/smoke.geojson?hours=2")
        assert len(web_adp.requests) > asked, "otra ventana sí vuelve a pedir"


@pytest.mark.parametrize("empty_bucket", [False, True], ids=["s3-caido", "sin-archivos"])
def test_sin_datos_recientes_responde_503_sin_romper_el_indice(make_client, web, monkeypatch, empty_bucket):
    monkeypatch.setattr(opendata, "_SMOKE_CACHE", {})
    if empty_bucket:
        web.add(lambda r: "list-type" in r.url.params, lambda r: httpx.Response(200, text="<ListBucketResult></ListBucketResult>"))
    else:
        web.add(lambda r: True, lambda r: httpx.Response(500))
    with make_client() as client:
        response = client.get("/api/opendata/smoke.geojson")
        assert response.status_code == 503
        assert "no está disponible" in response.json()["detail"]
        if not empty_bucket:
            assert client.get("/api/opendata").status_code == 200

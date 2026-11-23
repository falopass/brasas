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


AOD_KEY = "ABI-L2-AODF/2026/292/04/OR_ABI-L2-AODF-M6_G19_s20262920400208_e20262920409517_c20262920414009.nc"
AOD_SCALE, AOD_OFFSET, AOD_FILL = 0.00015, -0.05, 65535


def synthetic_aod(points: list[tuple[float, float, float | None, int, bool]], size: int = 240) -> bytes:
    """AODF mínimo con la grilla de `synthetic_adp`: `AOD` uint16 empaquetado y `DQF` uint8.

    `points` es una lista de (lat, lon, aod, dqf, block); `aod=None` deja el `_FillValue`
    en el píxel. `DQF`: 0 alta, 1 media, 2 baja, 3 sin dato (el valor de fondo).
    """
    x_w, y_s = goes.latlon_to_scan(PROJ, -40.0, -76.0)
    x_e, y_n = goes.latlon_to_scan(PROJ, -28.0, -66.0)
    xs = (x_e - x_w) / (size - 1)
    ys = -(y_n - y_s) / (size - 1)
    raw = np.full((size, size), AOD_FILL, dtype="uint16")
    dqf = np.full((size, size), 3, dtype="uint8")
    for lat, lon, aod, quality, block in points:
        x, y = goes.latlon_to_scan(PROJ, lat, lon)
        col, row = int(round((x - x_w) / xs)), int(round((y - y_n) / ys))
        sl = (slice(row - 1, row + 2), slice(col - 1, col + 2)) if block else (row, col)
        raw[sl] = AOD_FILL if aod is None else int(round((aod - AOD_OFFSET) / AOD_SCALE))
        dqf[sl] = quality
    buf = io.BytesIO()
    with h5py.File(buf, "w") as f:
        gp = f.create_dataset("goes_imager_projection", data=np.int32(0))
        gp.attrs["longitude_of_projection_origin"] = np.array([-75.0])
        gp.attrs["perspective_point_height"] = np.array([35786023.0])
        gp.attrs["semi_major_axis"] = np.array([6378137.0])
        gp.attrs["semi_minor_axis"] = np.array([6356752.31414])
        xd = f.create_dataset("x", data=np.arange(size, dtype="int16"))
        xd.attrs["scale_factor"], xd.attrs["add_offset"] = np.array([xs], "float32"), np.array([x_w], "float32")
        yd = f.create_dataset("y", data=np.arange(size, dtype="int16"))
        yd.attrs["scale_factor"], yd.attrs["add_offset"] = np.array([ys], "float32"), np.array([y_n], "float32")
        ad = f.create_dataset("AOD", data=raw)
        ad.attrs["scale_factor"] = np.array([AOD_SCALE], "float32")
        ad.attrs["add_offset"] = np.array([AOD_OFFSET], "float32")
        ad.attrs["_FillValue"] = np.array([AOD_FILL], "uint16")
        f.create_dataset("DQF", data=dqf).attrs["_FillValue"] = np.array([255], "uint8")
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


# -------------------------------------------------------------------- espesor óptico (AODF)


def test_parse_aod_filters_quality_fill_and_window_and_scales_values():
    content = synthetic_aod(
        [
            (-33.1, -71.5, 0.25, 0, False),  # calidad alta
            (-36.6, -72.1, 0.8, 1, False),  # calidad media: se acepta
            (-35.0, -70.0, 0.5, 2, False),  # calidad baja: se descarta
            (-34.0, -71.0, 0.5, 3, False),  # sin dato: se descarta
            (-34.5, -70.5, None, 0, False),  # _FillValue aunque la calidad diga alta
            (-31.0, -69.0, 5.5, 0, False),  # sobre el techo físico
            (-32.0, -70.0, -0.03, 0, False),  # negativo tras el offset
            (-29.0, -67.0, 0.5, 0, False),  # fuera de la ventana
        ]
    )
    cells = smoke.parse_aod(content, AOD_KEY, window=WINDOW)
    assert len(cells) == 2
    by_lat = sorted(cells, key=lambda c: c["lat"])
    assert abs(by_lat[0]["lat"] + 36.6) < 0.08 and by_lat[0]["aod"] == pytest.approx(0.8, abs=1e-3)
    assert abs(by_lat[1]["lat"] + 33.1) < 0.08 and by_lat[1]["aod"] == pytest.approx(0.25, abs=1e-3)
    assert all(c["observed_at"] == "2026-10-19T04:00:20Z" for c in cells)


def test_parse_aod_night_file_is_empty_and_bad_inputs_raise():
    assert smoke.parse_aod(synthetic_aod([]), AOD_KEY, window=WINDOW) == []
    with pytest.raises(goes.GoesError):
        smoke.parse_aod(b"no es un HDF5", AOD_KEY)
    with pytest.raises(goes.GoesError):
        smoke.parse_aod(synthetic_aod([]), "ABI-L2-AODF/2026/292/04/sin-fecha.nc")
    with pytest.raises(goes.GoesError):  # un archivo ADPF no trae el dataset AOD
        smoke.parse_aod(synthetic_adp([]), KEY)


@pytest.mark.parametrize(
    ("aod", "expected"),
    [(0.0, "tenue"), (0.25, "tenue"), (0.39, "tenue"), (0.4, "moderado"), (0.99, "moderado"), (1.0, "denso"), (3.2, "denso"),
     (None, None), (float("nan"), None), (float("inf"), None), (-0.01, None)],
)
def test_classify_density(aod, expected):
    assert smoke.classify_density(aod) == expected


def blob_at(polys: list[dict], lat: float) -> dict:
    """El polígono cuyo centro (promedio de vértices) queda más cerca de `lat`."""
    def center(poly):
        ring = poly["geometry"]["coordinates"][0]
        return sum(pt[1] for pt in ring) / len(ring)

    return min(polys, key=lambda p: abs(center(p) - lat))


def _two_blobs() -> list[dict]:
    adp = synthetic_adp([(-33.1, -71.5, 0, True), (-36.6, -72.1, 0, True), (-34.5, -70.5, 0, True)])
    return smoke.parse_adp(adp, KEY, window=WINDOW)


def test_polygons_without_aod_keep_the_shape_and_leave_density_empty():
    for polys in (smoke.polygons(_two_blobs()), smoke.polygons(_two_blobs(), []), smoke.polygons(_two_blobs(), None)):
        assert len(polys) == 3
        assert all(p["aod_median"] is None and p["aod_p90"] is None and p["density"] is None for p in polys)
        assert all({"observed_at", "geometry", "cells"} <= set(p) for p in polys)


def test_polygons_assign_density_from_the_aod_inside_each_blob():
    aod = smoke.parse_aod(
        synthetic_aod([(-33.1, -71.5, 0.25, 0, True), (-36.6, -72.1, 1.4, 0, True)]), AOD_KEY, window=WINDOW)
    polys = smoke.polygons(_two_blobs(), aod)
    tenue, denso, sin_aod = (blob_at(polys, lat) for lat in (-33.1, -36.6, -34.5))
    assert tenue["density"] == "tenue" and tenue["aod_p90"] == pytest.approx(0.25, abs=0.01)
    assert denso["density"] == "denso" and denso["aod_median"] == pytest.approx(1.4, abs=0.01)
    assert sin_aod["density"] is None and sin_aod["aod_p90"] is None, "sin AOD en la mancha no se inventa un valor"


def test_polygons_only_pair_scans_within_fifteen_minutes():
    near = smoke.parse_aod(
        synthetic_aod([(-33.1, -71.5, 0.25, 0, True)]),
        AOD_KEY.replace("s20262920400208", "s20262920410208"), window=WINDOW)
    far = [dict(c, observed_at="2026-10-19T04:20:20Z") for c in near]
    cells = _two_blobs()
    assert blob_at(smoke.polygons(cells, near), -33.1)["density"] == "tenue"
    assert blob_at(smoke.polygons(cells, far), -33.1)["density"] is None


def test_polygons_uses_only_nearest_aod_scan_not_pooled():
    """Con tres barridos AODF (-10, 0, +10 min), toma solo el más cercano (0 min) sin mezclar."""
    same = smoke.parse_aod(synthetic_aod([(-33.1, -71.5, 1.4, 0, True)]), AOD_KEY, window=WINDOW)
    before = [dict(c, aod=0.2, observed_at="2026-10-19T03:50:20Z") for c in same]
    after = [dict(c, aod=0.2, observed_at="2026-10-19T04:10:20Z") for c in same]
    blob = blob_at(smoke.polygons(_two_blobs(), before + same + after), -33.1)
    assert blob["density"] == "denso"
    assert blob["aod_median"] == pytest.approx(1.4, abs=0.01)


def test_parse_aod_handles_unsigned_netcdf_packed_int16_and_int8():
    """GOES-R PUG empaqueta AOD en int16 y DQF en int8 con `_Unsigned="true"` y `_FillValue=-1`."""
    size = 240
    scale, offset = 7.706e-5, -0.05
    x_w, y_s = goes.latlon_to_scan(PROJ, -40.0, -76.0)
    x_e, y_n = goes.latlon_to_scan(PROJ, -28.0, -66.0)
    xs = (x_e - x_w) / (size - 1)
    ys = -(y_n - y_s) / (size - 1)
    raw_u16 = np.full((size, size), 65535, dtype="uint16")
    dqf_u8 = np.full((size, size), 255, dtype="uint8")

    # Píxel muy denso: AOD=3,0 -> crudo uint16 ~39580 (>32767, negativo visto como int16).
    x1, y1 = goes.latlon_to_scan(PROJ, -33.1, -71.5)
    c1, r1 = int(round((x1 - x_w) / xs)), int(round((y1 - y_n) / ys))
    raw_u16[r1, c1] = int(round((3.0 - offset) / scale))
    dqf_u8[r1, c1] = 0

    # Píxel con AOD=0,8 pero DQF de relleno (-1 en int8 == 255 en uint8): debe descartarse.
    x2, y2 = goes.latlon_to_scan(PROJ, -36.6, -72.1)
    c2, r2 = int(round((x2 - x_w) / xs)), int(round((y2 - y_n) / ys))
    raw_u16[r2, c2] = int(round((0.8 - offset) / scale))
    dqf_u8[r2, c2] = 255

    buf = io.BytesIO()
    with h5py.File(buf, "w") as f:
        gp = f.create_dataset("goes_imager_projection", data=np.int32(0))
        gp.attrs["longitude_of_projection_origin"] = np.array([-75.0])
        gp.attrs["perspective_point_height"] = np.array([35786023.0])
        gp.attrs["semi_major_axis"] = np.array([6378137.0])
        gp.attrs["semi_minor_axis"] = np.array([6356752.31414])
        xd = f.create_dataset("x", data=np.arange(size, dtype="int16"))
        xd.attrs["scale_factor"], xd.attrs["add_offset"] = np.array([xs], "float32"), np.array([x_w], "float32")
        yd = f.create_dataset("y", data=np.arange(size, dtype="int16"))
        yd.attrs["scale_factor"], yd.attrs["add_offset"] = np.array([ys], "float32"), np.array([y_n], "float32")
        ad = f.create_dataset("AOD", data=raw_u16.view("int16"))
        ad.attrs["_Unsigned"] = "true"
        ad.attrs["scale_factor"] = np.array([scale], "float32")
        ad.attrs["add_offset"] = np.array([offset], "float32")
        ad.attrs["_FillValue"] = np.array([-1], "int16")
        qd = f.create_dataset("DQF", data=dqf_u8.view("int8"))
        qd.attrs["_Unsigned"] = "true"
        qd.attrs["_FillValue"] = np.array([-1], "int8")

    cells = smoke.parse_aod(buf.getvalue(), AOD_KEY, window=WINDOW)
    assert len(cells) == 1
    assert cells[0]["aod"] == pytest.approx(3.0, abs=1e-2)
    assert smoke.classify_density(cells[0]["aod"]) == "denso"


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

# -------------------------------------------------------------------- humo con densidad (ADPF + AODF)


def aod_key_for(moment: datetime) -> str:
    return key_for(moment).replace("ADPF", "AODF")


def _is_aodf(r: httpx.Request) -> bool:
    return "ABI-L2-AODF" in (r.url.params.get("prefix", "") + r.url.path)


def aod_sample_file() -> bytes:
    """Mismas manchas que `sample_file`: el parche 3×3 con humo denso y el píxel suelto, tenue."""
    return synthetic_aod([(-33.1, -71.5, 1.4, 0, True), (-36.6, -72.1, 0.25, 1, True)])


@pytest.fixture
def web_adp_aod(web, monkeypatch):
    monkeypatch.setattr(opendata, "_SMOKE_CACHE", {})
    now = datetime.now(timezone.utc)

    def listing(r):
        key = aod_key_for(now) if _is_aodf(r) else key_for(now)
        return _listing(key)

    web.add(lambda r: "list-type" in r.url.params, listing)
    web.add(lambda r: r.url.path.endswith(".nc") and _is_aodf(r), lambda r: httpx.Response(200, content=aod_sample_file()))
    web.add(lambda r: r.url.path.endswith(".nc"), lambda r: httpx.Response(200, content=sample_file()))
    return web


def test_smoke_geojson_reports_density_when_aodf_is_available(make_client, web_adp_aod):
    with make_client() as client:
        response = client.get("/api/opendata/smoke.geojson")
        assert response.status_code == 200
        body = response.json()
    assert body["aod_available"] is True
    assert body["source"] == "NOAA GOES-19 ABI-L2-ADPF + ABI-L2-AODF diurno (dominio público)"
    big = max(body["features"], key=lambda f: f["properties"]["cells"])["properties"]
    small = min(body["features"], key=lambda f: f["properties"]["cells"])["properties"]
    assert big["density"] == "denso" and big["aod_p90"] == pytest.approx(1.4, abs=0.01)
    assert big["aod_median"] == pytest.approx(1.4, abs=0.01) and big["cells"] == 9
    assert small["density"] == "tenue" and small["aod_p90"] == pytest.approx(0.25, abs=0.01)


@pytest.mark.parametrize("failure", ["503", "vacio"])
def test_smoke_geojson_degrades_cleanly_without_aodf(make_client, web, monkeypatch, failure):
    monkeypatch.setattr(opendata, "_SMOKE_CACHE", {})
    now = datetime.now(timezone.utc)
    if failure == "503":
        web.add(lambda r: "list-type" in r.url.params and _is_aodf(r), lambda r: httpx.Response(503))
    else:  # de noche el prefijo existe pero no trae archivos
        web.add(lambda r: "list-type" in r.url.params and _is_aodf(r), lambda r: httpx.Response(200, text="<ListBucketResult></ListBucketResult>"))
    web.add(lambda r: "list-type" in r.url.params, lambda r: _listing(key_for(now)))
    web.add(lambda r: r.url.path.endswith(".nc"), lambda r: httpx.Response(200, content=sample_file()))
    with make_client() as client:
        response = client.get("/api/opendata/smoke.geojson")
        assert response.status_code == 200
        body = response.json()
    assert body["aod_available"] is False and body["source"] == "NOAA GOES-19 ABI-L2-ADPF (dominio público)"
    assert body["count"] == 2
    for feature in body["features"]:
        props = feature["properties"]
        assert props["density"] is None and props["aod_p90"] is None and props["aod_median"] is None


def test_fetch_aod_takes_only_the_latest_files_and_never_raises(web):
    now = datetime.now(timezone.utc)
    keys = [aod_key_for(now - timedelta(minutes=10 * i)) for i in range(5)]
    web.add(lambda r: "list-type" in r.url.params, lambda r: _listing(*keys))
    web.add(lambda r: r.url.path.endswith(".nc"), lambda r: httpx.Response(200, content=aod_sample_file()))

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(web.handler)) as client:
            return await smoke.fetch_aod(client, hours=1, now=now)

    cells = asyncio.run(run())
    downloads = [r for r in web.requests if r.url.path.endswith(".nc")]
    assert len(downloads) == smoke.AOD_MAX_FILES and cells

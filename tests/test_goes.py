import asyncio
import io
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import h5py
import httpx
import numpy as np
import pytest

from backend.providers import _retry, goes

PROJ = goes.Projection(lon0=-75.0, h=35786023.0 + 6378137.0, r_eq=6378137.0, r_pol=6356752.31414)


def test_projection_roundtrip_in_chile():
    for lat, lon in [(-33.05, -71.55), (-18.5, -70.3), (-53.2, -70.9), (-36.6, -72.1)]:
        x, y = goes.latlon_to_scan(PROJ, lat, lon)
        la, lo = goes.scan_to_latlon(PROJ, np.array([x]), np.array([y]))
        assert abs(la[0] - lat) < 1e-6 and abs(lo[0] - lon) < 1e-6


def synthetic_fdc(fires: list[tuple[float, float, int, float]], size: int = 240) -> bytes:
    """FDCF mínimo con la misma estructura que el producto real, cubriendo Chile central."""
    x_w, y_s = goes.latlon_to_scan(PROJ, -40.0, -76.0)
    x_e, y_n = goes.latlon_to_scan(PROJ, -28.0, -66.0)
    xs = (x_e - x_w) / (size - 1)
    ys = -(y_n - y_s) / (size - 1)
    mask = np.full((size, size), 100, dtype="int16")
    power = np.full((size, size), -9.0, dtype="float32")
    temp = np.full((size, size), 65535, dtype="uint16")
    area = np.full((size, size), 65535, dtype="uint16")
    for lat, lon, code, frp in fires:
        x, y = goes.latlon_to_scan(PROJ, lat, lon)
        col, row = int(round((x - x_w) / xs)), int(round((y - y_n) / ys))
        mask[row, col] = code
        power[row, col] = frp
        temp[row, col] = int((900 - 400) / 0.05493667)
    buf = io.BytesIO()
    with h5py.File(buf, "w") as f:
        f.attrs["time_coverage_start"] = np.bytes_(b"2024-02-02T21:00:20.8Z")
        gp = f.create_dataset("goes_imager_projection", data=np.int32(0))
        gp.attrs["longitude_of_projection_origin"] = np.array([-75.0])
        gp.attrs["perspective_point_height"] = np.array([35786023.0])
        gp.attrs["semi_major_axis"] = np.array([6378137.0])
        gp.attrs["semi_minor_axis"] = np.array([6356752.31414])
        xd = f.create_dataset("x", data=np.arange(size, dtype="int16"))
        xd.attrs["scale_factor"], xd.attrs["add_offset"] = np.array([xs], "float32"), np.array([x_w], "float32")
        yd = f.create_dataset("y", data=np.arange(size, dtype="int16"))
        yd.attrs["scale_factor"], yd.attrs["add_offset"] = np.array([ys], "float32"), np.array([y_n], "float32")
        f.create_dataset("Mask", data=mask).attrs["_FillValue"] = np.array([-99], "int16")
        f.create_dataset("Power", data=power).attrs["_FillValue"] = np.array([-9.0], "float32")
        t = f.create_dataset("Temp", data=temp)
        t.attrs["_FillValue"], t.attrs["scale_factor"], t.attrs["add_offset"] = (
            np.array([65535], "uint16"),
            np.array([0.05493667], "float32"),
            np.array([400.0], "float32"),
        )
        a = f.create_dataset("Area", data=area)
        a.attrs["_FillValue"] = np.array([65535], "uint16")
    return buf.getvalue()


def test_parse_synthetic_fdc_extracts_fire_pixels_with_confidence():
    content = synthetic_fdc([(-33.1, -71.5, 10, 812.5), (-36.6, -72.1, 35, 20.0), (-29.0, -67.0, 10, 5.0)])
    points = goes.parse_fdc(content, "G16", window=(-75.0, -38.0, -68.0, -30.0))
    assert len(points) == 2  # el tercero está fuera de la ventana pedida
    by_conf = {p["confidence"]: p for p in points}
    vina = by_conf["alta"]
    assert abs(vina["lat"] + 33.1) < 0.08 and abs(vina["lon"] + 71.5) < 0.08
    assert vina["frp_mw"] == 812.5 and vina["satellite"] == "GOES-16" and vina["observed_at"] == "2024-02-02T21:00:20Z"
    assert abs(vina["brightness_k"] - 900) < 1
    low = by_conf["baja"]
    assert low["temporally_filtered"] is True and "probabilidad baja" in low["confidence_raw"]


# ------------------------------------------------------------- territorio (FUEGO-15)
# La ventana de lectura cubre Argentina, Bolivia, Perú y mar abierto; el recorte
# fino es territorial, igual que en FIRMS.


def test_parse_fdc_descarta_fuego_en_argentina():
    content = synthetic_fdc([(-31.5, -68.0, 10, 50.0)])  # San Juan, Argentina
    assert goes.parse_fdc(content, "G16") == []


def test_parse_fdc_conserva_fuego_chileno_con_su_confianza():
    content = synthetic_fdc([(-35.0, -71.5, 12, 61.0)])  # Hualañé, Maule
    (punto,) = goes.parse_fdc(content, "G19")
    assert punto["confidence"] == "media" and punto["frp_mw"] == 61.0


def test_parse_fdc_descarta_mar_mas_alla_de_la_tolerancia():
    """El mar frente a La Serena queda fuera: con la tolerancia de FIRMS (0.16°) entraría."""
    content = synthetic_fdc([(-29.9, -71.3, 10, 40.0)])
    assert goes.parse_fdc(content, "G16") == []


def test_parse_fdc_conserva_punto_costero_dentro_de_la_tolerancia():
    content = synthetic_fdc([(-32.93, -71.52, 13, 30.0)])  # Concón, borde costero
    (punto,) = goes.parse_fdc(content, "G16")
    assert punto["confidence"] == "alta"


def test_parse_fdc_barrido_mixto_deja_solo_los_chilenos():
    content = synthetic_fdc(
        [
            (-35.0, -71.5, 10, 61.0),  # Hualañé, Chile
            (-31.5, -68.0, 10, 50.0),  # San Juan, Argentina
            (-32.89, -68.84, 11, 40.0),  # Mendoza, Argentina
            (-34.6, -68.3, 12, 30.0),  # San Rafael, Argentina
        ]
    )
    puntos = goes.parse_fdc(content, "G16")
    assert len(puntos) == 1
    assert abs(puntos[0]["lat"] + 35.0) < 0.08 and abs(puntos[0]["lon"] + 71.5) < 0.08


def test_invalid_file_raises():
    with pytest.raises(goes.GoesError):
        goes.parse_fdc(b"not a netcdf", "G19")


def test_key_start_parses_s3_names():
    key = "ABI-L2-FDCF/2024/033/21/OR_ABI-L2-FDCF-M6_G16_s20240332100208_e20240332109516_c20240332113362.nc"
    moment = goes.key_start(key)
    assert moment.isoformat() == "2024-02-02T21:00:20+00:00"


# -------------------------------------------------------------------- reintentos de red

HOUR = datetime(2024, 2, 2, 21, tzinfo=timezone.utc)
KEY = "ABI-L2-FDCF/2024/033/21/OR_ABI-L2-FDCF-M6_G16_s20240332100208_e20240332109516_c20240332113362.nc"


def _listing(*keys: str) -> httpx.Response:
    body = "".join(f"<Contents><Key>{k}</Key></Contents>" for k in keys)
    return httpx.Response(200, text=f"<ListBucketResult>{body}</ListBucketResult>")


@pytest.fixture
def fast_retries(monkeypatch):
    """Sin esperas reales entre intentos: se verifica el conteo, no el reloj."""
    monkeypatch.setattr(_retry, "RETRY_DELAYS", (0, 0))


def test_list_keys_retries_transient_500s_then_succeeds(web, fast_retries):
    answers = iter([httpx.Response(500), httpx.Response(500), _listing(KEY)])
    web.add(lambda r: True, lambda r: next(answers))

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(web.handler)) as client:
            return await goes.list_keys(client, "G16", HOUR)

    assert asyncio.run(run()) == [KEY]
    assert len(web.requests) == 3


def test_download_retries_a_transient_500(web, fast_retries):
    answers = iter([httpx.Response(500), httpx.Response(200, content=b"contenido nc")])
    web.add(lambda r: True, lambda r: next(answers))

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(web.handler)) as client:
            return await goes.download(client, "G16", KEY)

    assert asyncio.run(run()) == b"contenido nc"
    assert len(web.requests) == 2


def test_a_404_is_not_retried(web, fast_retries):
    web.add(lambda r: True, lambda r: httpx.Response(404))

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(web.handler)) as client:
            await goes.download(client, "G16", KEY)

    with pytest.raises(goes.GoesError, match=r"tras 1 intento\)"):
        asyncio.run(run())
    assert len(web.requests) == 1


def test_three_500s_raise_mentioning_three_attempts(web, fast_retries):
    web.add(lambda r: True, lambda r: httpx.Response(500))

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(web.handler)) as client:
            await goes.list_keys(client, "G16", HOUR)

    with pytest.raises(goes.GoesError, match="tras 3 intentos"):
        asyncio.run(run())
    assert len(web.requests) == 3


# ---------------------------------------------------- respaldo al barrido anterior

PREV_KEY = "ABI-L2-FDCF/2024/033/20/OR_ABI-L2-FDCF-M6_G16_s20240332050208_e20240332059516_c20240332063362.nc"


def _stub_s3(monkeypatch, keys_by_hour, parsed):
    """list_keys/download/parse_fdc falsos: devuelve la lista de claves descargadas."""
    downloaded = []

    async def fake_list(client, satellite, hour):
        return keys_by_hour.get(hour, [])

    async def fake_download(client, satellite, key):
        downloaded.append(key)
        return key.encode()

    def fake_parse(content, satellite, window=goes.READ_WINDOW):
        result = parsed[content.decode()]
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(goes, "list_keys", fake_list)
    monkeypatch.setattr(goes, "download", fake_download)
    monkeypatch.setattr(goes, "parse_fdc", fake_parse)
    return downloaded


def test_fetch_latest_uses_previous_scan_when_newest_is_empty(monkeypatch):
    downloaded = _stub_s3(
        monkeypatch,
        {HOUR: [KEY], HOUR - timedelta(hours=1): [PREV_KEY]},
        {KEY: [], PREV_KEY: [{"lat": -33.1}, {"lat": -36.6}]},
    )
    key, points = asyncio.run(goes.fetch_latest(None, HOUR))
    assert key == PREV_KEY and len(points) == 2
    assert downloaded == [KEY, PREV_KEY]


def test_fetch_latest_uses_previous_scan_when_newest_is_corrupt(monkeypatch):
    prev_hour = HOUR - timedelta(hours=1)
    _stub_s3(
        monkeypatch,
        {HOUR: [KEY], prev_hour: [PREV_KEY]},
        {KEY: goes.GoesError("archivo truncado"), PREV_KEY: [{"lat": -33.1}]},
    )
    key, points = asyncio.run(goes.fetch_latest(None, HOUR))
    assert key == PREV_KEY and len(points) == 1


def test_fetch_latest_returns_none_when_all_scans_are_empty(monkeypatch):
    prev_hour = HOUR - timedelta(hours=1)
    downloaded = _stub_s3(monkeypatch, {HOUR: [KEY], prev_hour: [PREV_KEY]}, {KEY: [], PREV_KEY: []})
    assert asyncio.run(goes.fetch_latest(None, HOUR)) == (None, [])
    assert downloaded == [KEY, PREV_KEY]


def test_fetch_latest_does_not_download_the_same_key_twice(monkeypatch):
    downloaded = _stub_s3(monkeypatch, {HOUR: [KEY], HOUR - timedelta(hours=1): [KEY]}, {KEY: []})
    assert asyncio.run(goes.fetch_latest(None, HOUR)) == (None, [])
    assert downloaded == [KEY]


REAL_FILE = os.getenv("BRASA_GOES_SAMPLE")


@pytest.mark.skipif(not REAL_FILE or not Path(REAL_FILE).exists(), reason="Define BRASA_GOES_SAMPLE con un FDCF real")
def test_real_goes16_file_viña_2024():
    """Con el barrido real GOES-16 del 2024-02-02 21:00 UTC: debe haber fuego en Viña del Mar/Quilpué."""
    points = goes.parse_fdc(Path(REAL_FILE).read_bytes(), "G16")
    near = [p for p in points if -33.25 < p["lat"] < -32.95 and -71.75 < p["lon"] < -71.2]
    assert len(near) >= 10
    assert max(p["frp_mw"] or 0 for p in near) > 1000

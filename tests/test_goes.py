import io
import os
from pathlib import Path

import h5py
import numpy as np
import pytest

from backend.providers import goes

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
        t.attrs["_FillValue"], t.attrs["scale_factor"], t.attrs["add_offset"] = np.array([65535], "uint16"), np.array([0.05493667], "float32"), np.array([400.0], "float32")
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


def test_invalid_file_raises():
    with pytest.raises(goes.GoesError):
        goes.parse_fdc(b"not a netcdf", "G19")


def test_key_start_parses_s3_names():
    key = "ABI-L2-FDCF/2024/033/21/OR_ABI-L2-FDCF-M6_G16_s20240332100208_e20240332109516_c20240332113362.nc"
    moment = goes.key_start(key)
    assert moment.isoformat() == "2024-02-02T21:00:20+00:00"


REAL_FILE = os.getenv("BRASA_GOES_SAMPLE")


@pytest.mark.skipif(not REAL_FILE or not Path(REAL_FILE).exists(), reason="Define BRASA_GOES_SAMPLE con un FDCF real")
def test_real_goes16_file_viña_2024():
    """Con el barrido real GOES-16 del 2024-02-02 21:00 UTC: debe haber fuego en Viña del Mar/Quilpué."""
    points = goes.parse_fdc(Path(REAL_FILE).read_bytes(), "G16")
    near = [p for p in points if -33.25 < p["lat"] < -32.95 and -71.75 < p["lon"] < -71.2]
    assert len(near) >= 10
    assert max(p["frp_mw"] or 0 for p in near) > 1000

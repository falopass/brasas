"""Genera `glm_lcfa_sample.nc`: un LCFA mínimo con los nombres de dataset del producto real.

Cuatro destellos con valores conocidos: dos buenos dentro de la ventana de lectura
(Viña del Mar y Concepción), uno bueno fuera de ella y uno con `flash_quality_flag` 1,
para que `tests/test_glm.py` compruebe los filtros sin red. Se regenera con:

    .venv/bin/python tests/data/build_glm_sample.py
"""
from pathlib import Path

import h5py
import numpy as np

OUT = Path(__file__).with_name("glm_lcfa_sample.nc")

# (lat, lon, offset_s, flag, energy_j, area_km2)
FLASHES = [
    (-33.05, -71.55, 12.5, 0, 520.0, 48.0),   # Viña del Mar: bueno, dentro
    (-36.60, -72.10, 30.0, 0, 310.0, 30.0),   # Concepción: bueno, dentro
    (-10.00, -50.00, 15.0, 0, 100.0, 10.0),   # bueno pero fuera de la ventana de Chile
    (-33.00, -72.00, 45.0, 1, 900.0, 80.0),   # dentro pero con calidad degradada
]

LAT_SCALE, LON_SCALE, OFFSET_SCALE, AREA_SCALE = 0.005, 0.005, 0.1, 0.1


def main() -> None:
    lats = [r[0] for r in FLASHES]
    lons = [r[1] for r in FLASHES]
    with h5py.File(OUT, "w") as f:
        f.attrs["time_coverage_start"] = np.bytes_(b"2025-10-18T15:00:00.0Z")
        lat = f.create_dataset("flash_lat", data=np.array([v / LAT_SCALE for v in lats], "int16"))
        lat.attrs["scale_factor"] = np.array([LAT_SCALE], "float32")
        lat.attrs["_FillValue"] = np.array([-32768], "int16")
        lon = f.create_dataset("flash_lon", data=np.array([v / LON_SCALE for v in lons], "int16"))
        lon.attrs["scale_factor"] = np.array([LON_SCALE], "float32")
        lon.attrs["_FillValue"] = np.array([-32768], "int16")
        off = f.create_dataset("flash_time_offset_of_first_event",
                               data=np.array([r[2] / OFFSET_SCALE for r in FLASHES], "int16"))
        off.attrs["scale_factor"] = np.array([OFFSET_SCALE], "float32")
        off.attrs["_FillValue"] = np.array([-1], "int16")
        f.create_dataset("flash_quality_flag", data=np.array([r[3] for r in FLASHES], "int16"))
        f.create_dataset("flash_energy", data=np.array([r[4] for r in FLASHES], "float32"))
        area = f.create_dataset("flash_area", data=np.array([r[5] / AREA_SCALE for r in FLASHES], "int16"))
        area.attrs["scale_factor"] = np.array([AREA_SCALE], "float32")
    print(f"Escrito {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()

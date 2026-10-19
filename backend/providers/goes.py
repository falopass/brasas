"""Detecciones de fuego GOES-R ABI L2 FDC (Fire/Hot Spot Characterization), disco completo.

GOES-Este observa Chile cada 10 minutos. Los archivos son públicos en AWS Open Data:
- noaa-goes19: GOES-19, GOES-Este operacional desde abril de 2025.
- noaa-goes16: GOES-16, GOES-Este entre 2017 y abril de 2025 (archivo histórico).

Resolución nominal ~2 km en el nadir; en Chile central el píxel es mayor (~3-4 km).
Una detección GOES es un píxel caliente, no un incendio confirmado ni su ubicación exacta.
"""
from __future__ import annotations

import io
import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import numpy as np

from backend.providers import _retry

S3_BUCKETS = {"G16": "noaa-goes16", "G19": "noaa-goes19"}
PRODUCT = "ABI-L2-FDCF"
GOES19_OPERATIONAL_FROM = datetime(2025, 4, 7, tzinfo=timezone.utc)
# Ventana de lectura (west, south, east, north): Chile continental, Juan Fernández y margen.
READ_WINDOW = (-81.5, -56.5, -66.0, -17.0)

# Códigos de la máscara FDC (GOES-R PUG vol. 5). 30-35 son los mismos con filtro temporal.
MASK_CONFIDENCE = {
    10: "alta", 11: "alta", 12: "media", 13: "alta", 14: "media", 15: "baja",
    30: "alta", 31: "alta", 32: "media", 33: "alta", 34: "media", 35: "baja",
}
MASK_LABELS = {
    10: "fuego (buena calidad)", 11: "fuego saturado", 12: "fuego con nubes",
    13: "probabilidad alta", 14: "probabilidad media", 15: "probabilidad baja",
}


class GoesError(Exception):
    pass


@dataclass(frozen=True)
class Projection:
    lon0: float
    h: float  # distancia del satélite al centro de la Tierra (m)
    r_eq: float
    r_pol: float

    @property
    def e2(self) -> float:
        return 1 - (self.r_pol ** 2) / (self.r_eq ** 2)


def latlon_to_scan(proj: Projection, lat: float, lon: float) -> tuple[float, float]:
    """Latitud/longitud (grados) → ángulos de escaneo x, y (radianes)."""
    phi, lam = math.radians(lat), math.radians(lon)
    lam0 = math.radians(proj.lon0)
    phi_c = math.atan((proj.r_pol ** 2 / proj.r_eq ** 2) * math.tan(phi))
    r_c = proj.r_pol / math.sqrt(1 - proj.e2 * math.cos(phi_c) ** 2)
    sx = proj.h - r_c * math.cos(phi_c) * math.cos(lam - lam0)
    sy = -r_c * math.cos(phi_c) * math.sin(lam - lam0)
    sz = r_c * math.sin(phi_c)
    y = math.atan(sz / sx)
    x = math.asin(-sy / math.sqrt(sx * sx + sy * sy + sz * sz))
    return x, y


def scan_to_latlon(proj: Projection, x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Ángulos de escaneo x, y (radianes) → latitud/longitud (grados). Vectorizado."""
    cos_x, sin_x, cos_y, sin_y = np.cos(x), np.sin(x), np.cos(y), np.sin(y)
    ratio = proj.r_eq ** 2 / proj.r_pol ** 2
    a = sin_x ** 2 + cos_x ** 2 * (cos_y ** 2 + ratio * sin_y ** 2)
    b = -2 * proj.h * cos_x * cos_y
    c = proj.h ** 2 - proj.r_eq ** 2
    disc = b * b - 4 * a * c
    with np.errstate(invalid="ignore"):
        r_s = (-b - np.sqrt(disc)) / (2 * a)
    s_x = r_s * cos_x * cos_y
    s_y = -r_s * sin_x
    s_z = r_s * cos_x * sin_y
    lat = np.degrees(np.arctan(ratio * s_z / np.sqrt((proj.h - s_x) ** 2 + s_y ** 2)))
    lon = proj.lon0 - np.degrees(np.arctan(s_y / (proj.h - s_x)))
    return lat, lon


def _attr(ds, name: str, default: float = 1.0) -> float:
    value = ds.attrs.get(name)
    if value is None:
        return default
    return float(np.asarray(value).ravel()[0])


def _scaled(ds, rows: slice, cols: slice) -> np.ndarray:
    raw = ds[rows, cols]
    fill = ds.attrs.get("_FillValue")
    out = raw.astype("float64") * _attr(ds, "scale_factor") + _attr(ds, "add_offset", 0.0)
    if fill is not None:
        out[raw == np.asarray(fill).ravel()[0]] = np.nan
    return out


def parse_fdc(content: bytes, satellite: str, window: tuple[float, float, float, float] = READ_WINDOW) -> list[dict[str, Any]]:
    """Extrae los píxeles de fuego de un archivo FDCF dentro de `window` (west, south, east, north)."""
    import h5py

    try:
        f = h5py.File(io.BytesIO(content), "r")
    except OSError as exc:
        raise GoesError("El archivo GOES no es un NetCDF4/HDF5 válido.") from exc
    with f:
        gp = f["goes_imager_projection"].attrs
        proj = Projection(
            lon0=float(np.asarray(gp["longitude_of_projection_origin"]).ravel()[0]),
            h=float(np.asarray(gp["perspective_point_height"]).ravel()[0]) + float(np.asarray(gp["semi_major_axis"]).ravel()[0]),
            r_eq=float(np.asarray(gp["semi_major_axis"]).ravel()[0]),
            r_pol=float(np.asarray(gp["semi_minor_axis"]).ravel()[0]),
        )
        x_ds, y_ds = f["x"], f["y"]
        xs, xo = _attr(x_ds, "scale_factor"), _attr(x_ds, "add_offset", 0.0)
        ys, yo = _attr(y_ds, "scale_factor"), _attr(y_ds, "add_offset", 0.0)
        n_rows, n_cols = f["Mask"].shape
        west, south, east, north = window
        corners = [latlon_to_scan(proj, lat, lon) for lat in (south, north) for lon in (west, east)]
        cols_f = [(cx - xo) / xs for cx, _ in corners]
        rows_f = [(cy - yo) / ys for _, cy in corners]
        r0, r1 = max(0, int(min(rows_f)) - 2), min(n_rows, int(max(rows_f)) + 3)
        c0, c1 = max(0, int(min(cols_f)) - 2), min(n_cols, int(max(cols_f)) + 3)
        rows, cols = slice(r0, r1), slice(c0, c1)
        mask = f["Mask"][rows, cols]
        fire = np.isin(mask, list(MASK_CONFIDENCE))
        if not fire.any():
            return []
        rr, cc = np.nonzero(fire)
        x = (cc + c0).astype("float64") * xs + xo
        y = (rr + r0).astype("float64") * ys + yo
        lat, lon = scan_to_latlon(proj, x, y)
        power = _scaled(f["Power"], rows, cols)[rr, cc] if "Power" in f else np.full(len(rr), np.nan)
        temp = _scaled(f["Temp"], rows, cols)[rr, cc] if "Temp" in f else np.full(len(rr), np.nan)
        area = _scaled(f["Area"], rows, cols)[rr, cc] if "Area" in f else np.full(len(rr), np.nan)
        start = f.attrs.get("time_coverage_start")
        start = start.decode() if isinstance(start, bytes) else str(start)
    observed = datetime.strptime(start[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    stamp = observed.strftime("%Y-%m-%dT%H:%M:%SZ")
    product = f"GOES{satellite[1:]}_FDCF"
    result = []
    for i in range(len(rr)):
        la, lo = float(lat[i]), float(lon[i])
        if not (math.isfinite(la) and math.isfinite(lo) and west <= lo <= east and south <= la <= north):
            continue
        code = int(mask[rr[i], cc[i]])
        frp = float(power[i]) if math.isfinite(power[i]) else None
        result.append({
            "id": f"{product}:{observed:%Y%m%d%H%M}:{int(rr[i]) + r0}:{int(cc[i]) + c0}",
            "source": product, "sensor": "ABI", "satellite": f"GOES-{satellite[1:]}", "resolution_m": 2000,
            "lat": round(la, 5), "lon": round(lo, 5), "observed_at": stamp, "date": observed.date().isoformat(),
            "frp_mw": round(frp, 1) if frp is not None else None,
            "brightness_k": round(float(temp[i]), 1) if math.isfinite(temp[i]) else None,
            "fire_area_m2": round(float(area[i])) if math.isfinite(area[i]) else None,
            "confidence": MASK_CONFIDENCE[code],
            "confidence_raw": f"{code} · {MASK_LABELS[code - 20 if code >= 30 else code]}",
            "temporally_filtered": code >= 30,
        })
    return result


_KEY_RE = re.compile(r"<Key>([^<]+)</Key>")
_START_RE = re.compile(r"_s(\d{4})(\d{3})(\d{2})(\d{2})(\d{2})")


def satellite_for(moment: datetime) -> str:
    return "G19" if moment >= GOES19_OPERATIONAL_FROM else "G16"


def key_start(key: str) -> datetime | None:
    m = _START_RE.search(key)
    if not m:
        return None
    year, doy, hh, mm, ss = (int(g) for g in m.groups())
    return datetime(year, 1, 1, hh, mm, ss, tzinfo=timezone.utc) + timedelta(days=doy - 1)


async def list_keys(client: httpx.AsyncClient, satellite: str, hour: datetime) -> list[str]:
    prefix = f"{PRODUCT}/{hour:%Y}/{hour.timetuple().tm_yday:03d}/{hour:%H}/"
    url = f"https://{S3_BUCKETS[satellite]}.s3.amazonaws.com/"
    try:
        response = await _retry.get(client, url, params={"list-type": "2", "prefix": prefix})
    except _retry.Failure as exc:
        raise GoesError(f"No fue posible listar GOES ({exc.detail}).") from exc.cause
    return sorted(_KEY_RE.findall(response.text))


async def download(client: httpx.AsyncClient, satellite: str, key: str) -> bytes:
    try:
        response = await _retry.get(client, f"https://{S3_BUCKETS[satellite]}.s3.amazonaws.com/{key}")
    except _retry.Failure as exc:
        raise GoesError(f"No fue posible descargar GOES ({exc.detail}).") from exc.cause
    return response.content


async def latest_scan(client: httpx.AsyncClient, now: datetime | None = None) -> tuple[str, str] | None:
    """Clave S3 del barrido de disco completo más reciente (busca en la hora actual y la anterior)."""
    now = now or datetime.now(timezone.utc)
    satellite = satellite_for(now)
    for hour in (now, now - timedelta(hours=1)):
        keys = await list_keys(client, satellite, hour)
        if keys:
            return satellite, keys[-1]
    return None


async def fetch_latest(client: httpx.AsyncClient, now: datetime | None = None) -> tuple[str | None, list[dict[str, Any]]]:
    found = await latest_scan(client, now)
    if not found:
        return None, []
    satellite, key = found
    return key, parse_fdc(await download(client, satellite, key), satellite)

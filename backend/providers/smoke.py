"""Humo visto por GOES-19: máscara del producto de aerosoles ABI-L2-ADPF (disco completo).

Vive en el mismo bucket público `noaa-goes19` que el producto de fuego y sale cada ~10 minutos
(~1 MB por archivo). Es la respuesta satelital a «¿hacia dónde va el humo?»: una detección de
aerosol, no un incendio confirmado ni su trayectoria.

Estructura real del archivo (verificada el 19-oct-2026 con OR_ABI-L2-ADPF-M6_G19_s20262920450211):
- `Smoke` (int8, 5424×5424): 0 ausente / 1 presente, `_FillValue` -128.
- `Dust`, `Cloud`, `SnowIce` (int8): mismas banderas binarias para otros aerosoles y nube.
- `DQF` (uint16): calidad bit a bit; los bits 2-3 son la detección de humo
  (0 alta confianza, 4 media, 8 baja, 12 malo/faltante). El `_FillValue` 65535 cae solo en 12.
- `x`, `y` (int16) + `goes_imager_projection`: misma grilla de escaneo que el FDCF de fuego.
- `time_coverage_start` (atributo de archivo): instante del barrido; se usa el del nombre (`_s`),
  como hace GLM, porque también ordena los archivos en el bucket.

De noche la detección de humo no corre (necesita canales visibles): el archivo existe pero
queda sin píxeles válidos y el conjunto responde vacío, que es la verdad operacional.
"""
from __future__ import annotations

import asyncio
import io
import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import numpy as np

from backend.providers import goes

log = logging.getLogger("brasa.smoke")

PRODUCT = "ABI-L2-ADPF"
# Una hora de ADPF son ~6 archivos; se descargan de a tandas acotadas.
MAX_PARALLEL = 8
# Bits 2-3 del DQF = calidad de la detección de humo; 12 (0b1100) es «malo o faltante».
SMOKE_QF_BAD = 0b1100
# Tolerancia del `simplify` en grados (~1 km): suaviza los bordes de píxel sin mover la pluma.
SIMPLIFY_DEG = 0.01
# Precisión de las coordenadas publicadas (~11 m), como el `round(…, 4)` de los puntos.
PRECISION_DEG = 1e-4


async def list_keys(client: httpx.AsyncClient, satellite: str, hour: datetime) -> list[str]:
    """Mismo listado `list-type=2` que `goes.list_keys`, con el prefijo del producto ADPF."""
    prefix = f"{PRODUCT}/{hour:%Y}/{hour.timetuple().tm_yday:03d}/{hour:%H}/"
    url = f"https://{goes.S3_BUCKETS[satellite]}.s3.amazonaws.com/"
    try:
        response = await client.get(url, params={"list-type": "2", "prefix": prefix})
        response.raise_for_status()
    except (httpx.RequestError, httpx.HTTPStatusError) as exc:
        raise goes.GoesError(f"No fue posible listar ADPF ({type(exc).__name__}).") from exc
    return sorted(goes._KEY_RE.findall(response.text))


async def download(client: httpx.AsyncClient, satellite: str, key: str) -> bytes:
    try:
        response = await client.get(f"https://{goes.S3_BUCKETS[satellite]}.s3.amazonaws.com/{key}")
        response.raise_for_status()
    except (httpx.RequestError, httpx.HTTPStatusError) as exc:
        raise goes.GoesError(f"No fue posible descargar ADPF ({type(exc).__name__}).") from exc
    return response.content


def parse_adp(content: bytes, key: str,
              window: tuple[float, float, float, float] = goes.READ_WINDOW) -> list[dict[str, Any]]:
    """Celdas con humo de un archivo ADPF dentro de `window` (west, south, east, north).

    Cada celda lleva su centro (`lat`, `lon`) y su caja (`min_*`/`max_*`), ya proyectada a
    lat/lon desde la grilla de escaneo, para que el agrupado no vuelva a calcular la geometría.
    Se aceptan las confianzas alta, media y baja; se descarta solo el dato malo o faltante.
    """
    import h5py

    base = goes.key_start(key)
    if base is None:
        raise goes.GoesError(f"El nombre del archivo ADPF no trae fecha legible: {key}")
    try:
        f = h5py.File(io.BytesIO(content), "r")
    except OSError as exc:
        raise goes.GoesError("El archivo ADPF no es un NetCDF4/HDF5 válido.") from exc
    with f:
        gp = f["goes_imager_projection"].attrs
        proj = goes.Projection(
            lon0=float(np.asarray(gp["longitude_of_projection_origin"]).ravel()[0]),
            h=float(np.asarray(gp["perspective_point_height"]).ravel()[0])
              + float(np.asarray(gp["semi_major_axis"]).ravel()[0]),
            r_eq=float(np.asarray(gp["semi_major_axis"]).ravel()[0]),
            r_pol=float(np.asarray(gp["semi_minor_axis"]).ravel()[0]),
        )
        x_ds, y_ds = f["x"], f["y"]
        xs, xo = goes._attr(x_ds, "scale_factor"), goes._attr(x_ds, "add_offset", 0.0)
        ys, yo = goes._attr(y_ds, "scale_factor"), goes._attr(y_ds, "add_offset", 0.0)
        n_rows, n_cols = f["Smoke"].shape
        west, south, east, north = window
        corners = [goes.latlon_to_scan(proj, lat, lon) for lat in (south, north) for lon in (west, east)]
        cols_f = [(cx - xo) / xs for cx, _ in corners]
        rows_f = [(cy - yo) / ys for _, cy in corners]
        r0, r1 = max(0, int(min(rows_f)) - 2), min(n_rows, int(max(rows_f)) + 3)
        c0, c1 = max(0, int(min(cols_f)) - 2), min(n_cols, int(max(cols_f)) + 3)
        rows, cols = slice(r0, r1), slice(c0, c1)
        smoke = np.asarray(f["Smoke"][rows, cols])
        detected = smoke == 1
        if "DQF" in f:
            detected &= (np.asarray(f["DQF"][rows, cols]) & SMOKE_QF_BAD) != SMOKE_QF_BAD
        if not detected.any():
            return []
        rr, cc = np.nonzero(detected)
        x = (cc + c0).astype("float64") * xs + xo
        y = (rr + r0).astype("float64") * ys + yo
        lat, lon = goes.scan_to_latlon(proj, x, y)
        # Caja del píxel: las cuatro esquinas proyectadas (la grilla no es exactamente
        # axis-aligned en lat/lon). dx/dy son el medio paso de escaneo.
        hx, hy = abs(xs) / 2, abs(ys) / 2
        corners_ll = [goes.scan_to_latlon(proj, x + dx, y + dy)
                      for dx in (-hx, hx) for dy in (-hy, hy)]
        min_lat = np.minimum.reduce([c[0] for c in corners_ll])
        max_lat = np.maximum.reduce([c[0] for c in corners_ll])
        min_lon = np.minimum.reduce([c[1] for c in corners_ll])
        max_lon = np.maximum.reduce([c[1] for c in corners_ll])
    stamp = base.strftime("%Y-%m-%dT%H:%M:%SZ")
    cells = []
    for i in range(len(rr)):
        la, lo = float(lat[i]), float(lon[i])
        bounds = (float(min_lat[i]), float(max_lat[i]), float(min_lon[i]), float(max_lon[i]))
        if not (math.isfinite(la) and math.isfinite(lo) and all(map(math.isfinite, bounds))
                and west <= lo <= east and south <= la <= north):
            continue
        cells.append({
            "lat": round(la, 5), "lon": round(lo, 5),
            "min_lat": float(min_lat[i]), "max_lat": float(max_lat[i]),
            "min_lon": float(min_lon[i]), "max_lon": float(max_lon[i]),
            "observed_at": stamp,
        })
    return cells


def polygons(cells: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Celdas → un polígono por mancha contigua de humo, agrupada por instante del barrido.

    Une las cajas de los píxeles con `unary_union`, suaviza el borde escalonado con
    `simplify` y reparte el resultado en polígonos separados. `cells` cuenta los píxeles
    cuyo centro cayó dentro de cada polígono.
    """
    import shapely
    from shapely.geometry import box, mapping
    from shapely.ops import unary_union

    by_scan: dict[str, list[dict[str, Any]]] = {}
    for cell in cells:
        by_scan.setdefault(cell["observed_at"], []).append(cell)
    out = []
    for observed_at, group in sorted(by_scan.items()):
        boxes = [box(c["min_lon"], c["min_lat"], c["max_lon"], c["max_lat"]) for c in group]
        merged = shapely.set_precision(
            unary_union(boxes).simplify(SIMPLIFY_DEG, preserve_topology=True), PRECISION_DEG)
        parts = [g for g in getattr(merged, "geoms", [merged]) if g.geom_type == "Polygon" and not g.is_empty]
        lons = np.array([c["lon"] for c in group])
        lats = np.array([c["lat"] for c in group])
        for part in parts:
            out.append({"observed_at": observed_at, "geometry": mapping(part),
                        "cells": int(shapely.contains_xy(part, lons, lats).sum())})
    return out


async def fetch_smoke(client: httpx.AsyncClient, hours: int = 1,
                      now: datetime | None = None) -> list[dict[str, Any]]:
    """Celdas de humo de los archivos ADPF de las últimas `hours` horas.

    Lista los prefijos horarios que la ventana toca, descarta los archivos anteriores a
    `since` o sin fecha en el nombre, y descarga el resto en tandas acotadas. Un archivo
    que no se pueda leer se registra y se descarta: solo se propaga el error cuando
    ninguna clave de la ventana resultó legible. Sin archivos recientes (satélite
    atrasado o bucket vacío) también falla, para que la ruta responda 503 y no un
    conjunto vacío indistinguible de «no hay humo».
    """
    now = now or datetime.now(timezone.utc)
    satellite = goes.satellite_for(now)
    since = now - timedelta(hours=hours)
    listed = await asyncio.gather(
        *(list_keys(client, satellite, now - timedelta(hours=h)) for h in range(hours + 1)))
    keys = sorted({k for keys in listed for k in keys
                   if (start := goes.key_start(k)) is not None and start >= since})
    if not keys:
        raise goes.GoesError("No hay archivos ABI-L2-ADPF recientes en el bucket.")
    sem = asyncio.Semaphore(MAX_PARALLEL)
    errors: list[Exception] = []

    async def one(key: str) -> list[dict[str, Any]] | None:
        try:
            async with sem:
                content = await download(client, satellite, key)
            return await asyncio.to_thread(parse_adp, content, key)
        except Exception as exc:
            log.warning("Se descarta el archivo ADPF %s: %r", key, exc)
            errors.append(exc)
            return None

    chunks = await asyncio.gather(*(one(k) for k in keys))
    if all(chunk is None for chunk in chunks):
        raise errors[0]
    cells: list[dict[str, Any]] = []
    for chunk in chunks:
        cells.extend(chunk or [])
    return cells

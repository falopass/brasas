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

Densidad del humo: el producto `ABI-L2-AODF` (mismo bucket y misma grilla de 2 km) entrega el
espesor óptico de aerosoles a 550 nm (`AOD`, adimensional, `int16` con `_Unsigned="true"` en
NetCDF4/HDF5) con su calidad `DQF` (`int8` con `_Unsigned="true"`: 0 alta, 1 media, 2 baja,
3 sin dato, 255 relleno). También es diurno y es mejor esfuerzo: si falta, el humo se publica
igual, sin densidad (`None`), nunca con un valor inventado.
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

from backend.geo import territory
from backend.providers import goes

log = logging.getLogger("brasa.smoke")

PRODUCT = "ABI-L2-ADPF"
AOD_PRODUCT = "ABI-L2-AODF"
# `DQF` de AODF: 0 alta, 1 media, 2 baja, 3 sin dato. Solo se aceptan calidad alta y media.
AOD_DQF_MAX = 1
# Espesor óptico de aerosoles a 550 nm (adimensional) para clasificar la mancha por su p90.
AOD_DENSE_MIN = 1.0
AOD_MODERATE_MIN = 0.4
# Más allá de 5 el producto ya es artefacto (nube o reflejo), no humo medible.
AOD_MAX = 5.0
# ADPF y AODF no salen en el mismo instante: se aparean barridos a menos de 15 min.
AOD_MATCH_S = 15 * 60
# Archivos AODF que se bajan como máximo: acota latencia y memoria en el contenedor.
AOD_MAX_FILES = 3
# Una hora de ADPF son ~6 archivos; se descargan de a tandas acotadas.
MAX_PARALLEL = 8
# Bits 2-3 del DQF = calidad de la detección de humo; 12 (0b1100) es «malo o faltante».
SMOKE_QF_BAD = 0b1100
# Tolerancia del `simplify` en grados (~1 km): suaviza los bordes de píxel sin mover la pluma.
SIMPLIFY_DEG = 0.01
# Precisión de las coordenadas publicadas (~11 m), como el `round(…, 4)` de los puntos.
PRECISION_DEG = 1e-4


async def list_keys(client: httpx.AsyncClient, satellite: str, hour: datetime,
                    product: str = PRODUCT) -> list[str]:
    """Mismo listado `list-type=2` que `goes.list_keys`, con el prefijo del producto pedido."""
    prefix = f"{product}/{hour:%Y}/{hour.timetuple().tm_yday:03d}/{hour:%H}/"
    url = f"https://{goes.S3_BUCKETS[satellite]}.s3.amazonaws.com/"
    try:
        response = await client.get(url, params={"list-type": "2", "prefix": prefix})
        response.raise_for_status()
    except (httpx.RequestError, httpx.HTTPStatusError) as exc:
        raise goes.GoesError(f"No fue posible listar {product} ({type(exc).__name__}).") from exc
    return sorted(goes._KEY_RE.findall(response.text))


async def download(client: httpx.AsyncClient, satellite: str, key: str) -> bytes:
    try:
        response = await client.get(f"https://{goes.S3_BUCKETS[satellite]}.s3.amazonaws.com/{key}")
        response.raise_for_status()
    except (httpx.RequestError, httpx.HTTPStatusError) as exc:
        raise goes.GoesError(f"No fue posible descargar ADPF ({type(exc).__name__}).") from exc
    return response.content


def _scan_window(f, variable: str, window: tuple[float, float, float, float]):
    """Proyección GOES y recorte (filas, columnas) de la grilla que cubre `window`.

    Devuelve (proj, xs, xo, ys, yo, rows, cols). Leer solo el recorte evita cargar los
    5424×5424 píxeles del disco completo.
    """
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
    n_rows, n_cols = f[variable].shape
    west, south, east, north = window
    corners = [goes.latlon_to_scan(proj, lat, lon) for lat in (south, north) for lon in (west, east)]
    cols_f = [(cx - xo) / xs for cx, _ in corners]
    rows_f = [(cy - yo) / ys for _, cy in corners]
    r0, r1 = max(0, int(min(rows_f)) - 2), min(n_rows, int(max(rows_f)) + 3)
    c0, c1 = max(0, int(min(cols_f)) - 2), min(n_cols, int(max(cols_f)) + 3)
    return proj, xs, xo, ys, yo, slice(r0, r1), slice(c0, c1)


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
        proj, xs, xo, ys, yo, rows, cols = _scan_window(f, "Smoke", window)
        r0, c0 = rows.start, cols.start
        west, south, east, north = window
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


def classify_density(aod: float | None) -> str | None:
    """Etiqueta de densidad según el espesor óptico (550 nm); None si no hay dato válido."""
    if aod is None or not math.isfinite(aod) or aod < 0:
        return None
    if aod >= AOD_DENSE_MIN:
        return "denso"
    if aod >= AOD_MODERATE_MIN:
        return "moderado"
    return "tenue"


def _is_unsigned_attr(ds) -> bool:
    """Detecta la convención NetCDF classic `_Unsigned="true"` que h5py no aplica sola."""
    flag = ds.attrs.get("_Unsigned")
    if isinstance(flag, (bytes, bytearray)):
        flag = flag.decode("ascii", errors="ignore")
    elif isinstance(flag, np.ndarray) and flag.size:
        val = flag.ravel()[0]
        flag = val.decode("ascii", errors="ignore") if isinstance(val, (bytes, bytearray)) else str(val)
    return str(flag).strip().lower() == "true"


def _unpack_unsigned(ds, arr: np.ndarray) -> tuple[np.ndarray, np.dtype | None]:
    """Reinterpreta enteros con signo como sin signo si el dataset declara `_Unsigned="true"`."""
    if arr.dtype.kind == "i" and _is_unsigned_attr(ds):
        unsigned_dtype = np.dtype(f"u{arr.dtype.itemsize}")
        return arr.view(unsigned_dtype), arr.dtype
    return arr, None


def parse_aod(content: bytes, key: str,
              window: tuple[float, float, float, float] = goes.READ_WINDOW) -> list[dict[str, Any]]:
    """Píxeles de espesor óptico (AOD, 550 nm) de un archivo AODF dentro de `window`.

    Aplica `_Unsigned="true"` (PUG GOES-R: `AOD` int16 y `DQF` int8 empaquetados sin signo),
    `_FillValue`, `scale_factor` y `add_offset` solo si el dataset los declara, y descarta
    calidad menor a `AOD_DQF_MAX`, valores no finitos, negativos o mayores a `AOD_MAX`.
    """
    import h5py

    base = goes.key_start(key)
    if base is None:
        raise goes.GoesError(f"El nombre del archivo AODF no trae fecha legible: {key}")
    try:
        f = h5py.File(io.BytesIO(content), "r")
    except OSError as exc:
        raise goes.GoesError("El archivo AODF no es un NetCDF4/HDF5 válido.") from exc
    with f:
        if "AOD" not in f:
            raise goes.GoesError("El archivo AODF no trae el dataset AOD.")
        proj, xs, xo, ys, yo, rows, cols = _scan_window(f, "AOD", window)
        r0, c0 = rows.start, cols.start
        west, south, east, north = window
        ds = f["AOD"]
        raw, signed_dtype = _unpack_unsigned(ds, np.asarray(ds[rows, cols]))
        fill = ds.attrs.get("_FillValue")
        valid = np.ones(raw.shape, dtype=bool)
        if fill is not None:
            fill_val = np.asarray(fill).ravel()[0]
            if signed_dtype is not None:
                fill_val = fill_val.astype(signed_dtype).view(raw.dtype)
            else:
                fill_val = fill_val.astype(raw.dtype)
            valid &= raw != fill_val
        aod = raw.astype("float64") * goes._attr(ds, "scale_factor") + goes._attr(ds, "add_offset", 0.0)
        with np.errstate(invalid="ignore"):
            valid &= np.isfinite(aod) & (aod >= 0) & (aod <= AOD_MAX)
        if "DQF" in f:
            dqf_ds = f["DQF"]
            dqf_raw, dqf_signed = _unpack_unsigned(dqf_ds, np.asarray(dqf_ds[rows, cols]))
            dqf_fill = dqf_ds.attrs.get("_FillValue")
            if dqf_fill is not None:
                dqf_fill_val = np.asarray(dqf_fill).ravel()[0]
                if dqf_signed is not None:
                    dqf_fill_val = dqf_fill_val.astype(dqf_signed).view(dqf_raw.dtype)
                else:
                    dqf_fill_val = dqf_fill_val.astype(dqf_raw.dtype)
                valid &= dqf_raw != dqf_fill_val
            valid &= (dqf_raw >= 0) & (dqf_raw <= AOD_DQF_MAX)
        if not valid.any():
            return []
        rr, cc = np.nonzero(valid)
        values = aod[rr, cc]
        lat, lon = goes.scan_to_latlon(
            proj, (cc + c0).astype("float64") * xs + xo, (rr + r0).astype("float64") * ys + yo)
    stamp = base.strftime("%Y-%m-%dT%H:%M:%SZ")
    cells = []
    for la, lo, val in zip(lat.tolist(), lon.tolist(), values.tolist()):
        if not (math.isfinite(la) and math.isfinite(lo) and west <= lo <= east and south <= la <= north):
            continue
        cells.append({"lat": round(la, 5), "lon": round(lo, 5), "aod": round(val, 3), "observed_at": stamp})
    return cells


def clip_cells(cells: list[dict[str, Any]], terr) -> list[dict[str, Any]]:
    """Solo las celdas cuya caja de píxel toca territorio chileno (la unión de comunas).

    La ventana de lectura es un rectángulo con Argentina, Bolivia, Perú y mar abierto
    adentro: sin este recorte, humo del otro lado de la cordillera se dibuja sobre el
    mapa de Chile. Una celda que cruza la frontera o la costa se conserva entera —la
    caja es el píxel real del satélite—; se descarta solo la que no toca Chile.
    """
    from shapely.geometry import box

    return [c for c in cells if terr.comunas_in(box(c["min_lon"], c["min_lat"], c["max_lon"], c["max_lat"]))]


def _epoch(stamp: str) -> float:
    return datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()


def polygons(cells: list[dict[str, Any]],
             aod_cells: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Celdas → un polígono por mancha contigua de humo, agrupada por instante del barrido.

    Une las cajas de los píxeles con `unary_union`, suaviza el borde escalonado con
    `simplify` y reparte el resultado en polígonos separados. `cells` cuenta los píxeles
    cuyo centro cayó dentro de cada polígono.

    Con `aod_cells` (salida de `parse_aod`) cada polígono suma la mediana y el p90 del AOD de
    los píxeles que caen dentro y salieron a menos de `AOD_MATCH_S` de su barrido, más la
    `density` según el p90. Sin píxeles de AOD en la mancha los tres quedan en None.
    """
    import shapely
    from shapely.geometry import box, mapping
    from shapely.ops import unary_union

    by_scan: dict[str, list[dict[str, Any]]] = {}
    for cell in cells:
        by_scan.setdefault(cell["observed_at"], []).append(cell)
    aod_lon = aod_lat = aod_val = aod_ts = None
    if aod_cells:
        aod_lon = np.array([c["lon"] for c in aod_cells], dtype="float64")
        aod_lat = np.array([c["lat"] for c in aod_cells], dtype="float64")
        aod_val = np.array([c["aod"] for c in aod_cells], dtype="float64")
        aod_ts = np.array([_epoch(c["observed_at"]) for c in aod_cells], dtype="float64")
    out = []
    for observed_at, group in sorted(by_scan.items()):
        boxes = [box(c["min_lon"], c["min_lat"], c["max_lon"], c["max_lat"]) for c in group]
        merged = shapely.set_precision(
            unary_union(boxes).simplify(SIMPLIFY_DEG, preserve_topology=True), PRECISION_DEG)
        parts = [g for g in getattr(merged, "geoms", [merged]) if g.geom_type == "Polygon" and not g.is_empty]
        lons = np.array([c["lon"] for c in group])
        lats = np.array([c["lat"] for c in group])
        near = None
        if aod_ts is not None and aod_ts.size:
            diffs = np.abs(aod_ts - _epoch(observed_at))
            best_idx = int(np.argmin(diffs))
            if diffs[best_idx] <= AOD_MATCH_S:
                # Usa solo el barrido AODF más cercano (normalmente el mismo `_s`), sin mezclar varios barridos.
                near = aod_ts == aod_ts[best_idx]
        for part in parts:
            median = p90 = density = None
            if near is not None and near.any():
                inside = shapely.contains_xy(part, aod_lon[near], aod_lat[near])
                vals = aod_val[near][inside]
                if vals.size:
                    median = round(float(np.median(vals)), 2)
                    p90 = round(float(np.percentile(vals, 90)), 2)
                    density = classify_density(p90)
            out.append({"observed_at": observed_at, "geometry": mapping(part),
                        "cells": int(shapely.contains_xy(part, lons, lats).sum()),
                        "aod_median": median, "aod_p90": p90, "density": density})
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
    return clip_cells(cells, territory())


async def fetch_aod(client: httpx.AsyncClient, hours: int = 1,
                    now: datetime | None = None) -> list[dict[str, Any]]:
    """Píxeles de AOD de los últimos archivos AODF de la ventana; `[]` ante cualquier falla.

    Es mejor esfuerzo: la densidad es un añadido de la capa de humo, así que un listado
    caído, un prefijo vacío o la noche (archivo sin píxeles válidos) no rompen nada. Se
    bajan como máximo `AOD_MAX_FILES` archivos, los más recientes.
    """
    try:
        now = now or datetime.now(timezone.utc)
        satellite = goes.satellite_for(now)
        since = now - timedelta(hours=hours)
        listed = await asyncio.gather(
            *(list_keys(client, satellite, now - timedelta(hours=h), AOD_PRODUCT) for h in range(hours + 1)),
            return_exceptions=True)
        keys = sorted({k for keys in listed if not isinstance(keys, BaseException) for k in keys
                       if (start := goes.key_start(k)) is not None and start >= since},
                      key=lambda k: goes.key_start(k))[-AOD_MAX_FILES:]
        if not keys:
            return []
        sem = asyncio.Semaphore(MAX_PARALLEL)

        async def one(key: str) -> list[dict[str, Any]]:
            try:
                async with sem:
                    content = await download(client, satellite, key)
                return await asyncio.to_thread(parse_aod, content, key)
            except Exception as exc:
                log.info("Se descarta el archivo AODF %s: %r", key, exc)
                return []

        chunks = await asyncio.gather(*(one(k) for k in keys))
        return [cell for chunk in chunks for cell in chunk]
    except Exception as exc:
        log.info("Sin AOD de GOES-19: %r", exc)
        return []


async def fetch_smoke_polygons(client: httpx.AsyncClient, hours: int = 1,
                               now: datetime | None = None) -> tuple[list[dict[str, Any]], bool]:
    """Polígonos de humo con su densidad, y si algún polígono la trae.

    El humo (ADPF) manda: si falla, el `GoesError` se propaga. El AOD (AODF) se pide en
    paralelo y, si falta, los polígonos salen sin densidad.
    """
    now = now or datetime.now(timezone.utc)
    cells, aod = await asyncio.gather(
        fetch_smoke(client, hours, now), fetch_aod(client, hours, now), return_exceptions=True)
    if isinstance(cells, BaseException):
        raise cells
    polys = polygons(cells, aod if isinstance(aod, list) else None)
    return polys, any(p["density"] is not None for p in polys)

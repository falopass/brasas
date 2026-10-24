"""Rayos (flashes) del GLM de GOES, producto L2 LCFA, en el mismo bucket público que el ABI.

GOES-19 lleva el mapeador geostacionario de rayos: cada archivo LCFA cubre unos segundos de
destellos del disco completo y pesa varios MB. Un rayo sobre pasto seco en el sur o la
Patagonia puede ser una ignición antes de que haya columna de humo. El instante de cada
destello es la fecha del archivo (en el nombre, `_sAAAADDDHHMMSS`) más
`flash_time_offset_of_first_event` (segundos), según el PUG del producto.
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
from backend.providers import _retry, goes

log = logging.getLogger("brasa.glm")

PRODUCT = "GLM-L2-LCFA"
# Recorte territorial fino: el polígono comunal generaliza costa y frontera. 0,03°
# (~3,3 km en latitud, menos en longitud hacia el sur) cubre ese borde sin alcanzar
# Argentina, Bolivia ni Perú: con los 0,16° de `firms.COASTAL_TOLERANCE_DEG` Ushuaia
# queda a tiro de Navarino y entraría como destello chileno.
TERRITORY_TOLERANCE_DEG = 0.03
# Una hora de GLM son ~180 archivos; se descargan de a tandas acotadas.
MAX_PARALLEL = 8
# Tope duro por consulta: cada archivo pesa varios MB y un pedido público no puede
# disparar una descarga sin fondo. Si la ventana junta más, se conservan los más recientes.
MAX_FILES = 240


async def list_keys(client: httpx.AsyncClient, satellite: str, hour: datetime) -> list[str]:
    """Mismo listado `list-type=2` que `goes.list_keys`, con el prefijo del producto GLM."""
    prefix = f"{PRODUCT}/{hour:%Y}/{hour.timetuple().tm_yday:03d}/{hour:%H}/"
    url = f"https://{goes.S3_BUCKETS[satellite]}.s3.amazonaws.com/"
    try:
        response = await _retry.get(client, url, params={"list-type": "2", "prefix": prefix})
    except _retry.Failure as exc:
        raise goes.GoesError(f"No fue posible listar GLM ({exc.detail}).") from exc.cause
    return sorted(goes._KEY_RE.findall(response.text))


async def download(client: httpx.AsyncClient, satellite: str, key: str) -> bytes:
    try:
        response = await _retry.get(client, f"https://{goes.S3_BUCKETS[satellite]}.s3.amazonaws.com/{key}")
    except _retry.Failure as exc:
        raise goes.GoesError(f"No fue posible descargar GLM ({exc.detail}).") from exc.cause
    return response.content


def _scaled(ds) -> np.ndarray:
    """Variable 1-D con `scale_factor`/`add_offset` y `_FillValue` → NaN, como `goes._scaled`."""
    raw = ds[:]
    out = raw.astype("float64") * goes._attr(ds, "scale_factor") + goes._attr(ds, "add_offset", 0.0)
    fill = ds.attrs.get("_FillValue")
    if fill is not None:
        out[raw == np.asarray(fill).ravel()[0]] = np.nan
    return out


def in_chile(lat: float, lon: float,
             window: tuple[float, float, float, float] = goes.READ_WINDOW) -> bool:
    """El punto cuenta solo si cae dentro de `window` y sobre territorio chileno.

    La caja sigue mandando: Rapa Nui es comuna chilena pero queda fuera de
    `READ_WINDOW`, así que un destello insular no entra aunque `territory()` lo ubique.
    """
    west, south, east, north = window
    if not (west <= lon <= east and south <= lat <= north):
        return False
    return territory().locate(lat, lon, tolerance_deg=TERRITORY_TOLERANCE_DEG) is not None


def parse_lcfa(content: bytes, satellite: str, key: str,
               window: tuple[float, float, float, float] = goes.READ_WINDOW) -> list[dict[str, Any]]:
    """Destellos de calidad nominal (`flash_quality_flag` 0) dentro de `window`.

    El `id` usa el segundo de inicio del archivo y el índice del destello dentro de él, así
    queda estable entre reprocesos del mismo archivo. Los LCFA cubren ~20 s y reinician los
    índices: con solo el minuto, dos archivos del mismo minuto producían ids iguales y la
    PK con `INSERT OR IGNORE` (tabla `lightning`, DET-03) se tragaba destellos reales.
    """
    import h5py

    base = goes.key_start(key)
    if base is None:
        raise goes.GoesError(f"El nombre del archivo GLM no trae fecha legible: {key}")
    try:
        f = h5py.File(io.BytesIO(content), "r")
    except OSError as exc:
        raise goes.GoesError("El archivo GLM no es un NetCDF4/HDF5 válido.") from exc
    with f:
        # Sin bandera de calidad no hay cómo separar lo nominal de lo degradado: se descarta todo.
        if "flash_quality_flag" not in f:
            return []
        good = np.nonzero(np.asarray(f["flash_quality_flag"][:]) == 0)[0]
        if not len(good):
            return []
        lats, lons = _scaled(f["flash_lat"]), _scaled(f["flash_lon"])
        offsets = _scaled(f["flash_time_offset_of_first_event"])
        energy = _scaled(f["flash_energy"]) if "flash_energy" in f else None
        area = _scaled(f["flash_area"]) if "flash_area" in f else None
    product = f"GOES{satellite[1:]}_GLM"
    result = []
    dropped = 0
    for i in good:
        la, lo = float(lats[i]), float(lons[i])
        if not (math.isfinite(la) and math.isfinite(lo) and in_chile(la, lo, window)):
            dropped += 1
            continue
        offset = float(offsets[i])
        observed = base + timedelta(seconds=offset) if math.isfinite(offset) else base
        result.append({
            "id": f"{product}:{base:%Y%m%d%H%M%S}:{int(i)}",
            "source": product, "sensor": "GLM", "satellite": f"GOES-{satellite[1:]}",
            "lat": round(la, 5), "lon": round(lo, 5),
            "observed_at": observed.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "energy_j": round(float(energy[i]), 1) if energy is not None and math.isfinite(energy[i]) else None,
            "area_km2": round(float(area[i]), 1) if area is not None and math.isfinite(area[i]) else None,
        })
    log.debug("%s: %d destellos nominales, %d descartados por el recorte (caja, territorio o coords inválidas)",
              key, len(good), dropped)
    return result


async def fetch_flashes(client: httpx.AsyncClient, hours: int = 1,
                        now: datetime | None = None) -> list[dict[str, Any]]:
    """Todos los destellos nominales de los archivos GLM de las últimas `hours` horas.

    Lista los prefijos horarios que la ventana toca (uno por hora), descarta los archivos
    anteriores a `since` o sin fecha en el nombre, y descarga el resto en tandas acotadas,
    hasta `MAX_FILES` (los más recientes si la ventana junta más). Un archivo que no se
    pueda leer se registra y se descarta: solo se propaga el error cuando ninguna clave
    de la ventana resultó legible.
    """
    now = now or datetime.now(timezone.utc)
    satellite = goes.satellite_for(now)
    since = now - timedelta(hours=hours)
    listed = await asyncio.gather(
        *(list_keys(client, satellite, now - timedelta(hours=h)) for h in range(hours + 1)))
    keys = sorted({k for keys in listed for k in keys
                   if (start := goes.key_start(k)) is not None and start >= since})
    if len(keys) > MAX_FILES:
        log.warning("La ventana GLM reunió %d archivos; se descargan solo los %d más recientes.",
                    len(keys), MAX_FILES)
        keys = keys[-MAX_FILES:]
    sem = asyncio.Semaphore(MAX_PARALLEL)
    errors: list[Exception] = []

    async def one(key: str) -> list[dict[str, Any]] | None:
        try:
            async with sem:
                content = await download(client, satellite, key)
            return await asyncio.to_thread(parse_lcfa, content, satellite, key)
        except Exception as exc:
            log.warning("Se descarta el archivo GLM %s: %r", key, exc)
            errors.append(exc)
            return None

    chunks = await asyncio.gather(*(one(k) for k in keys))
    if keys and all(chunk is None for chunk in chunks):
        raise errors[0]
    flashes: list[dict[str, Any]] = []
    for chunk in chunks:
        flashes.extend(chunk or [])
    flashes.sort(key=lambda f: f["observed_at"])
    return flashes


# Los destellos se guardan en la tabla `lightning` de work.db al bajarlos (DET-03): sirven
# para marcar si hubo rayos cerca del inicio de un incidente. Retención corta —no es un
# archivo histórico— y la purga viaja en la misma escritura. Los llenan el ciclo de
# ingesta (`Services._ingest_glm`) y la capa pública: sin alguno de los dos no se guarda
# nada y la marca de los incidentes queda en cero, nunca inventada.
LIGHTNING_KEEP_HOURS = 48


def save_flashes(db, flashes: list[dict[str, Any]]) -> int | None:
    """Persiste el lote recién bajado y purga lo que ya cumplió la retención.

    Idempotente por `id`: dos ventanas que se solapan (el ciclo y la capa pública, u
    hours=1 y hours=6) no duplican. Devuelve cuántos destellos quedaron insertados de
    verdad (los ya guardados no cuentan), y `None` si la escritura falló: así quien
    ingiere puede marcar la corrida en error y reintentar el archivo, mientras que un
    fallo de escritura no puede tumbar ni el conjunto público ni el ciclo.
    """
    if not flashes:
        return 0
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=LIGHTNING_KEEP_HOURS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        with db.connect() as conn:
            inserted = conn.executemany(
                "INSERT OR IGNORE INTO lightning(id, observed_at, lat, lon, energy_j, source) VALUES (?,?,?,?,?,?)",
                [(f["id"], f["observed_at"], f["lat"], f["lon"], f.get("energy_j"), f["source"]) for f in flashes],
            ).rowcount
            conn.execute("DELETE FROM lightning WHERE observed_at < ?", (cutoff,))
    except Exception:
        log.warning("No se pudieron guardar los destellos GLM en work.db.", exc_info=True)
        return None
    return inserted

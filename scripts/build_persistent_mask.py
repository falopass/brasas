"""Celdas candidatas a «fuente fija» (DET-05) a partir del archivo FIRMS SP 2019-2025.

Método (docs/investigacion/INV-16-industria-antorchas.md, §3): cada detección de MODIS o VIIRS
cae en una celda de 0,01° (~1,1 km en Chile central). Por celda se cuentan los días distintos
con al menos una detección (MODIS y VIIRS el mismo día cuentan una vez, como dos sensores),
cuántos de esos días son de abril a noviembre —fuera de la temporada alta de quemas, diciembre
a marzo—, los años cubiertos y los sensores que la vieron. Una celda es candidata con más de
15 días distintos y al menos 8 fuera de temporada. Se excluyen las celdas a ≤ 3 km de los
volcanes ya listados en `web/data/persistent_hotspots.json` (se usa el radio de cada fuente).

La salida NO se publica sola: es la lista de candidatos para la revisión humana de INV-16
(§6-7). Solo una celda revisada, con fuente oficial que explique el calor, pasa a mano a
`persistent_hotspots.json`; este script nunca lo modifica.

Uso:  python scripts/build_persistent_mask.py --input firms.csv [carpeta/ ...]
          [--out web/data/persistent_mask_candidates.json] [--min-days 16] [--min-off-season 8]

Campos aceptados: MODIS (`acq_date`, `latitude`, `longitude`, `daynight`, `type`, …) y VIIRS
(`acq_date`, `latitude`, `longitude`, `daynight`, …). Solo `latitude`, `longitude` y `acq_date`
son obligatorios; el sensor sale de `instrument` o `satellite`.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator

ROOT = Path(__file__).resolve().parents[1]

HOTSPOTS = ROOT / "web" / "data" / "persistent_hotspots.json"
DEFAULT_OUT = ROOT / "web" / "data" / "persistent_mask_candidates.json"

CELL_DEG = 0.01                       # celda de la máscara: ~1,1 km en Chile central
MIN_DAYS = 16                         # > 15 días distintos con al menos una detección
MIN_OFF_SEASON = 8                    # ≥ 8 de esos días fuera de diciembre-marzo
VOLCANO_KM = 3.0                      # radio por defecto si la fuente no lo declara
OFF_SEASON_MONTHS = (4, 5, 6, 7, 8, 9, 10, 11)

EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Misma fórmula que backend/geo.py; copiada para que el script corra sin dependencias."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def cell_of(lat: float, lon: float) -> tuple[float, float]:
    """Esquina de la celda de CELL_DEG que contiene el punto; es la identidad de la celda."""
    return (round(math.floor(lat / CELL_DEG) * CELL_DEG, 5),
            round(math.floor(lon / CELL_DEG) * CELL_DEG, 5))


def iter_detections(path: Path) -> Iterator[dict]:
    """Detecciones válidas de un CSV FIRMS SP (MODIS o VIIRS); las filas malas se saltan."""
    with path.open(newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            try:
                yield {
                    "lat": float(row["latitude"]),
                    "lon": float(row["longitude"]),
                    "date": date.fromisoformat(row["acq_date"]),
                    "sensor": row.get("instrument") or row.get("satellite") or "desconocido",
                }
            except (KeyError, TypeError, ValueError):
                continue


def input_files(sources: list[Path]) -> list[Path]:
    """Los --input pueden ser archivos CSV o carpetas: de cada carpeta se toman los *.csv."""
    files: list[Path] = []
    for source in sources:
        files += sorted(source.glob("*.csv")) if source.is_dir() else [source]
    return [f for f in files if f.is_file()]


def summarize(detections: Iterable[dict]) -> dict[tuple[float, float], dict]:
    """Agrupa detecciones por celda: días distintos, días fuera de temporada, años y sensores."""
    cells: dict[tuple[float, float], dict] = {}
    for det in detections:
        cell = cell_of(det["lat"], det["lon"])
        info = cells.setdefault(cell, {"days": set(), "off": set(), "years": set(), "sensors": set()})
        day = det["date"]
        info["days"].add(day)
        if day.month in OFF_SEASON_MONTHS:
            info["off"].add(day)
        info["years"].add(day.year)
        info["sensors"].add(det["sensor"])
    return cells


def load_volcanoes(path: Path = HOTSPOTS) -> list[dict]:
    """Fuentes fijas ya publicadas (volcanes). Si el archivo falta o está mal, lista vacía."""
    try:
        sources = json.loads(path.read_text(encoding="utf-8"))["sources"]
    except (OSError, ValueError, KeyError):
        return []
    return [s for s in sources if "lat" in s and "lon" in s]


def near_volcano(lat: float, lon: float, volcanoes: list[dict]) -> bool:
    return any(haversine_km(lat, lon, v["lat"], v["lon"]) <= v.get("radius_km", VOLCANO_KM)
               for v in volcanoes)


def candidates(cells: dict[tuple[float, float], dict], volcanoes: list[dict],
               min_days: int = MIN_DAYS, min_off_season: int = MIN_OFF_SEASON) -> list[dict]:
    """Celdas que superan los umbrales y no están junto a un volcán conocido.

    `lat`/`lon` de salida son el centro de la celda (para revisarla en un mapa).
    """
    out = []
    for (lat, lon), info in cells.items():
        days, off = len(info["days"]), len(info["off"])
        if days < min_days or off < min_off_season:
            continue
        clat, clon = lat + CELL_DEG / 2, lon + CELL_DEG / 2
        if near_volcano(clat, clon, volcanoes):
            continue
        out.append({
            "lat": round(clat, 4), "lon": round(clon, 4),
            "days": days, "off_season_days": off,
            "years": sorted(info["years"]), "sensors": sorted(info["sensors"]),
        })
    return sorted(out, key=lambda c: (c["lat"], c["lon"]))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                   formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", type=Path, nargs="+", required=True,
                        help="CSV de FIRMS SP o carpetas que los contienen")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT,
                        help=f"salida JSON (por defecto {DEFAULT_OUT.relative_to(ROOT)})")
    parser.add_argument("--min-days", type=int, default=MIN_DAYS,
                        help=f"mínimo de días distintos con detección (por defecto {MIN_DAYS}: >15)")
    parser.add_argument("--min-off-season", type=int, default=MIN_OFF_SEASON,
                        help=f"mínimo de días fuera de dic-mar (por defecto {MIN_OFF_SEASON})")
    args = parser.parse_args(argv)

    files = input_files(args.input)
    if not files:
        sys.exit("error: --input no contiene ningún archivo CSV")
    detections = [det for f in files for det in iter_detections(f)]
    if not detections:
        sys.exit("error: los CSV no tienen detecciones válidas (latitude, longitude, acq_date)")

    cells = summarize(detections)
    found = candidates(cells, load_volcanoes(), args.min_days, args.min_off_season)
    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "note": ("Candidatos de la máscara DET-05 (celdas de 0,01° con al menos "
                 f"{args.min_days} días FIRMS y {args.min_off_season} fuera de dic-mar). "
                 "Requieren revisión humana (INV-16): ninguna celda se publica en "
                 "persistent_hotspots.json sin una fuente oficial que explique el calor."),
        "cells": found,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{len(detections)} detecciones, {len(cells)} celdas, "
          f"{len(found)} candidatas → {args.out}")


if __name__ == "__main__":
    main()

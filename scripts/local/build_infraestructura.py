"""Construye `web/data/infraestructura/chile.json` con infraestructura crítica de Chile (MAPA-181).

Combina dos fuentes con licencia abierta verificada, evitando llamadas directas del
navegador a Overpass API o servidores estatales lentos:
1. OpenStreetMap (extracto Chile de Geofabrik, licencia **ODbL**): cuarteles de bomberos
   (`amenity=fire_station`), escuelas / posibles albergues (`amenity=school`), subestaciones
   eléctricas (`power=substation`), líneas eléctricas de alta tensión (`power=line`,
   `voltage >= 110 kV`) y hospitales OSM donde no hay registro DEIS a <= 500 m.
2. DEIS · MINSAL en `datos.gob.cl` (licencia **CC0 1.0**): establecimientos vigentes de
   salud pública y urgencia (Hospitales, CESFAM, SAR, SAPU, SUR, CECOSF y Postas de Salud
   Rural), clave en zonas rurales donde OSM es incompleto.

Nota sobre MINEDUC: el Directorio de Establecimientos de `datosabiertos.mineduc.cl` y el
WMS de `geoportal.cl` no declaran licencia explícita de redistribución; mientras no se
confirme (criterio de `docs/backlog/hecho/MAPA-181.md`), las escuelas provienen de OSM.

El archivo se guarda en `web/data/infraestructura/chile.json` (carga diferida al encender
la capa desde zoom >= 10, fuera del precaché de `sw.js`).

Uso:
    python scripts/local/build_infraestructura.py [--pbf RUTA] [--deis RUTA]
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
import re
import tempfile
import urllib.request
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from shapely.geometry import LineString, Point, shape
from shapely.ops import unary_union
from shapely.prepared import prep

ROOT = Path(__file__).resolve().parents[2]
OUT_PATH = ROOT / "web" / "data" / "infraestructura" / "chile.json"
COMUNAS_PATH = ROOT / "web" / "data" / "comunas.geojson"

PBF_URL = "https://download.geofabrik.de/south-america/chile-latest.osm.pbf"
DEIS_CSV_URL = (
    "https://datos.gob.cl/dataset/3bf4cf7c-f638-4735-9a01-f65faae4beca/"
    "resource/2c44d782-3365-44e3-aefb-2c8b8363a1bc/download/establecimientos_20261117.csv"
)
DEIS_DATASET_URL = "https://datos.gob.cl/dataset/3bf4cf7c-f638-4735-9a01-f65faae4beca"
OSM_LICENSE_URL = "https://www.openstreetmap.org/copyright"
UA = {"User-Agent": "BRASA-Chile build_infraestructura (+https://github.com/falopass/brasas)"}

# Caja de Chile continental e insular (misma que tests/test_territorio_datos.py).
LAT_MIN, LAT_MAX = -56.5, -17.2
LON_MIN, LON_MAX = -110.0, -66.0
# Tolerancia solo para registros oficiales DEIS MINSAL en costas/fiordos simplificados (~450 m de BCN).
DEIS_COASTAL_TOL_DEG = 0.004
COORD_DECIMALS = 4
MIN_KV = 110
LINE_SIMPLIFY_M = 100.0
METERS_PER_DEG = 111_320.0
COS_LAT_MIN = math.cos(math.radians(abs(LAT_MIN)))
_KV_SPLIT = re.compile(r"[;/,|]+")
_KV_TOKEN = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*(k?v)?\s*$", re.IGNORECASE)

DEIS_TIPOS: dict[str, str] = {
    "Hospital": "Hospital",
    "Centro de Salud Familiar (CESFAM)": "CESFAM",
    "Servicio de Atención Primaria de Urgencia de Alta Resolutividad (SAR)": "SAR",
    "Servicio de Atención Primaria de Urgencia (SAPU)": "SAPU",
    "Servicio de Urgencia Rural (SUR)": "Urgencia rural (SUR)",
    "Posta de Salud Rural (PSR)": "Posta rural",
    "Centro Comunitario de Salud Familiar (CECOSF)": "CECOSF",
}


@lru_cache(maxsize=1)
def _chile_union():
    """Unión de las 345 comunas BCN (incluye Rapa Nui y Juan Fernández, excluye Antártica)."""
    data = json.loads(COMUNAS_PATH.read_text(encoding="utf-8"))
    geoms = [shape(f["geometry"]) for f in data.get("features", []) if f.get("geometry")]
    return unary_union(geoms)


@lru_cache(maxsize=1)
def _chile_mask():
    """Polígono exacto de las 345 comunas BCN sin buffer fronterizo (para fuentes OSM)."""
    return prep(_chile_union())


@lru_cache(maxsize=1)
def _chile_deis_mask():
    """Polígono BCN con tolerancia costera de ~450 m solo para registros oficiales DEIS MINSAL."""
    return prep(_chile_union().buffer(DEIS_COASTAL_TOL_DEG))


def in_chile(lon: float, lat: float, *, coastal_tol: bool = False) -> bool:
    """Valida que (lon, lat) caiga dentro del territorio chileno (polígono comunal BCN).

    Por defecto usa el polígono exacto sin buffer para impedir fugas en fronteras terrestres
    (Perú, Bolivia y Argentina). Con ``coastal_tol=True`` (solo para DEIS MINSAL) admite ~450 m
    en bordes costeros/fiordos por la simplificación de ``comunas.geojson``.
    """
    if not (LON_MIN <= lon <= LON_MAX and LAT_MIN <= lat <= LAT_MAX):
        return False
    mask = _chile_deis_mask() if coastal_tol else _chile_mask()
    return mask.contains(Point(lon, lat))


def parse_max_kv(raw: str | None) -> int:
    """Extrae el mayor voltaje en kV de un tag OSM `voltage` (ej. '220000;110000' -> 220).

    Acepta decimales, unidades explícitas (`V`/`kV`) y separadores múltiples (`;`, `/`, `,`, `|`).
    Rechaza rangos ambiguos (como `110000-220000`) o valores fuera de rango.
    """
    best = 0
    for part in _KV_SPLIT.split(str(raw or "")):
        if not part.strip():
            continue
        match = _KV_TOKEN.match(part)
        if not match:
            continue
        num = float(match.group(1).replace(",", "."))
        unit = (match.group(2) or "").lower()
        if unit == "kv":
            kv = num
        elif unit == "v":
            kv = num / 1000.0
        else:
            kv = num / 1000.0 if num >= 1000.0 else num
        val = int(round(kv))
        if 1 <= val <= 1500:
            best = max(best, val)
    return best


def clean_name(text: str | None) -> str:
    return " ".join(str(text or "").split())[:96]


def _grid_steps(radius_m: float) -> tuple[float, float]:
    """Pasos (cell_lon, cell_lat) que garantizan celdas >= radius_m incluso a -56,5° S."""
    cell_lat = radius_m / METERS_PER_DEG
    cell_lon = radius_m / (METERS_PER_DEG * COS_LAT_MIN)
    return cell_lon, cell_lat


def _has_neighbor(
    grid: dict[tuple[int, int], list[tuple[float, float]]],
    lon: float,
    lat: float,
    cell_lon: float,
    cell_lat: float,
    radius_m: float,
) -> bool:
    cx, cy = int(math.floor(lon / cell_lon)), int(math.floor(lat / cell_lat))
    kx = math.cos(math.radians(lat)) * METERS_PER_DEG
    r2 = radius_m * radius_m
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for olon, olat in grid.get((cx + dx, cy + dy), ()):
                mx = (lon - olon) * kx
                my = (lat - olat) * METERS_PER_DEG
                if mx * mx + my * my <= r2:
                    return True
    return False


def dedupe_points(
    items: list[tuple[float, float, str, str, str]],
    radius_m: float,
) -> list[tuple[float, float, str, str, str]]:
    """Elimina duplicados cercanos en una grilla compensada por latitud, prefiriendo entradas con nombre."""
    cell_lon, cell_lat = _grid_steps(radius_m)
    # Primero elementos con nombre (y detalle), para que ganen sobre nodos anónimos vecinos.
    ordered = sorted(items, key=lambda x: (0 if x[2] else 1, 0 if x[4] else 1, x[1], x[0]))
    grid: dict[tuple[int, int], list[tuple[float, float]]] = {}
    kept: list[tuple[float, float, str, str, str]] = []
    for lon, lat, name, src, detail in ordered:
        if _has_neighbor(grid, lon, lat, cell_lon, cell_lat, radius_m):
            continue
        cx, cy = int(math.floor(lon / cell_lon)), int(math.floor(lat / cell_lat))
        grid.setdefault((cx, cy), []).append((lon, lat))
        kept.append((round(lon, COORD_DECIMALS), round(lat, COORD_DECIMALS), name, src, detail))
    return kept


def simplify_line(coords: list[tuple[float, float]]) -> list[list[float]]:
    """Simplifica una línea de alta tensión en metros y redondea a 4 decimales."""
    pts = [(lon, lat) for lon, lat in coords if in_chile(lon, lat)]
    if len(pts) < 2:
        return []
    lat0 = sum(p[1] for p in pts) / len(pts)
    kx = math.cos(math.radians(lat0)) * METERS_PER_DEG
    line_m = LineString([(lon * kx, lat * METERS_PER_DEG) for lon, lat in pts])
    simp = line_m.simplify(LINE_SIMPLIFY_M, preserve_topology=False)
    out: list[list[float]] = []
    for x, y in simp.coords:
        pt = [round(x / kx, COORD_DECIMALS), round(y / METERS_PER_DEG, COORD_DECIMALS)]
        if in_chile(pt[0], pt[1]) and (not out or out[-1] != pt):
            out.append(pt)
    return out if len(out) >= 2 else []


def load_deis(csv_path: Path | None) -> list[tuple[float, float, str, str, str]]:
    """Lee establecimientos vigentes de salud pública desde el CSV CC0 de DEIS MINSAL."""
    if csv_path and csv_path.is_file():
        raw = csv_path.read_text(encoding="utf-8-sig", errors="replace")
    else:
        req = urllib.request.Request(DEIS_CSV_URL, headers=UA)
        with urllib.request.urlopen(req, timeout=45) as resp:
            raw = resp.read().decode("utf-8-sig", errors="replace")

    reader = csv.DictReader(raw.splitlines(), delimiter=";")
    out: list[tuple[float, float, str, str, str]] = []
    for row in reader:
        estado = (row.get("EstadoFuncionamiento") or "").strip().lower()
        if not estado.startswith("vigente"):
            continue
        tipo_raw = (row.get("TipoEstablecimientoGlosa") or "").strip()
        detalle = DEIS_TIPOS.get(tipo_raw)
        if not detalle:
            continue
        try:
            lat = float((row.get("Latitud") or "").replace(",", ".").strip())
            lon = float((row.get("Longitud") or "").replace(",", ".").strip())
        except ValueError:
            continue
        rlon, rlat = round(lon, COORD_DECIMALS), round(lat, COORD_DECIMALS)
        if not in_chile(rlon, rlat, coastal_tol=True):
            continue
        nombre = clean_name(row.get("EstablecimientoGlosa")) or detalle
        out.append((lon, lat, nombre, "deis", detalle))
    return out


def extract_osm(pbf_path: Path) -> dict[str, list]:
    """Extrae bomberos, escuelas, subestaciones, hospitales y líneas AT desde un PBF de Chile."""
    import osmium  # dependencia opcional de construcción (no se usa en producción ni en tests)

    class Handler(osmium.SimpleHandler):
        def __init__(self) -> None:
            super().__init__()
            self.bomberos: list[tuple[float, float, str, str, str]] = []
            self.escuelas: list[tuple[float, float, str, str, str]] = []
            self.subestaciones: list[tuple[float, float, str, str, str]] = []
            self.hospitales: list[tuple[float, float, str, str, str]] = []
            self.lineas: list[dict] = []

        def _add_pt(self, tags, lon: float, lat: float) -> None:
            rlon, rlat = round(lon, COORD_DECIMALS), round(lat, COORD_DECIMALS)
            if not in_chile(rlon, rlat):
                return
            am = tags.get("amenity")
            pw = tags.get("power")
            name = clean_name(tags.get("name"))
            if am == "fire_station":
                self.bomberos.append((lon, lat, name, "osm", ""))
            elif am == "school":
                self.escuelas.append((lon, lat, name, "osm", ""))
            elif pw == "substation":
                kv = parse_max_kv(tags.get("voltage"))
                det = f"{kv} kV" if kv else ""
                self.subestaciones.append((lon, lat, name, "osm", det))
            elif am == "hospital":
                self.hospitales.append((lon, lat, name, "osm", "Hospital"))

        def node(self, n) -> None:
            if n.tags and n.location.valid():
                self._add_pt(n.tags, n.location.lon, n.location.lat)

        def way(self, w) -> None:
            if not w.tags:
                return
            pw = w.tags.get("power")
            am = w.tags.get("amenity")
            if pw == "line":
                kv = parse_max_kv(w.tags.get("voltage"))
                if kv >= MIN_KV:
                    pts = [(nd.lon, nd.lat) for nd in w.nodes if nd.location.valid()]
                    coords = simplify_line(pts)
                    if coords:
                        self.lineas.append(
                            {
                                "kv": kv,
                                "n": clean_name(w.tags.get("name")),
                                "s": "osm",
                                "coordinates": coords,
                            }
                        )
                return
            if am in ("fire_station", "school", "hospital") or pw == "substation":
                pts = [(nd.lon, nd.lat) for nd in w.nodes if nd.location.valid()]
                if pts:
                    lon = sum(p[0] for p in pts) / len(pts)
                    lat = sum(p[1] for p in pts) / len(pts)
                    self._add_pt(w.tags, lon, lat)

    handler = Handler()
    handler.apply_file(str(pbf_path), locations=True)
    return {
        "bomberos": handler.bomberos,
        "escuelas": handler.escuelas,
        "subestaciones": handler.subestaciones,
        "hospitales": handler.hospitales,
        "lineas": handler.lineas,
    }


def merge_health(
    deis: list[tuple[float, float, str, str, str]],
    osm_hosp: list[tuple[float, float, str, str, str]],
) -> list[tuple[float, float, str, str, str]]:
    """Prioriza DEIS MINSAL (CC0) y solo añade hospitales OSM a > 500 m de cualquier punto DEIS."""
    base = dedupe_points(deis, radius_m=80.0)
    cell_lon, cell_lat = _grid_steps(500.0)
    grid: dict[tuple[int, int], list[tuple[float, float]]] = {}
    for lon, lat, *_ in base:
        grid.setdefault((int(math.floor(lon / cell_lon)), int(math.floor(lat / cell_lat))), []).append((lon, lat))

    extras: list[tuple[float, float, str, str, str]] = []
    for lon, lat, name, src, det in dedupe_points(osm_hosp, radius_m=200.0):
        if not _has_neighbor(grid, lon, lat, cell_lon, cell_lat, 500.0):
            extras.append((lon, lat, name, src, det))
    return base + extras


def filter_schools(schools: list[tuple[float, float, str, str, str]]) -> list[tuple[float, float, str, str, str]]:
    """Deduplica escuelas a <= 120 m y omite nodos anónimos urbanos pegados a una escuela con nombre."""
    deduped = dedupe_points(schools, radius_m=120.0)
    named = [s for s in deduped if s[2]]
    unnamed = [s for s in deduped if not s[2]]
    cell_lon, cell_lat = _grid_steps(500.0)
    grid: dict[tuple[int, int], list[tuple[float, float]]] = {}
    for lon, lat, *_ in named:
        grid.setdefault((int(math.floor(lon / cell_lon)), int(math.floor(lat / cell_lat))), []).append((lon, lat))
    rural_unnamed: list[tuple[float, float, str, str, str]] = []
    for lon, lat, name, src, det in unnamed:
        if not _has_neighbor(grid, lon, lat, cell_lon, cell_lat, 500.0):
            rural_unnamed.append((lon, lat, name, src, det))
    return named + rural_unnamed


def build_payload(pbf_path: Path, deis_path: Path | None) -> dict:
    deis_raw = load_deis(deis_path)
    osm = extract_osm(pbf_path)

    bomberos = dedupe_points(osm["bomberos"], radius_m=100.0)
    salud = merge_health(deis_raw, osm["hospitales"])
    escuelas = filter_schools(osm["escuelas"])
    subestaciones = dedupe_points(osm["subestaciones"], radius_m=150.0)

    rows: list[list] = []
    for kind, group in (("b", bomberos), ("s", salud), ("e", escuelas), ("t", subestaciones)):
        for lon, lat, name, src, detail in group:
            rows.append([lon, lat, kind, name, src, detail])

    lines = sorted(osm["lineas"], key=lambda l: (-l["kv"], l["coordinates"][0][1], l["coordinates"][0][0]))
    now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return {
        "fetched_at": now_iso,
        "note": (
            "Infraestructura crítica de referencia en Chile (MAPA-181): cuarteles de bomberos, "
            "establecimientos de salud pública, escuelas (posibles albergues), subestaciones y "
            "líneas eléctricas de alta tensión (>= 110 kV). Solo referencia orientativa; en "
            "emergencia sigue siempre las rutas y albergues oficiales de SENAPRED y el municipio."
        ),
        "sources": {
            "osm": {
                "name": "OpenStreetMap (Geofabrik Chile)",
                "license": "ODbL",
                "url": OSM_LICENSE_URL,
            },
            "deis": {
                "name": "DEIS · MINSAL (datos.gob.cl)",
                "license": "CC0 1.0",
                "url": DEIS_DATASET_URL,
            },
        },
        "counts": {
            "bomberos": len(bomberos),
            "salud": len(salud),
            "escuelas": len(escuelas),
            "subestaciones": len(subestaciones),
            "lineas_at": len(lines),
        },
        "fields": ["lon", "lat", "k", "n", "s", "d"],
        "rows": rows,
        "lines": lines,
    }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pbf", type=Path, help="ruta local a chile-latest.osm.pbf")
    parser.add_argument("--deis", type=Path, help="ruta local al CSV de establecimientos DEIS MINSAL")
    parser.add_argument("--out", type=Path, default=OUT_PATH, help="ruta de salida del JSON")
    args = parser.parse_args(argv)

    pbf_path = args.pbf
    tmp_dir = None
    if pbf_path is None:
        tmp_dir = tempfile.TemporaryDirectory()
        pbf_path = Path(tmp_dir.name) / "chile-latest.osm.pbf"
        print(f"Descargando {PBF_URL} ...")
        urllib.request.urlretrieve(PBF_URL, pbf_path)

    try:
        payload = build_payload(pbf_path, args.deis)
    finally:
        if tmp_dir is not None:
            tmp_dir.cleanup()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    args.out.write_bytes(raw)
    gz = len(gzip.compress(raw, compresslevel=9, mtime=0))
    print("Conteos:", payload["counts"])
    print(f"Escrito {args.out} ({len(raw):,} B raw / {gz:,} B gzip)")


if __name__ == "__main__":
    main()

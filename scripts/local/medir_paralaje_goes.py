"""Mide el desplazamiento por paralaje de los píxeles GOES en Chile (INV-05 / DET-02).

El producto FDC entrega ángulos de escaneo sobre el elipsoide: no corrige la altura del
terreno (NOAA, ReadMe FDC). Esta herramienta, de solo lectura, hace dos mediciones:

1. Teórica: para puntos de referencia de Chile y alturas de 1.000 a 4.000 m, calcula
   dónde cae el píxel aparente y cuánto hay que moverlo para recuperar el punto real.
2. Empírica: contra los perímetros oficiales de CONAF versionados en los casos, mide qué
   fracción de las detecciones GOES cae dentro y a qué distancia y rumbo queda el resto.
   Es una cota inferior: el perímetro es un área final, no la posición puntual del foco.

No escribe en la base ni en el producto. Uso:
    python scripts/local/medir_paralaje_goes.py [--case ID] [--sample N] [--json salida.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
from shapely import STRtree
from shapely.geometry import Point, shape
from shapely.ops import nearest_points

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.geo import bearing_deg, haversine_km  # noqa: E402
from backend.providers.goes import Projection, latlon_to_scan, scan_to_latlon  # noqa: E402

DATA = ROOT / "web" / "data"
# GOES-Este (GOES-16/19): 75,2° O. Constantes del `goes_imager_projection` del FDC.
PROJ = Projection(lon0=-75.2, h=35786023.0 + 6378137.0, r_eq=6378137.0, r_pol=6356752.31414)
LUGARES = (
    ("Arica", -18.48, -70.31),
    ("Santiago", -33.45, -70.67),
    ("Concepción", -36.83, -73.05),
    ("Temuco", -38.74, -72.59),
    ("Puerto Montt", -41.47, -72.94),
    ("Punta Arenas", -53.16, -70.91),
)
ALTURAS = (1000, 2000, 3000, 4000)
SECTORES = ("N", "NE", "E", "SE", "S", "SO", "O", "NO")


def desplazamiento(proj: Projection, lat: float, lon: float, altura_m: float) -> dict[str, Any]:
    """Punto real a `altura_m` → píxel aparente del FDC y corrección necesaria."""
    x, y = latlon_to_scan(proj, lat, lon, altura_m)
    aparente = scan_to_latlon(proj, np.array([x]), np.array([y]))
    lat_ap, lon_ap = float(aparente[0][0]), float(aparente[1][0])
    return {
        "lat": lat,
        "lon": lon,
        "altura_m": altura_m,
        "lat_aparente": lat_ap,
        "lon_aparente": lon_ap,
        "km": haversine_km(lat_ap, lon_ap, lat, lon),
        "rumbo_correccion": bearing_deg(lat_ap, lon_ap, lat, lon),
        "rumbo_aparente": bearing_deg(lat, lon, lat_ap, lon_ap),
    }


def corregir(proj: Projection, lat_aparente: float, lon_aparente: float, altura_m: float) -> tuple[float, float]:
    """Píxel aparente del FDC + altura del terreno → punto real (la corrección futura)."""
    x, y = latlon_to_scan(proj, lat_aparente, lon_aparente)
    real = scan_to_latlon(proj, np.array([x]), np.array([y]), altura_m)
    return float(real[0][0]), float(real[1][0])


def tabla_teorica(proj: Projection = PROJ) -> list[dict[str, Any]]:
    return [{"lugar": nombre, **desplazamiento(proj, lat, lon, altura)} for nombre, lat, lon in LUGARES for altura in ALTURAS]


def _media_circular(rumbos: list[float]) -> float | None:
    if not rumbos:
        return None
    angulos = np.radians(rumbos)
    return float(np.degrees(np.arctan2(np.sin(angulos).mean(), np.cos(angulos).mean())) % 360)


def _sectores(rumbos: list[float]) -> list[int]:
    out = [0] * len(SECTORES)
    for rumbo in rumbos:
        out[int(rumbo // 45) % len(SECTORES)] += 1
    return out


def _resumen(puntos: list[tuple[float, float, int]], polys: list, sample: int) -> dict[str, Any]:
    """Distancia y rumbo al perímetro más cercano, sobre una muestra determinista."""
    step = max(1, len(puntos) // sample)
    muestra = puntos[::step][:sample]
    distancias, rumbos = [], []
    for lat, lon, idx in muestra:
        borde = nearest_points(Point(lon, lat), polys[idx])[1]
        distancias.append(haversine_km(lat, lon, borde.y, borde.x))
        rumbos.append(bearing_deg(lat, lon, borde.y, borde.x))
    cerca = [(d, b) for d, b in zip(distancias, rumbos) if d <= 2.0]
    return {
        "sample_n": len(muestra),
        "median_km": float(np.percentile(distancias, 50)),
        "p90_km": float(np.percentile(distancias, 90)),
        "max_km": float(max(distancias)),
        "bearing_mean": _media_circular(rumbos),
        "bearing_sectors": _sectores(rumbos),
        "near_2km_n": len(cerca),
        "near_2km_median_km": float(np.median([d for d, _ in cerca])) if cerca else None,
        "near_2km_bearing_mean": _media_circular([b for _, b in cerca]),
        "near_2km_sectors": _sectores([b for _, b in cerca]),
    }


def medir_caso(case: dict[str, Any], data_dir: Path = DATA, sample: int = 2000) -> dict[str, Any]:
    """GOES versionado del caso contra su perímetro oficial de CONAF."""
    goes_path = data_dir / "cases" / f"{case['id']}.goes.json"
    perimeter_path = data_dir / "cases" / f"{case['id']}.perimeter.json"
    result: dict[str, Any] = {
        "id": case["id"],
        "rows": 0,
        "polygons": 0,
        "inside": 0,
        "outside": 0,
        "inside_fraction": None,
        "note": None,
    }
    goes = json.loads(goes_path.read_text(encoding="utf-8")) if goes_path.exists() else None
    perimeter = json.loads(perimeter_path.read_text(encoding="utf-8")) if perimeter_path.exists() else None
    result["rows"] = len(goes["rows"]) if goes else 0
    result["polygons"] = len(perimeter["features"]) if perimeter else 0
    if goes is None:
        result["note"] = "sin GOES versionado"
        return result
    if perimeter is None:
        result["note"] = "sin perímetro versionado"
        return result
    polys = [shape(feature["geometry"]) for feature in perimeter["features"]]
    tree = STRtree(polys)
    outside: list[tuple[float, float, int]] = []
    high_outside: list[tuple[float, float, int]] = []
    high_inside = 0
    for minute, lat, lon, frp, bright, conf in goes["rows"]:
        point = Point(lon, lat)
        idx = int(tree.nearest(point))
        if polys[idx].covers(point):
            result["inside"] += 1
            if conf == 2:
                high_inside += 1
        else:
            outside.append((lat, lon, idx))
            if conf == 2:
                high_outside.append((lat, lon, idx))
    result["outside"] = len(outside)
    result["inside_fraction"] = result["inside"] / result["rows"] if result["rows"] else None
    if outside:
        result.update(_resumen(outside, polys, sample))
    result["high_confidence"] = {
        "inside": high_inside,
        "outside": len(high_outside),
        **(_resumen(high_outside, polys, sample) if high_outside else {"sample_n": 0}),
    }
    return result


def _num(value: float | None, digits: int = 2) -> str:
    return "—" if value is None else f"{value:.{digits}f}".replace(".", ",")


def imprimir(teorica: list[dict[str, Any]], casos: list[dict[str, Any]]) -> None:
    print("## Desplazamiento teórico (GOES-Este, 75,2° O)\n")
    print("| Lugar | Lat | Lon | Altura (m) | km | Rumbo corrección | Rumbo aparente |")
    print("|---|---|---|---|---|---|---|")
    for row in teorica:
        print(
            f"| {row['lugar']} | {_num(row['lat'])} | {_num(row['lon'])} | {row['altura_m']} | "
            f"{_num(row['km'])} | {_num(row['rumbo_correccion'], 1)} | {_num(row['rumbo_aparente'], 1)} |"
        )
    print("\n## Casos versionados\n")
    print(
        "| Caso | Filas GOES | Polígonos | Dentro | Fuera | Dentro % | Muestra | Mediana fuera (km) | p90 (km) | Rumbo medio | Sectores N/NE/E/SE/S/SO/O/NO |"
    )
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for row in casos:
        if row["note"]:
            print(f"| {row['id']} | {row['rows'] or '—'} | {row['polygons'] or '—'} | — | — | — | — | — | — | — | {row['note']} |")
            continue
        sectores = "/".join(str(n) for n in row.get("bearing_sectors", []))
        print(
            f"| {row['id']} | {row['rows']} | {row['polygons']} | {row['inside']} | {row['outside']} | "
            f"{_num((row['inside_fraction'] or 0) * 100, 1)} | {row.get('sample_n', 0)} | "
            f"{_num(row.get('median_km'))} | {_num(row.get('p90_km'))} | {_num(row.get('bearing_mean'), 1)} | {sectores} |"
        )
    print("\n### Detecciones a ≤2 km del perímetro (cota inferior del error)\n")
    print("| Caso | ≤2 km (muestra) | % de la muestra | Mediana ≤2 km (km) | Rumbo medio ≤2 km | Sectores N/NE/E/SE/S/SO/O/NO |")
    print("|---|---|---|---|---|---|")
    for row in casos:
        if row["note"]:
            continue
        muestra = row.get("sample_n") or 1
        sectores = "/".join(str(n) for n in row.get("near_2km_sectors", []))
        print(
            f"| {row['id']} | {row.get('near_2km_n', 0)} | {_num(100 * row.get('near_2km_n', 0) / muestra, 1)} | "
            f"{_num(row.get('near_2km_median_km'))} | {_num(row.get('near_2km_bearing_mean'), 1)} | {sectores} |"
        )


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--case", action="append", help="ID de caso (repetible); por defecto, todos los del catálogo")
    parser.add_argument("--sample", type=int, default=2000, help="píxeles fuera del perímetro usados para distancia y rumbo")
    parser.add_argument("--json", type=Path, help="guarda la medición completa en este archivo")
    args = parser.parse_args()
    catalog = json.loads((DATA / "cases.json").read_text(encoding="utf-8"))
    cases = [case for case in catalog["cases"] if not args.case or case["id"] in args.case]
    if not cases:
        raise SystemExit("No hay casos que coincidan con --case.")
    teorica = tabla_teorica()
    medidas = [medir_caso(case, DATA, args.sample) for case in cases]
    imprimir(teorica, medidas)
    if args.json:
        args.json.write_text(json.dumps({"teorica": teorica, "casos": medidas}, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

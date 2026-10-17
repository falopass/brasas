"""Genera las capas territoriales livianas de BRASA a partir de las comunas de BCN.

Fuente: Biblioteca del Congreso Nacional (mapas vectoriales), vía
https://github.com/fcortes/Chile-GeoJSON (comunas.geojson, CRS84).

Uso:  python scripts/build_territory.py ruta/comunas.geojson
Salida: web/data/comunas.geojson y web/data/regiones.geojson (WGS84, simplificadas).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from shapely.geometry import mapping, shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]

REGION_NAMES = {
    15: "Arica y Parinacota", 1: "Tarapacá", 2: "Antofagasta", 3: "Atacama", 4: "Coquimbo",
    5: "Valparaíso", 13: "Metropolitana", 6: "O'Higgins", 7: "Maule", 16: "Ñuble", 8: "Biobío",
    9: "La Araucanía", 14: "Los Ríos", 10: "Los Lagos", 11: "Aysén", 12: "Magallanes",
}


def drop_islets(geom, min_area: float):
    """Quita islotes diminutos para aligerar la capa, conservando siempre la parte mayor."""
    if geom.geom_type != "MultiPolygon":
        return geom
    parts = sorted(geom.geoms, key=lambda g: g.area, reverse=True)
    kept = [parts[0]] + [g for g in parts[1:] if g.area >= min_area]
    return unary_union(kept)


def rounded(geom, digits: int = 4):
    return json.loads(json.dumps(mapping(geom)), parse_float=lambda x: round(float(x), digits))


def build(source: Path, tolerance: float) -> None:
    data = json.loads(source.read_text(encoding="utf-8"))
    comunas, by_region = [], {}
    for feature in data["features"]:
        p = feature["properties"]
        region_code = int(p["codregion"])
        if region_code not in REGION_NAMES:
            continue
        geom = shape(feature["geometry"]).buffer(0)
        simple = drop_islets(geom, 2e-4).simplify(tolerance, preserve_topology=True)
        point = geom.representative_point()
        minx, miny, maxx, maxy = geom.bounds
        comunas.append({
            "type": "Feature",
            "properties": {
                "code": int(p["cod_comuna"]), "name": p["Comuna"], "provincia": p["Provincia"],
                "region_code": region_code, "region": REGION_NAMES[region_code],
                "center": [round(point.x, 4), round(point.y, 4)],
                "bbox": [round(minx, 3), round(miny, 3), round(maxx, 3), round(maxy, 3)],
                "area_km2": round(float(p.get("st_area_sh") or 0) / 1e6, 1),
            },
            "geometry": rounded(simple),
        })
        by_region.setdefault(region_code, []).append(geom)
    comunas.sort(key=lambda f: f["properties"]["code"])
    regiones = []
    for code, geoms in sorted(by_region.items()):
        union = unary_union(geoms)
        minx, miny, maxx, maxy = union.bounds
        regiones.append({
            "type": "Feature",
            "properties": {"code": code, "name": REGION_NAMES[code],
                           "bbox": [round(minx, 3), round(miny, 3), round(maxx, 3), round(maxy, 3)]},
            "geometry": rounded(drop_islets(union, 2e-3).simplify(tolerance * 2, preserve_topology=True), 3),
        })
    attribution = "Límites comunales: Biblioteca del Congreso Nacional de Chile (BCN), simplificados para visualización."
    out = ROOT / "web" / "data"
    out.mkdir(parents=True, exist_ok=True)
    for name, features in (("comunas", comunas), ("regiones", regiones)):
        payload = {"type": "FeatureCollection", "attribution": attribution, "features": features}
        (out / f"{name}.geojson").write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{len(comunas)} comunas y {len(regiones)} regiones escritas en {out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", type=Path)
    parser.add_argument("--tolerance", type=float, default=0.006, help="Simplificación en grados (0.006 ≈ 600 m)")
    args = parser.parse_args()
    build(args.source, args.tolerance)

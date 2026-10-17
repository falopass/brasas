"""Genera las capas territoriales livianas de BRASA a partir de las comunas de BCN.

Fuente: Biblioteca del Congreso Nacional (mapas vectoriales), en alta resolución por región vía
https://github.com/caracena/chile-geojson (1.geojson … 16.geojson, WGS84).

La simplificación es de cobertura (shapely.coverage_simplify): los bordes compartidos entre comunas
vecinas se simplifican una sola vez, sin huecos ni líneas dobles.

Uso:  python scripts/build_territory.py carpeta_o_archivos.geojson [...] [--tolerance 0.0045]
Salida: web/data/comunas.geojson y web/data/regiones.geojson (WGS84).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import shapely
from shapely.geometry import mapping, shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]

REGION_NAMES = {
    15: "Arica y Parinacota", 1: "Tarapacá", 2: "Antofagasta", 3: "Atacama", 4: "Coquimbo",
    5: "Valparaíso", 13: "Metropolitana", 6: "O'Higgins", 7: "Maule", 16: "Ñuble", 8: "Biobío",
    9: "La Araucanía", 14: "Los Ríos", 10: "Los Lagos", 11: "Aysén", 12: "Magallanes",
}
ANTARTICA = 12202  # Territorio Chileno Antártico: fuera del alcance de los incendios forestales


def drop_islets(geom, min_area: float):
    """Quita islotes diminutos para aligerar la capa, conservando siempre la parte mayor."""
    if geom.geom_type != "MultiPolygon":
        return geom
    parts = sorted(geom.geoms, key=lambda g: g.area, reverse=True)
    kept = [parts[0]] + [g for g in parts[1:] if g.area >= min_area]
    return unary_union(kept)


def rounded(geom, digits: int = 4):
    return json.loads(json.dumps(mapping(geom)), parse_float=lambda x: round(float(x), digits))


def read_features(sources: list[Path]) -> list[dict]:
    files: list[Path] = []
    for source in sources:
        files += sorted(source.glob("*.geojson")) if source.is_dir() else [source]
    features = []
    for path in files:
        features += json.loads(path.read_text(encoding="utf-8"))["features"]
    return features


def build(sources: list[Path], tolerance: float) -> None:
    props, geoms = [], []
    seen = set()
    for feature in read_features(sources):
        p = feature["properties"]
        code, region_code = int(p["cod_comuna"]), int(p["codregion"])
        if region_code not in REGION_NAMES or code == ANTARTICA or code in seen:
            continue
        seen.add(code)
        geom = shapely.make_valid(shape(feature["geometry"]))
        if geom.geom_type == "GeometryCollection":
            geom = unary_union([g for g in geom.geoms if g.geom_type in ("Polygon", "MultiPolygon")])
        props.append(p)
        geoms.append(drop_islets(geom, 1e-4))
    simplified = shapely.coverage_simplify(geoms, tolerance)
    comunas, by_region = [], {}
    for p, original, simple in zip(props, geoms, simplified):
        region_code = int(p["codregion"])
        point = original.representative_point()
        minx, miny, maxx, maxy = original.bounds
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
        by_region.setdefault(region_code, []).append(original)
    comunas.sort(key=lambda f: f["properties"]["code"])
    region_codes = sorted(by_region)
    unions = [drop_islets(unary_union(by_region[c]), 5e-4) for c in region_codes]
    region_simple = shapely.coverage_simplify(unions, tolerance * 3)
    regiones = []
    for code, union, simple in zip(region_codes, unions, region_simple):
        minx, miny, maxx, maxy = union.bounds
        regiones.append({
            "type": "Feature",
            "properties": {"code": code, "name": REGION_NAMES[code],
                           "bbox": [round(minx, 3), round(miny, 3), round(maxx, 3), round(maxy, 3)]},
            "geometry": rounded(simple, 3),
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
    parser.add_argument("sources", type=Path, nargs="+")
    parser.add_argument("--tolerance", type=float, default=0.0045, help="Simplificación en grados (0.0045 ≈ 450 m)")
    args = parser.parse_args()
    build(args.sources, args.tolerance)

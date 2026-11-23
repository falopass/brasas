"""Genera las capas territoriales livianas de BRASA a partir de las comunas de BCN.

Fuente: Biblioteca del Congreso Nacional (mapas vectoriales), en alta resolución por región vía
https://github.com/caracena/chile-geojson (1.geojson … 16.geojson, WGS84).

La simplificación es de cobertura (shapely.coverage_simplify): los bordes compartidos entre comunas
vecinas se simplifican una sola vez, sin huecos ni líneas dobles.

Uso:  python scripts/build_territory.py carpeta_o_archivos.geojson [...] [--tolerance 0.0045]
      python scripts/build_territory.py --repair     # repara web/data/*.geojson sin volver a la fuente
      python scripts/build_territory.py --cabeceras  # actualiza center con cabeceras comunales OSM (ODbL)
Salida: web/data/comunas.geojson y web/data/regiones.geojson (WGS84), más web/data/comunas-index.json
(solo nombre, región, centro y caja de cada comuna, para los buscadores sin procesar el geojson completo).
"""

from __future__ import annotations

import argparse
import json
import unicodedata
import urllib.request
from pathlib import Path

import shapely
from shapely.geometry import Point, mapping, shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]

REGION_NAMES = {
    15: "Arica y Parinacota",
    1: "Tarapacá",
    2: "Antofagasta",
    3: "Atacama",
    4: "Coquimbo",
    5: "Valparaíso",
    13: "Metropolitana",
    6: "O'Higgins",
    7: "Maule",
    16: "Ñuble",
    8: "Biobío",
    9: "La Araucanía",
    14: "Los Ríos",
    10: "Los Lagos",
    11: "Aysén",
    12: "Magallanes",
}
ANTARTICA = 12202  # Territorio Chileno Antártico: fuera del alcance de los incendios forestales


def valid_polygonal(geom):
    """Geometría válida para GEOS y solo poligonal: make_valid puede devolver líneas o puntos."""
    if not geom.is_valid:
        geom = shapely.make_valid(geom)
    if geom.geom_type == "GeometryCollection":
        geom = unary_union([g for g in geom.geoms if g.geom_type in ("Polygon", "MultiPolygon")])
    if geom.geom_type not in ("Polygon", "MultiPolygon"):
        raise ValueError(f"la geometría no conserva ninguna parte poligonal (quedó como {geom.geom_type})")
    return geom


def drop_islets(geom, min_area: float):
    """Quita islotes diminutos para aligerar la capa, conservando siempre la parte mayor."""
    if geom.geom_type != "MultiPolygon":
        return geom
    parts = sorted(geom.geoms, key=lambda g: g.area, reverse=True)
    kept = [parts[0]] + [g for g in parts[1:] if g.area >= min_area]
    return unary_union(kept)


def rounded(geom, digits: int = 4):
    return json.loads(json.dumps(mapping(geom)), parse_float=lambda x: round(float(x), digits))


def rounded_valid(geom, digits: int = 4):
    """Redondea y repara si el redondeo vuelve inválida la geometría.

    Redondear a 3-4 decimales puede colapsar anillos o crear auto-intersecciones; se
    valida el resultado redondeado, no solo la salida de coverage_simplify.
    """
    for _ in range(4):
        out = rounded(geom, digits)
        if shape(out).is_valid:
            return out
        geom = valid_polygonal(shape(out))
    raise ValueError("no se pudo dejar válida la geometría redondeada")


def read_features(sources: list[Path]) -> list[dict]:
    files: list[Path] = []
    for source in sources:
        files += sorted(source.glob("*.geojson")) if source.is_dir() else [source]
    features = []
    for path in files:
        features += json.loads(path.read_text(encoding="utf-8"))["features"]
    return features


def build(
    sources: list[Path],
    tolerance: float,
    out: Path | None = None,
    cabeceras: dict[int, list[float]] | None = None,
) -> None:
    out = out or ROOT / "web" / "data"
    if cabeceras is None and (out / "comunas-index.json").exists():
        # Al regenerar geometrías sobre un directorio ya publicado, conserva cabeceras válidas.
        prev = json.loads((out / "comunas-index.json").read_text(encoding="utf-8"))
        cabeceras = {int(c["code"]): c["center"] for c in prev if isinstance(c.get("center"), list) and len(c["center"]) == 2}
    props, geoms = [], []
    seen = set()
    for feature in read_features(sources):
        p = feature["properties"]
        code, region_code = int(p["cod_comuna"]), int(p["codregion"])
        if region_code not in REGION_NAMES or code == ANTARTICA or code in seen:
            continue
        seen.add(code)
        try:
            geom = valid_polygonal(shape(feature["geometry"]))
        except ValueError as exc:
            raise ValueError(f"comuna {p.get('Comuna', code)} ({code}): {exc}") from exc
        props.append(p)
        geoms.append(drop_islets(geom, 1e-4))
    # coverage_simplify puede colapsar anillos y dejar vértices repetidos: la salida se
    # vuelve a validar para que el archivo publicado sirva para operaciones de conjunto.
    simplified = [valid_polygonal(g) for g in shapely.coverage_simplify(geoms, tolerance)]
    comunas, by_region = [], {}
    for p, original, simple in zip(props, geoms, simplified):
        region_code = int(p["codregion"])
        point = original.representative_point()
        minx, miny, maxx, maxy = original.bounds
        comunas.append(
            {
                "type": "Feature",
                "properties": {
                    "code": int(p["cod_comuna"]),
                    "name": p["Comuna"],
                    "provincia": p["Provincia"],
                    "region_code": region_code,
                    "region": REGION_NAMES[region_code],
                    "center": [round(point.x, 4), round(point.y, 4)],
                    "bbox": [round(minx, 3), round(miny, 3), round(maxx, 3), round(maxy, 3)],
                    "area_km2": round(float(p.get("st_area_sh") or 0) / 1e6, 1),
                },
                "geometry": rounded_valid(simple, 4),
            }
        )
        by_region.setdefault(region_code, []).append(original)
    if cabeceras:
        apply_cabeceras(comunas, cabeceras)
    comunas.sort(key=lambda f: f["properties"]["code"])
    region_codes = sorted(by_region)
    unions = [drop_islets(unary_union(by_region[c]), 5e-4) for c in region_codes]
    region_simple = [valid_polygonal(g) for g in shapely.coverage_simplify(unions, tolerance * 3)]
    regiones = []
    for code, union, simple in zip(region_codes, unions, region_simple):
        minx, miny, maxx, maxy = union.bounds
        regiones.append(
            {
                "type": "Feature",
                "properties": {
                    "code": code,
                    "name": REGION_NAMES[code],
                    "bbox": [round(minx, 3), round(miny, 3), round(maxx, 3), round(maxy, 3)],
                },
                "geometry": rounded_valid(simple, 3),
            }
        )
    attribution = "Límites comunales: Biblioteca del Congreso Nacional de Chile (BCN), simplificados para visualización."
    out.mkdir(parents=True, exist_ok=True)
    for name, features in (("comunas", comunas), ("regiones", regiones)):
        payload = {"type": "FeatureCollection", "attribution": attribution, "features": features}
        (out / f"{name}.geojson").write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    write_index(out, comunas)
    print(f"{len(comunas)} comunas y {len(regiones)} regiones escritas en {out}")


def write_index(out: Path, comunas: list[dict]) -> None:
    keys = ("code", "name", "region", "center", "bbox")
    index = sorted(({k: f["properties"][k] for k in keys} for f in comunas), key=lambda c: c["name"])
    (out / "comunas-index.json").write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


OVERPASS_URLS = (
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
)
_CABECERA_RANK = {"city": 0, "town": 1, "village": 2, "hamlet": 3}


def _norm_name(text: str) -> str:
    clean = "".join(c for c in unicodedata.normalize("NFD", str(text or "")) if not unicodedata.combining(c))
    return " ".join(clean.replace("'", "").replace("’", "").lower().split())


def apply_cabeceras(comunas: list[dict], cabeceras: dict[int, list[float]]) -> int:
    """Reemplaza `properties.center` por la cabecera si cae estrictamente dentro de su polígono."""
    geoms = [(f["properties"]["code"], shape(f["geometry"])) for f in comunas]
    updated = 0
    for feature, (code, own_geom) in zip(comunas, geoms):
        cand = cabeceras.get(code)
        if not cand or len(cand) != 2:
            continue
        lon, lat = round(float(cand[0]), 4), round(float(cand[1]), 4)
        pt = Point(lon, lat)
        if not own_geom.contains(pt):
            continue
        if any(other_code != code and other_geom.contains(pt) for other_code, other_geom in geoms):
            continue
        feature["properties"]["center"] = [lon, lat]
        updated += 1
    return updated


def fetch_cabeceras_osm(comunas: list[dict]) -> dict[int, list[float]]:
    """Consulta Overpass (© OpenStreetMap contributors, ODbL) por `admin_centre` de comunas de Chile."""
    query = (
        "[out:json][timeout:90];\n"
        'area["ISO3166-1"="CL"][admin_level=2]->.cl;\n'
        'relation["boundary"="administrative"]["admin_level"="8"](area.cl)->.rels;\n'
        "(\n"
        '  node(r.rels:"admin_centre");\n'
        '  node["place"~"^(city|town|village|hamlet)$"]["name"](area.cl);\n'
        ")->.pts;\n"
        ".rels out body;\n"
        ".pts out body;\n"
    )
    data = None
    for url in OVERPASS_URLS:
        try:
            req = urllib.request.Request(
                url,
                data=query.encode("utf-8"),
                headers={"User-Agent": "brasas-territory/1.0 (github.com/falopass/brasas)"},
            )
            with urllib.request.urlopen(req, timeout=120) as res:
                data = json.load(res)
                break
        except Exception:
            continue
    if data is None:
        raise RuntimeError("No se pudo consultar Overpass para actualizar cabeceras comunales.")

    nodes_by_id: dict[int, dict] = {}
    place_nodes: list[dict] = []
    rels: list[dict] = []
    for elem in data["elements"]:
        if elem["type"] == "node":
            nodes_by_id[elem["id"]] = elem
            tags = elem.get("tags", {})
            if tags.get("place") in _CABECERA_RANK and tags.get("name"):
                place_nodes.append(elem)
        elif elem["type"] == "relation":
            rels.append(elem)

    rel_admin: dict[int | str, list[dict]] = {}
    for rel in rels:
        tags = rel.get("tags", {})
        ac = next(
            (nodes_by_id[m["ref"]] for m in rel.get("members", []) if m["type"] == "node" and m.get("role") == "admin_centre" and m["ref"] in nodes_by_id),
            None,
        )
        if not ac:
            continue
        rel_admin.setdefault(_norm_name(tags.get("name", "")), []).append(ac)
        cut = tags.get("ine:cut") or tags.get("ref:INE") or tags.get("ref:cl:cut") or ""
        if cut.isdigit():
            rel_admin[int(cut)] = [ac]

    by_name: dict[str, list[dict]] = {}
    for node in place_nodes:
        by_name.setdefault(_norm_name(node["tags"]["name"]), []).append(node)

    geoms = {f["properties"]["code"]: shape(f["geometry"]) for f in comunas}

    def strictly_own(code: int, lon: float, lat: float) -> bool:
        pt = Point(lon, lat)
        return geoms[code].contains(pt) and not any(c != code and g.contains(pt) for c, g in geoms.items())

    def pop_of(node: dict) -> int:
        raw = str(node.get("tags", {}).get("population") or "").replace(",", "").replace(" ", "")
        return int(raw) if raw.isdigit() else 0

    result: dict[int, list[float]] = {}
    for feature in comunas:
        p = feature["properties"]
        code, name = p["code"], p["name"]
        chosen = None
        for ac in rel_admin.get(code, []) + rel_admin.get(_norm_name(name), []):
            lon, lat = round(ac["lon"], 4), round(ac["lat"], 4)
            if strictly_own(code, lon, lat):
                chosen = [lon, lat]
                break
        if not chosen:
            same = [n for n in by_name.get(_norm_name(name), []) if strictly_own(code, round(n["lon"], 4), round(n["lat"], 4))]
            if same:
                same.sort(key=lambda n: (_CABECERA_RANK.get(n["tags"]["place"], 9), -pop_of(n)))
                chosen = [round(same[0]["lon"], 4), round(same[0]["lat"], 4)]
        if not chosen:
            for ac in rel_admin.get(code, []) + rel_admin.get(_norm_name(name), []):
                lon, lat = round(ac["lon"], 4), round(ac["lat"], 4)
                pt = Point(lon, lat)
                if any(c != code and g.contains(pt) for c, g in geoms.items()):
                    continue
                for step in (0.0005, 0.001, 0.0015, 0.002):
                    for dlat, dlon in ((step, 0), (-step, 0), (0, step), (0, -step), (step, step), (step, -step), (-step, step), (-step, -step)):
                        clon, clat = round(lon + dlon, 4), round(lat + dlat, 4)
                        if strictly_own(code, clon, clat):
                            chosen = [clon, clat]
                            break
                    if chosen:
                        break
                if chosen:
                    break
        if not chosen:
            w, s, e, n_lat = p["bbox"]
            in_pts = [
                node for node in place_nodes
                if w <= node["lon"] <= e and s <= node["lat"] <= n_lat
                and strictly_own(code, round(node["lon"], 4), round(node["lat"], 4))
            ]
            if in_pts:
                in_pts.sort(key=lambda node: (_CABECERA_RANK.get(node["tags"]["place"], 9), -pop_of(node)))
                chosen = [round(in_pts[0]["lon"], 4), round(in_pts[0]["lat"], 4)]
        if chosen:
            result[code] = chosen
    return result


def update_cabeceras(out: Path | None = None) -> None:
    """Actualiza `center` en `comunas.geojson` y `comunas-index.json` con cabeceras OSM (ODbL)."""
    out = out or ROOT / "web" / "data"
    path = out / "comunas.geojson"
    payload = json.loads(path.read_text(encoding="utf-8"))
    cabeceras = fetch_cabeceras_osm(payload["features"])
    updated = apply_cabeceras(payload["features"], cabeceras)
    path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    write_index(out, payload["features"])
    print(f"{updated}/{len(payload['features'])} cabeceras actualizadas en {out}")


def repair_published(out: Path | None = None) -> None:
    """Repara en el lugar las geometrías inválidas publicadas, sin tocar el resto del archivo.

    make_valid mueve solo el anillo que GEOS rechaza; las comunas y regiones válidas
    conservan sus bytes. Sirve para los archivos versionados cuando no hay acceso a la
    fuente BCN; un build nuevo ya sale válido por valid_polygonal.
    """
    out = out or ROOT / "web" / "data"
    for name, digits in (("comunas", 4), ("regiones", 3)):
        path = out / f"{name}.geojson"
        payload = json.loads(path.read_text(encoding="utf-8"))
        fixed = 0
        for feature in payload["features"]:
            if shape(feature["geometry"]).is_valid:
                continue
            feature["geometry"] = rounded_valid(shape(feature["geometry"]), digits)
            fixed += 1
        path.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"{path}: {fixed} geometrías reparadas")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("sources", type=Path, nargs="*", help="GeoJSON de BCN por región o carpeta que los contiene")
    parser.add_argument("--tolerance", type=float, default=0.0045, help="Simplificación en grados (0.0045 ≈ 450 m)")
    parser.add_argument("--repair", action="store_true", help="reparar en el lugar web/data/*.geojson sin volver a la fuente")
    parser.add_argument("--cabeceras", action="store_true", help="actualizar center con cabeceras comunales OSM (ODbL)")
    args = parser.parse_args()
    if args.repair:
        repair_published()
    elif args.cabeceras:
        update_cabeceras()
    elif not args.sources:
        parser.error("indica los GeoJSON de origen o usa --repair / --cabeceras")
    else:
        build(args.sources, args.tolerance)

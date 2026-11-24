"""Construye `web/data/scars.json` con los perímetros históricos reales de CONAF (MAPA-182).

Fuente oficial de perímetros: servicio público de IDE Minagri / CONAF alojado en CIREN
(`https://esri.ciren.cl/server/rest/services/IDEMINAGRI/INCENDIOS_MINIS_INSTI/FeatureServer`,
capas `if_magnitud_<temporada>`, equivalentes a los paquetes SHP publicados en
`https://ide.minagri.gob.cl/descarga-de-capas-shp/desastres/`). La antigua capa
`PERÍMETROS_HISTORICOS_2014_2024_CON_SEMANA_DEL_AÑO` de GEPRIF ArcGIS dejó de responder
(HTTP 400); este servicio entrega los mismos polígonos oficiales de CONAF directamente en
GeoJSON `EPSG:4326`.

Metodología geométrica:
- Se proyecta cada geometría oficial a metros locales (`lon * cos(lat0) * 111320`, `lat * 111320`)
  para simplificar y medir área sin distorsión por latitud ni dependencias fuera de `requirements.txt`.
- Se conservan todos los lóbulos con >= 1 % del área oficial (`MultiPolygon` cuando hay varios)
  y todas las islas interiores no quemadas (huecos) con >= 1 % del área oficial.
- Se simplifica cada anillo con Douglas-Peucker (`preserve_topology=True`), se orienta según
  RFC 7946 (exterior antihorario, huecos horarios), se redondea a 4 decimales (~11 m) y se exige
  validez geométrica y retención de área dentro de [90 %, 110 %] del polígono oficial.
- Los incendios que CONAF no publicó en `if_magnitud_*` (`valparaiso-polvora-2014` y
  `agua-fria-2020`) conservan su polígono orientativo marcado como `"perimeter": "approx"`.

Uso:
    python scripts/local/build_scars.py
"""

from __future__ import annotations

import json
import math
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from shapely import transform as shp_transform
from shapely.geometry import MultiPolygon, Polygon, shape
from shapely.geometry.polygon import orient

ROOT = Path(__file__).resolve().parents[2]
SCARS_PATH = ROOT / "web" / "data" / "scars.json"

PERIMETERS_NAME = "CONAF · IDE Minagri (Incendios de Magnitud 2013-2024)"
PERIMETERS_URL = "https://esri.ciren.cl/server/rest/services/IDEMINAGRI/INCENDIOS_MINIS_INSTI/FeatureServer"
UA = {"User-Agent": "BRASA-Chile build_scars (+https://github.com/falopass/brasas)"}

COORD_DECIMALS = 4
MIN_PART_RATIO = 0.01  # conservar lóbulos e islas interiores >= 1 % del área total
MAX_MAIN_VERTICES = 30
MAX_SUB_VERTICES = 12
AREA_RATIO_MIN = 0.90
AREA_RATIO_MAX = 1.10
METERS_PER_DEG = 111_320.0

# Mapa explícito id -> (capa FeatureServer, cláusula WHERE en IDE Minagri CONAF).
OFFICIAL_QUERIES: dict[str, tuple[int, str]] = {
    "china-muerta-2015": (52, "UPPER(nom_incen) LIKE '%CHINA MUERTA%'"),
    "las-maquinas-2017": (54, "UPPER(nom_incen) LIKE '%MAQUINAS%'"),
    "nilahue-barahona-2017": (54, "UPPER(nom_incen) LIKE '%NILAHUE BARAHONA%'"),
    "portezuelo-san-francisco-2017": (
        54,
        "UPPER(nom_incen) LIKE '%SAN FRANCISCO%' AND UPPER(comuna) LIKE '%PORTEZUELO%'",
    ),
    "lago-penuelas-2021": (58, "UPPER(nom_incen) LIKE '%ENGORDA%'"),
    "timaukel-russfin-2022": (59, "UPPER(nom_incen) LIKE '%RUSSFIN%'"),
    "quillon-rosario-2022": (
        59,
        "UPPER(nom_incen) LIKE '%EL ROSARIO%' AND UPPER(comuna) LIKE '%QUILL%'",
    ),
    "santa-ana-2023": (60, "UPPER(nom_incen) = 'SANTA ANA' AND UPPER(comuna) LIKE '%NACIMIENTO%'"),
    "las-tablas-2024": (61, "UPPER(nom_incen) LIKE '%LAS TABLAS%'"),
}


def fetch_official_feature(layer_id: int, where: str) -> dict:
    """Consulta un polígono oficial de CONAF en WGS84 (`EPSG:4326`) desde IDE Minagri."""
    params = urllib.parse.urlencode(
        {
            "where": where,
            "outFields": "nom_incen,comuna,region,temporada,superficie",
            "outSR": "4326",
            "f": "geojson",
        }
    )
    url = f"{PERIMETERS_URL}/{layer_id}/query?{params}"
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=45) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    features = payload.get("features") or []
    if len(features) != 1:
        raise RuntimeError(f"Se esperaba 1 polígono en capa {layer_id} ({where}), llegaron {len(features)}")
    return features[0]


def _simplify_ring_metric(poly_m: Polygon, max_vertices: int) -> Polygon:
    """Simplifica un polígono en metros eligiendo la mínima tolerancia con <= max_vertices."""
    if len(poly_m.exterior.coords) <= max_vertices:
        return poly_m
    lo, hi = 1.0, 5000.0
    best = poly_m.simplify(hi, preserve_topology=True)
    for _ in range(36):
        mid = (lo + hi) / 2
        cand = poly_m.simplify(mid, preserve_topology=True)
        if not isinstance(cand, Polygon) or cand.is_empty:
            hi = mid
            continue
        if len(cand.exterior.coords) > max_vertices:
            lo = mid
        else:
            best = cand
            hi = mid
    if not isinstance(best, Polygon) or best.is_empty:
        raise RuntimeError("No se pudo simplificar el anillo conservando topología")
    # Si el salto de tolerancia dejó margen de área, intenta con una tolerancia apenas mayor/menor
    # alrededor de `hi` buscando mayor fidelidad de área dentro del tope de vértices.
    target_area = poly_m.area
    best_err = abs(best.area - target_area)
    for factor in (0.95, 0.98, 0.995, 1.01, 1.05, 1.15, 1.3):
        cand = poly_m.simplify(hi * factor, preserve_topology=True)
        if isinstance(cand, Polygon) and not cand.is_empty and len(cand.exterior.coords) <= max_vertices:
            err = abs(cand.area - target_area)
            if err < best_err:
                best, best_err = cand, err
    return best


def _round_ring(coords) -> list[list[float]]:
    ring = [[round(float(x), COORD_DECIMALS), round(float(y), COORD_DECIMALS)] for x, y in coords]
    dedup: list[list[float]] = []
    for pt in ring:
        if not dedup or dedup[-1] != pt:
            dedup.append(pt)
    if dedup and dedup[0] != dedup[-1]:
        dedup.append(dedup[0])
    if len(dedup) < 4:
        raise RuntimeError(f"Anillo degenerado tras redondear: {len(dedup)} posiciones")
    return dedup


def simplify_official_geometry(raw_geom: dict) -> tuple[dict, dict[str, float | int]]:
    """Simplifica la geometría oficial en metros preservando lóbulos y huecos >= 1 %."""
    wgs = shape(raw_geom)
    if not wgs.is_valid:
        wgs = wgs.buffer(0)
    lat0 = wgs.centroid.y
    kx = math.cos(math.radians(lat0)) * METERS_PER_DEG

    def to_m(coords):
        out = coords.copy()
        out[:, 0] *= kx
        out[:, 1] *= METERS_PER_DEG
        return out

    def to_deg(coords):
        out = coords.copy()
        out[:, 0] /= kx
        out[:, 1] /= METERS_PER_DEG
        return out

    metric = shp_transform(wgs, to_m)
    if not metric.is_valid:
        metric = metric.buffer(0)
    orig_area_m2 = metric.area
    if orig_area_m2 <= 0:
        raise RuntimeError("Geometría oficial sin área")

    if isinstance(metric, MultiPolygon):
        parts = sorted(metric.geoms, key=lambda p: p.area, reverse=True)
    elif isinstance(metric, Polygon):
        parts = [metric]
    else:
        raise TypeError(f"Geometría inesperada: {metric.geom_type}")

    kept = [p for p in parts if p.area / orig_area_m2 >= MIN_PART_RATIO]
    if not kept:
        kept = [parts[0]]

    out_polys_wgs: list[Polygon] = []
    total_holes = 0
    for idx, part in enumerate(kept):
        max_v = MAX_MAIN_VERTICES if idx == 0 else MAX_SUB_VERTICES
        ext_m = _simplify_ring_metric(Polygon(part.exterior), max_v)
        holes_wgs: list[list[list[float]]] = []
        for interior in part.interiors:
            hole_poly = Polygon(interior)
            if hole_poly.area / orig_area_m2 >= MIN_PART_RATIO:
                hole_s = _simplify_ring_metric(hole_poly, MAX_SUB_VERTICES)
                if hole_s.within(ext_m):
                    hole_wgs = orient(shp_transform(hole_s, to_deg), sign=-1.0)
                    holes_wgs.append(_round_ring(hole_wgs.exterior.coords))
                    total_holes += 1

        ext_wgs = orient(shp_transform(ext_m, to_deg), sign=1.0)
        ext_ring = _round_ring(ext_wgs.exterior.coords)
        poly_wgs = Polygon(ext_ring, holes_wgs)
        if not poly_wgs.is_valid:
            # Si el redondeo provocó contacto con un hueco, revalida descartando solo el hueco inválido.
            valid_holes = [h for h in holes_wgs if Polygon(ext_ring, [h]).is_valid]
            poly_wgs = Polygon(ext_ring, valid_holes)
            total_holes -= len(holes_wgs) - len(valid_holes)
        if not poly_wgs.is_valid:
            raise RuntimeError("Polígono redondeado inválido")
        out_polys_wgs.append(orient(poly_wgs, sign=1.0))

    final_wgs = MultiPolygon(out_polys_wgs) if len(out_polys_wgs) > 1 else out_polys_wgs[0]
    if not final_wgs.is_valid:
        raise RuntimeError("Geometría final inválida tras redondear")

    final_area_m2 = shp_transform(final_wgs, to_m).area
    ratio = final_area_m2 / orig_area_m2
    if not (AREA_RATIO_MIN <= ratio <= AREA_RATIO_MAX):
        raise RuntimeError(f"Retención de área fuera de rango: {ratio:.3f}")

    # Reconstruir GeoJSON limpio con listas (no tuplas) redondeadas a 4 decimales.
    def _coords_of(poly: Polygon) -> list[list[list[float]]]:
        rings = [_round_ring(poly.exterior.coords)]
        for h in poly.interiors:
            rings.append(_round_ring(h.coords))
        return rings

    if isinstance(final_wgs, MultiPolygon):
        geojson = {"type": "MultiPolygon", "coordinates": [_coords_of(p) for p in final_wgs.geoms]}
    else:
        geojson = {"type": "Polygon", "coordinates": _coords_of(final_wgs)}

    verts = sum(len(p.exterior.coords) + sum(len(h.coords) for h in p.interiors) for p in out_polys_wgs)
    stats = {
        "parts": len(out_polys_wgs),
        "holes": total_holes,
        "verts": verts,
        "orig_ha": round(orig_area_m2 / 1e4, 1),
        "final_ha": round(final_area_m2 / 1e4, 1),
        "ratio_pct": round(ratio * 100.0, 1),
    }
    return geojson, stats


def format_scars_json(data: dict) -> str:
    """Serializa el catálogo legible y compacto (< 15 KB) manteniendo coordenadas en una línea."""
    lines = ["{"]
    lines.append(f'  "note": {json.dumps(data["note"], ensure_ascii=False)},')
    lines.append('  "source": {')
    src_items = list(data["source"].items())
    for i, (k, v) in enumerate(src_items):
        comma = "," if i < len(src_items) - 1 else ""
        lines.append(f'    {json.dumps(k)}: {json.dumps(v, ensure_ascii=False)}{comma}')
    lines.append("  },")
    lines.append('  "scars": [')
    for idx, scar in enumerate(data["scars"]):
        lines.append("    {")
        keys = [
            "id",
            "name",
            "season",
            "year",
            "communes",
            "region",
            "burned_ha",
            "perimeter",
            "source",
            "center",
            "geometry",
        ]
        for j, k in enumerate(keys):
            comma = "," if j < len(keys) - 1 else ""
            val = scar[k]
            if k == "geometry":
                coords_json = json.dumps(val["coordinates"], separators=(",", ":"))
                lines.append(f'      "geometry": {{"type": {json.dumps(val["type"])}, "coordinates": {coords_json}}}{comma}')
            else:
                lines.append(f"      {json.dumps(k)}: {json.dumps(val, ensure_ascii=False)}{comma}")
        comma_s = "," if idx < len(data["scars"]) - 1 else ""
        lines.append(f"    }}{comma_s}")
    lines.append("  ]")
    lines.append("}")
    return "\n".join(lines) + "\n"


def build() -> dict:
    existing = json.loads(SCARS_PATH.read_text(encoding="utf-8"))
    now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    existing["note"] = (
        "Cicatrices de incendios grandes documentados por CONAF entre 2014 y 2024. "
        "Nueve entradas usan el perímetro histórico oficial de CONAF (IDE Minagri, capa "
        "if_magnitud_<temporada>) simplificado en metros conservando lóbulos e islas interiores "
        ">= 1 % del área oficial; las dos entradas sin polígono publicado en esa serie conservan "
        "un contorno orientativo marcado como «approx». Las superficies y puntos de inicio "
        "provienen de CONAF-GEPRIF."
    )
    existing["source"]["perimeters_name"] = PERIMETERS_NAME
    existing["source"]["perimeters_url"] = PERIMETERS_URL
    existing["source"]["fetched_at"] = now_iso

    updated_scars = []
    for scar in existing["scars"]:
        sid = scar["id"]
        if sid in OFFICIAL_QUERIES:
            layer_id, where = OFFICIAL_QUERIES[sid]
            feat = fetch_official_feature(layer_id, where)
            props = feat.get("properties") or {}
            official_name = " ".join(str(props.get("nom_incen") or scar["name"]).split())
            geom, st = simplify_official_geometry(feat["geometry"])
            detalle = []
            if st["parts"] > 1:
                detalle.append(f"{st['parts']} lóbulos")
            if st["holes"] > 0:
                detalle.append(f"{st['holes']} isla interior" if st["holes"] == 1 else f"{st['holes']} islas interiores")
            extra = f", {', '.join(detalle)}" if detalle else ""
            scar = {
                **scar,
                "perimeter": "real",
                "source": (
                    f"CONAF · IDE Minagri (if_magnitud_{scar['season'].replace('-', '_')}), "
                    f"perímetro histórico simplificado «{official_name}», temporada {scar['season']}, "
                    f"{scar['burned_ha']} ha ({st['ratio_pct']} % del área geométrica oficial{extra}; "
                    f"no es el borde metro a metro)."
                ),
                "geometry": geom,
            }
            print(
                f"OK  {sid:30s} {geom['type']:12s} parts={st['parts']} holes={st['holes']} "
                f"verts={st['verts']:2d} area={st['final_ha']}/{st['orig_ha']} ha ({st['ratio_pct']}%)"
            )
        else:
            scar = {
                **scar,
                "perimeter": "approx",
            }
            print(f"OK  {sid:30s} approx       (sin polígono en if_magnitud)")
        updated_scars.append(scar)

    existing["scars"] = updated_scars
    return existing


def main() -> None:
    data = build()
    text = format_scars_json(data)
    SCARS_PATH.write_text(text, encoding="utf-8")
    print(f"\nEscrito {SCARS_PATH} ({len(text.encode('utf-8'))} bytes)")


if __name__ == "__main__":
    main()

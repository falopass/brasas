"""Áreas protegidas del SNASPE (parques, reservas y monumentos nacionales), para la ficha del incidente.

Fuente oficial: capa `SNASPE` del FeatureServer de CONAF-GEPRIF (el hub público del Departamento
de Estudios e Investigación, https://deigeprif.com), consulta anónima verificada en
`docs/research/fuentes-meteologix-geprif.md`. Los ítems de GEPRIF declaran los datos «de uso
público» con la obligación de citar a CONAF como fuente.

Uso:  python scripts/local/build_snaspe.py [--refresh]

Determinista y reanudable: cada página cruda se guarda en `data/cache/geprif_snaspe/` (no se
versiona) con su fecha de descarga; si ya existe, se reutiliza. `--refresh` vuelve a
descargarlas. El resultado sí se versiona: `web/data/snaspe.json` (~150 KB gracias a
`maxAllowableOffset`/`geometryPrecision` en la consulta).

La capa repite algunas áreas con geometrías distintas (p. ej. una parte continental y otra
insular de la misma reserva): se publica una sola entrada por nombre con todos sus polígonos.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
from shapely import make_valid
from shapely.geometry import mapping, shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "web" / "data" / "snaspe.json"
CACHE = ROOT / "data" / "cache" / "geprif_snaspe"

SERVICE_URL = "https://services5.arcgis.com/A1ELWse9bRAi2JiV/arcgis/rest/services/SNASPE/FeatureServer/0"
QUERY_URL = f"{SERVICE_URL}/query"
OUT_FIELDS = "Nombre,Categoria,Region"
PAGE = 2000  # maxRecordCount de la capa

CONTROL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]")

LICENSE = "Datos de uso público; citar a CONAF como fuente (declaración de los ítems ArcGIS de GEPRIF-DEI, https://deigeprif.com)"

# La capa escribe la región «Taparacá» (sin la «r») en dos registros; el índice oficial dice Tarapacá.
REGION_FIX = {"Taparacá": "Tarapacá"}


def clean(text: object) -> str:
    """Texto sin caracteres de control ni espacios sobrantes (bordes y repeticiones)."""
    return " ".join(CONTROL_RE.sub("", str(text or "")).split())


def normalize(feature: dict) -> dict | None:
    """Un área de la capa → fila del JSON, o None si le falta algo esencial.

    Geometría en WGS84 (se pide con outSR=4326, ya simplificada por el servicio con
    `maxAllowableOffset` y `geometryPrecision`). Solo polígonos: otra cosa se omite.
    """
    props = feature.get("properties") or {}
    geom = feature.get("geometry") or {}
    name, category, region = (clean(props.get(k)) for k in ("Nombre", "Categoria", "Region"))
    if not (name and category and geom.get("type") in ("Polygon", "MultiPolygon") and geom.get("coordinates")):
        return None
    return {"name": name, "category": category, "region": region or None, "geometry": geom}


def merge_geoms(geoms: list[dict]) -> dict:
    """Todos los polígonos de un mismo nombre en una sola geometría."""
    polys = []
    for geom in geoms:
        if geom["type"] == "Polygon":
            polys.append(geom["coordinates"])
        else:
            polys.extend(geom["coordinates"])
    return {"type": "Polygon", "coordinates": polys[0]} if len(polys) == 1 else {"type": "MultiPolygon", "coordinates": polys}


def dedupe(items: list[dict]) -> list[dict]:
    """Una fila por nombre: la capa repite áreas con partes separadas; se unen los polígonos."""
    by_name: dict[str, dict] = {}
    for item in items:
        key = item["name"].upper()
        if key not in by_name:
            by_name[key] = item | {"geometry": [item["geometry"]]}
        else:
            by_name[key]["geometry"].append(item["geometry"])
            by_name[key]["region"] = by_name[key]["region"] or item["region"]
    return sorted((i | {"geometry": merge_geoms(i["geometry"])} for i in by_name.values()), key=lambda i: (i["category"], i["name"]))


def repair_geom(geom: dict) -> dict:
    """Polígono válido: la simplificación del servicio (`maxAllowableOffset`) deja anillos
    que se cruzan y GEOS los rechaza, así que `covers()` y la distancia al borde en
    backend/geo.py no eran confiables. `buffer(0)` queda de respaldo si make_valid no
    devuelve polígonos (p. ej. solo líneas o puntos)."""
    fixed = make_valid(shape(geom))
    if fixed.geom_type == "GeometryCollection":
        fixed = unary_union([p for p in fixed.geoms if p.geom_type in ("Polygon", "MultiPolygon")])
    if fixed.geom_type not in ("Polygon", "MultiPolygon"):
        fixed = shape(geom).buffer(0)
    return mapping(fixed) if fixed.geom_type in ("Polygon", "MultiPolygon") else geom


def repair_item(item: dict) -> dict:
    """Repara la geometría inválida y corrige «Taparacá»; el resto de la fila no cambia."""
    geom = item["geometry"]
    if not shape(geom).is_valid:
        geom = repair_geom(geom)
    return item | {"region": REGION_FIX.get(item["region"], item["region"]), "geometry": geom}


def fetch_page(offset: int, refresh: bool) -> dict:
    """Una página de la capa; si está en caché (y no se pidió --refresh) se reutiliza."""
    path = CACHE / f"offset_{offset}.json"
    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))
    params = {
        "where": "1=1",
        "outFields": OUT_FIELDS,
        "returnGeometry": "true",
        "outSR": "4326",
        "orderByFields": "FID",
        "geometryPrecision": "3",
        "maxAllowableOffset": "0.005",
        "resultRecordCount": str(PAGE),
        "resultOffset": str(offset),
        "f": "geojson",
    }
    response = httpx.get(QUERY_URL, params=params, timeout=90)
    response.raise_for_status()
    data = response.json()
    if "error" in data:
        sys.exit(f"La capa de GEPRIF respondió con error: {data['error']}")
    raw = {
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "features": data.get("features", []),
        "exceeded": bool(data.get("exceededTransferLimit")),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return raw


def build(pages: list[dict]) -> dict:
    """Páginas crudas → payload versionado, con unión de partes y nota de forma."""
    fetched_at = min(p["fetched_at"] for p in pages)
    items, skipped = [], 0
    for page in pages:
        for feature in page["features"]:
            item = normalize(feature)
            if item is None:
                skipped += 1
            else:
                items.append(item)
    rows = len(items)
    items = [repair_item(i) for i in dedupe(items)]
    notes = [
        "Polígonos del Sistema Nacional de Áreas Silvestres Protegidas del Estado (SNASPE): "
        "parques nacionales, reservas nacionales y monumentos naturales de Chile.",
        f"La capa repite algunas áreas con partes separadas ({rows - len(items)} registros): "
        "se publica una entrada por nombre con todos sus polígonos.",
    ]
    if skipped:
        notes.append(f"Se omitieron {skipped} registros sin nombre, categoría o geometría de polígono.")
    return {
        "source": {"name": "CONAF-GEPRIF", "url": QUERY_URL, "attribution": LICENSE, "fetched_at": fetched_at},
        "note": " ".join(notes),
        "items": items,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--refresh", action="store_true", help="descargar la capa de nuevo")
    args = parser.parse_args()

    pages, offset = [], 0
    while True:
        page = fetch_page(offset, args.refresh)
        pages.append(page)
        print(f"página offset={offset}: {len(page['features'])} registros (descargada {page['fetched_at']})", flush=True)
        if not page["exceeded"] or not page["features"]:
            break
        offset += PAGE

    result = build(pages)
    OUT.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    size_kb = OUT.stat().st_size / 1024
    print(
        f"{OUT.relative_to(ROOT)}: {len(result['items'])} áreas protegidas, {size_kb:.0f} KB "
        f"({sum(len(p['features']) for p in pages)} registros en la capa)"
    )


if __name__ == "__main__":
    main()

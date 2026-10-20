"""Superficie en zona de interfaz urbano-forestal por comuna (OFI-08), insumo de exposición
de RISK-03 junto al Censo 2024 (OFI-07).

Fuente oficial: capa `riesgo_dissolve_point` del catálogo ArcGIS de GEPRIF-DEI (CONAF,
organización `A1ELWse9bRAi2JiV`), la misma que alimenta el tablero «Zonas Interfaz» del hub
<https://deigeprif.com> (ítem 09532374973a495bb185fcbe55711cd3, dueño `deigeprif`). La capa
no publica polígonos —el mapa del tablero usa teselas vectoriales `riesgo_interfaz_tiled`,
que no sirven para medir—; cada registro es una zona de interfaz disuelta por comuna, clase
(`int_name`) y nivel de riesgo (`risk_name`), entregada como punto con `sup_ha` (hectáreas de
la zona) y `dpa_cod` (código CUT de la comuna según CONAF).

Uso:  python scripts/local/build_interfaz.py [--refresh]

Determinista y reanudable: la respuesta cruda se guarda en `data/cache/` (no se versiona) con
la fecha de descarga; si ya existe, se reutiliza y la salida es idéntica. `--refresh` vuelve a
descargarla. El resultado sí se versiona: `web/data/interfaz.json`.

Asignación a comuna: se cruza cada punto con los polígonos de `web/data/comunas.geojson`
(shapely). El `dpa_cod` oficial manda cuando es válido (los polígonos de BRASA están
simplificados ~450 m y un punto de borde puede caer en la comuna vecina); el cruce espacial
sirve de verificación y de respaldo para registros sin `dpa_cod` válido. Las discrepancias
quedan en `notes` del resultado.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
from shapely import STRtree
from shapely.geometry import Point, shape

ROOT = Path(__file__).resolve().parents[2]
GEOJSON = ROOT / "web" / "data" / "comunas.geojson"
OUT = ROOT / "web" / "data" / "interfaz.json"
RAW = ROOT / "data" / "cache" / "interfaz_riesgo_dissolve_point.json"

SERVICE_URL = "https://services5.arcgis.com/A1ELWse9bRAi2JiV/arcgis/rest/services/riesgo_dissolve_point/FeatureServer/0"
QUERY_URL = SERVICE_URL + "/query"
CATALOG_URL = "https://services5.arcgis.com/A1ELWse9bRAi2JiV/arcgis/rest/services"
DASHBOARD_URL = "https://www.arcgis.com/apps/dashboards/09532374973a495bb185fcbe55711cd3"
PAGE = 2000  # maxRecordCount de la capa

LICENSE = (
    "Datos de uso público, citando a CONAF como fuente — declaración del tablero "
    "«Zonas Interfaz» (ítem ArcGIS 09532374973a495bb185fcbe55711cd3, GEPRIF-DEI); "
    "la capa no declara licencia propia y el permiso formal sigue la puerta de OFI-03."
)


def download() -> dict:
    """La capa completa en GeoJSON (EPSG:4326), paginada por maxRecordCount."""
    features, offset = [], 0
    while True:
        params = {
            "where": "1=1",
            "outFields": "*",
            "f": "geojson",
            "orderByFields": "FID",
            "resultRecordCount": PAGE,
            "resultOffset": offset,
        }
        response = httpx.get(QUERY_URL, params=params, timeout=120)
        response.raise_for_status()
        page = response.json()
        if "error" in page:
            sys.exit(f"La capa de CONAF respondió con error: {page['error']}")
        features += page["features"]
        if len(page["features"]) < PAGE:
            break
        offset += PAGE
    raw = {"fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "features": features}
    RAW.parent.mkdir(parents=True, exist_ok=True)
    RAW.write_text(json.dumps(raw, ensure_ascii=False))
    return raw


def build(raw: dict) -> dict:
    collection = json.loads(GEOJSON.read_text())
    polygons = [shape(f["geometry"]) for f in collection["features"]]
    codes = [f["properties"]["code"] for f in collection["features"]]
    index = dict(zip(codes, polygons))
    areas = {f["properties"]["code"]: f["properties"]["area_km2"] for f in collection["features"]}
    tree = STRtree(polygons)

    fetched_at = raw["fetched_at"]
    ha, sin_dpa, fuera, discrepantes = {}, [], 0, []
    for feature in raw["features"]:
        props = feature["properties"]
        lon, lat = feature["geometry"]["coordinates"]
        hits = tree.query(Point(lon, lat), predicate="intersects")
        spatial = codes[hits[0]] if len(hits) else None
        dpa = props.get("dpa_cod")
        if dpa in index:  # el código oficial de CONAF manda
            code = dpa
            if spatial is None:
                fuera += 1  # punto fuera de los polígonos simplificados
            elif spatial != dpa:
                discrepantes.append((dpa, props.get("F_com"), spatial))
        elif spatial is not None:  # sin código oficial válido: decide el cruce
            code = spatial
            sin_dpa.append(spatial)
        else:
            continue  # ni código ni polígono: no se inventa
        ha[code] = ha.get(code, 0) + props["sup_ha"]

    comunas = {
        str(code): {"ha_interfaz": round(total, 1), "pct_comuna": round(total / (areas[code] * 100) * 100, 2)}
        for code, total in sorted(ha.items())
        if total > 0
    }

    notes = [
        "Capa riesgo_dissolve_point del catálogo ArcGIS de GEPRIF-DEI (CONAF): cada "
        "registro es una zona de interfaz urbano-forestal disuelta por comuna, clase de "
        "interfaz y nivel de riesgo, con su superficie en hectáreas (sup_ha) y el código "
        "CUT oficial (dpa_cod). Las clases son Urbano Principal, Urbano Secundario, "
        "Aldea, Vivienda Rural, Loteos-Parcelaciones y Campamentos.",
        "El tablero no publica los polígonos (solo teselas vectoriales): la superficie "
        "es la que declara la capa y la comuna es su dpa_cod, verificado cruzando cada "
        "punto con los polígonos BCN simplificados de web/data/comunas.geojson.",
    ]
    if fuera:
        notes.append(f"{fuera} puntos cayeron fuera de los polígonos simplificados (bordes y costa): se asignaron por su dpa_cod.")
    if sin_dpa:
        notes.append(
            f"{len(sin_dpa)} registros sin dpa_cod válido se asignaron por el polígono que contiene el punto: {sorted(set(sin_dpa))}."
        )
    if discrepantes:
        detalle = ", ".join(f"{d} {n}→{s}" for d, n, s in discrepantes[:8])
        notes.append(
            f"{len(discrepantes)} puntos cayeron en una comuna distinta a su "
            f"dpa_cod (borde o simplificación); se conserva el código oficial. "
            f"Ejemplos: {detalle}."
        )
    missing = sorted(set(index) - {int(c) for c in comunas})
    if missing:
        notes.append("Comunas del índice sin zonas de interfaz en la capa, omitidas: " + ", ".join(str(c) for c in missing) + ".")
    return {
        "source": SERVICE_URL,
        "catalog": CATALOG_URL,
        "dashboard": DASHBOARD_URL,
        "license": LICENSE,
        "fetched_at": fetched_at,
        "notes": notes,
        "comunas": comunas,
    }


def main() -> None:
    refresh = argparse.ArgumentParser()
    refresh.add_argument("--refresh", action="store_true", help="descargar la capa de nuevo")
    args = refresh.parse_args()
    raw = download() if args.refresh or not RAW.exists() else json.loads(RAW.read_text())
    print(f"capa de CONAF: {len(raw['features'])} zonas, descargada {raw['fetched_at']}")
    result = build(raw)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    total = sum(c["ha_interfaz"] for c in result["comunas"].values())
    print(f"{OUT.relative_to(ROOT)}: {len(result['comunas'])} comunas, {total:,.0f} ha en zona de interfaz")


if __name__ == "__main__":
    main()

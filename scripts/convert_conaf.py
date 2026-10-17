"""Convertir capas oficiales CONAF SHP/ZIP a GeoJSON EPSG:4326.

Uso: python scripts/convert_conaf.py archivo.shp --output web/mis_perimetros.geojson
     python scripts/convert_conaf.py archivo.zip --epsg EPSG:32719 --output perimetros.geojson
Instalar requirements-geo.txt para usar este script.
La geometria de temporada completa NO representa necesariamente avance temporal.
"""
from __future__ import annotations
import argparse
from pathlib import Path


def convert(source: Path, dest: Path, epsg: str | None, simplify: float) -> int:
    import geopandas as gpd
    gdf = gpd.read_file(source)
    if gdf.crs is None:
        if not epsg:
            raise ValueError("La capa carece de CRS. Informa --epsg con los metadatos de IDE Minagri.")
        gdf = gdf.set_crs(epsg)
    gdf = gdf.to_crs("EPSG:4326")
    if simplify > 0:
        gdf["geometry"] = gdf.geometry.simplify(simplify, preserve_topology=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(dest, driver="GeoJSON")
    return len(gdf)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, default=Path("perimetros.geojson"))
    parser.add_argument("--epsg", default=None, help="Solo si falta CRS, ej: EPSG:32719")
    parser.add_argument("--simplify", type=float, default=0, help="Simplificación opcional en grados (0 = no simplificar)")
    args = parser.parse_args()
    n = convert(args.source, args.output, args.epsg, args.simplify)
    print(f"Exportadas {n} geometrías a {args.output} (WGS84)")

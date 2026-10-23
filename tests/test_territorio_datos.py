"""QA-72: guarda territorial sobre los datos que el navegador descarga (web/data).

La promesa del producto —focos e incendios que corresponden a Chile real— la
vigila hoy la ingesta (providers/firms.py, geo.py) y el barrido de respuestas
(test_territorio_publico). Falta la red de seguridad sobre los archivos
publicados: si alguien regenera `incendios-nominados.json` con una capa GEPRIF
mal recortada, el mapa muestra fuego en Mendoza y nada falla. Esta prueba
recorre `web/data/**/*.json` (incluye `web/data/cases/`) y `web/data/*.geojson`:
ninguna coordenada puede caer fuera de la caja de Chile continental e insular.

`tests/data/` NO se revisa: esas fixtures traen a propósito filas de otros
países para probar los filtros de ingesta (FIXTURES-01, FUEGO-03..06). Solo
lectura de archivos, sin red.
"""

from __future__ import annotations

import json
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "web" / "data"

# Caja documentada de Chile continental e insular (Rapa Nui y Cabo de Hornos entran).
LAT_MIN, LAT_MAX = -56.5, -17.2
LON_MIN, LON_MAX = -110.0, -66.0

LAT_KEYS = ("lat", "latitude")
LON_KEYS = ("lon", "longitude")

# Claves cuyo valor es una posición [lon, lat(, z)] o una estructura de
# posiciones anidadas (el `coordinates` de GeoJSON).
POS_KEYS = ("center", "camera", "position", "coordinates")

# Claves cuyo arreglo de cuatro números es [oeste, sur, este, norte].
BBOX_KEYS = ("bbox", "extent")

# Estructura posicional declarada aparte: `web/data/cases/*.goes.json` guarda
# las detecciones en `rows`, con el orden de columnas en `fields` («lat», «lon»).
TABLE_FIELDS = "fields"
TABLE_ROWS = "rows"


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _failures() -> list[tuple[str, float, float]]:
    """(ruta dentro del archivo, lat, lon) de cada punto fuera de la caja, todos juntos."""
    out: list[tuple[str, float, float]] = []

    def check(lat, lon, path):
        if not (LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX):
            out.append((path, lat, lon))

    def walk_positions(node, path):
        """Hojas numéricas bajo una clave de POS_KEYS: cada una es [lon, lat(, z)]."""
        if not isinstance(node, list):
            return
        if node and all(_num(v) for v in node):
            if len(node) >= 2:
                check(node[1], node[0], path)
        else:
            for i, v in enumerate(node):
                walk_positions(v, f"{path}[{i}]")

    def walk(node, path):
        if isinstance(node, dict):
            lat_key = next((k for k in LAT_KEYS if _num(node.get(k))), None)
            lon_key = next((k for k in LON_KEYS if _num(node.get(k))), None)
            if lat_key is not None and lon_key is not None:
                check(node[lat_key], node[lon_key], f"{path}.{lat_key}")
            # Tabla posicional (cases/*.goes.json): filas `rows` de columnas `fields`.
            fields, rows = node.get(TABLE_FIELDS), node.get(TABLE_ROWS)
            if isinstance(fields, list) and isinstance(rows, list) and "lat" in fields and "lon" in fields:
                ilat, ilon = fields.index("lat"), fields.index("lon")
                for i, row in enumerate(rows):
                    if isinstance(row, list) and len(row) > max(ilat, ilon) and _num(row[ilat]) and _num(row[ilon]):
                        check(row[ilat], row[ilon], f"{path}.rows[{i}]")
            for key, value in node.items():
                child = f"{path}.{key}"
                if key in POS_KEYS and isinstance(value, list):
                    walk_positions(value, child)
                elif key in BBOX_KEYS and isinstance(value, list) and len(value) == 4 and all(_num(v) for v in value):
                    for off in (0, 2):  # (oeste, sur) y (este, norte)
                        check(value[off + 1], value[off], f"{child}[{off}]")
                elif isinstance(value, (dict, list)):
                    walk(value, child)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")

    for f in sorted(DATA.rglob("*.json")) + sorted(DATA.glob("*.geojson")):
        try:
            walk(json.loads(f.read_text(encoding="utf-8")), f.name)
        except (OSError, ValueError):
            continue  # la forma la vigila test_data_files; aquí solo el territorio

    return out


def test_ningun_punto_publicado_cae_fuera_de_chile():
    failures = _failures()
    assert not failures, "puntos fuera de Chile en los datos publicados:\n" + "\n".join(
        f"  {path}: lat {lat}, lon {lon}" for path, lat, lon in failures
    )

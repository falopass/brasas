"""Genera web/data/localidades.json: índice estático de localidades chilenas (MAPA-167).

Fuente: extracto de OpenStreetMap vía Overpass API — © OpenStreetMap contributors, ODbL
(se declara en web/data/licencias.json y docs/FUENTES.md). Se toman los nodos
place=city|town|village|hamlet|suburb|neighbourhood|locality|isolated_dwelling con nombre,
se les asigna la comuna por punto-en-polígono sobre web/data/comunas.geojson (límites BCN;
al caer fuera por la costa simplificada o las islas, el centro comunal más cercano a
≤ 30 km) y se deduplica por nombre + comuna quedándose el lugar de mayor jerarquía.

web/data entero tiene presupuesto de 4 MB (tests/test_data_files.py): para caber, el índice
conserva hasta MAX_POR_COMUNA localidades por comuna — primero ciudades, después pueblos,
villas y sectores— y cada fila viaja compacta: [nombre, comuna, tipo, lat, lon].

Uso:  python3 scripts/build_localidades.py [--endpoint URL] [--salida PATH]

Solo biblioteca estándar: no requiere el .venv del proyecto ni descargas previas.
El JSON queda ordenado por nombre; se commitea y se regenera a mano cuando haga falta.
"""

from __future__ import annotations

import argparse
import json
import math
import unicodedata
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMUNAS = ROOT / "web" / "data" / "comunas.geojson"
SALIDA = ROOT / "web" / "data" / "localidades.json"

ENDPOINT = "https://overpass-api.de/api/interpreter"
QUERY = """[out:json][timeout:180];
area["ISO3166-1"="CL"][admin_level=2]->.cl;
node["place"~"^(city|town|village|hamlet|suburb|neighbourhood|locality|isolated_dwelling)$"]["name"](area.cl);
out;
"""

# Encuadre de Chile incluyendo las islas oceánicas; corta la reclamación antártica.
LON_MIN, LON_MAX = -110.0, -66.0
LAT_MIN, LAT_MAX = -56.5, -17.0

# place de OSM → tipo aproximado que muestra el buscador.
TIPO = {
    "city": "ciudad",
    "town": "ciudad",
    "village": "pueblo",
    "hamlet": "pueblo",
    "suburb": "villa",
    "neighbourhood": "villa",
    "locality": "sector",
    "isolated_dwelling": "sector",
}
# Jerarquía para deduplicar: ante el mismo nombre en la misma comuna gana la entidad mayor.
RANGO = {p: i for i, p in enumerate(("city", "town", "village", "suburb", "neighbourhood", "hamlet", "locality", "isolated_dwelling"))}

KM_MAX_COMUNA = 30.0  # distancia al centro comunal cuando el punto cae fuera del polígono
MAX_POR_COMUNA = 7    # tope del índice por comuna, dentro del presupuesto de 4 MB de web/data


def normalizar(texto: str) -> str:
    """Minúsculas sin diacríticos: la misma llave que usa web/js/buscador.js."""
    plano = "".join(c for c in unicodedata.normalize("NFD", texto) if not unicodedata.combining(c))
    return " ".join(plano.lower().split())


def cargar_overpass(endpoint: str) -> list[dict]:
    req = urllib.request.Request(
        endpoint,
        data=QUERY.encode("utf-8"),
        headers={"User-Agent": "brasas-build-localidades/1.0 (github.com/falopass/brasas)"},
    )
    with urllib.request.urlopen(req, timeout=240) as res:
        return json.load(res)["elements"]


def anillos(geometry: dict) -> list[list[list[float]]]:
    """Todos los anillos exteriores de un Polygon o MultiPolygon, como listas [lon, lat]."""
    coords = geometry["coordinates"]
    poligonos = [coords] if geometry["type"] == "Polygon" else coords
    return [p[0] for p in poligonos]


def dentro(lon: float, lat: float, anillos_: list) -> bool:
    """Punto-en-polígono por ray casting sobre todos los anillos exteriores (sin huecos:
    para asignar comuna basta con el borde externo)."""
    dentro_de_alguno = False
    for ring in anillos_:
        dentro_del_anillo = False
        j = len(ring) - 1
        for i in range(len(ring)):
            xi, yi = ring[i]
            xj, yj = ring[j]
            if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
                dentro_del_anillo = not dentro_del_anillo
            j = i
        dentro_de_alguno = dentro_de_alguno or dentro_del_anillo
    return dentro_de_alguno


def distancia_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = math.radians
    h = math.sin((r(lat2) - r(lat1)) / 2) ** 2 + math.cos(r(lat1)) * math.cos(r(lat2)) * math.sin((r(lon2) - r(lon1)) / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def comuna_de(lon: float, lat: float, comunas: list[dict]) -> dict | None:
    for c in comunas:
        w, s, e, n = c["bbox"]
        if w <= lon <= e and s <= lat <= n and dentro(lon, lat, c["anillos"]):
            return c
    cerca, dist = None, KM_MAX_COMUNA
    for c in comunas:
        d = distancia_km(lat, lon, c["center"][1], c["center"][0])
        if d < dist:
            cerca, dist = c, d
    return cerca


def build(endpoint: str, salida: Path) -> None:
    features = json.loads(COMUNAS.read_text(encoding="utf-8"))["features"]
    comunas = [
        {
            "name": f["properties"]["name"],
            "center": f["properties"]["center"],
            "bbox": f["properties"]["bbox"],
            "anillos": anillos(f["geometry"]),
        }
        for f in features
    ]
    elementos = cargar_overpass(endpoint)
    elegidas: dict[tuple[str, str], dict] = {}
    descartes = {"sin_tipo": 0, "fuera": 0, "sin_comuna": 0, "nombre_comuna": 0}
    for el in elementos:
        place = el.get("tags", {}).get("place")
        nombre = (el.get("tags", {}).get("name") or "").strip()
        lat, lon = el.get("lat"), el.get("lon")
        if place not in TIPO or not nombre or lat is None or lon is None:
            descartes["sin_tipo"] += 1
            continue
        if not (LON_MIN <= lon <= LON_MAX and LAT_MIN <= lat <= LAT_MAX):
            descartes["fuera"] += 1
            continue
        comuna = comuna_de(lon, lat, comunas)
        if not comuna:
            descartes["sin_comuna"] += 1
            continue
        if normalizar(nombre) == normalizar(comuna["name"]):
            descartes["nombre_comuna"] += 1  # duplica a la comuna: el buscador ya la lista
            continue
        clave = (normalizar(nombre), comuna["name"])
        if clave in elegidas and RANGO[elegidas[clave]["place"]] <= RANGO[place]:
            continue
        try:
            pop = int(str(el["tags"].get("population") or "").replace(" ", "").replace(",", ""))
        except ValueError:
            pop = 0
        elegidas[clave] = {
            "name": nombre,
            "comuna": comuna["name"],
            "tipo": TIPO[place],
            "lat": round(lat, 4),
            "lon": round(lon, 4),
            "place": place,
            "pop": max(pop, 0),
        }
    # Tope por comuna: se conservan los de mayor jerarquía OSM y, a empate, los de mayor
    # población declarada (la mitad de los nodos la trae) y nombre — evita que se cuelen
    # caseríos diminutos por puro orden alfabético sobre localidades pobladas.
    por_comuna: dict[str, list[dict]] = {}
    for loc in elegidas.values():
        por_comuna.setdefault(loc["comuna"], []).append(loc)
    recortadas = sum(max(0, len(locs) - MAX_POR_COMUNA) for locs in por_comuna.values())
    localidades = sorted(
        (
            [loc["name"], loc["comuna"], loc["tipo"], loc["lat"], loc["lon"]]
            for locs in por_comuna.values()
            for loc in sorted(locs, key=lambda l: (RANGO[l["place"]], -l["pop"], normalizar(l["name"])))[:MAX_POR_COMUNA]
        ),
        key=lambda fila: (normalizar(fila[0]), fila[1]),
    )
    salida.write_text(json.dumps(localidades, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    kb = salida.stat().st_size / 1024
    print(f"{len(elementos)} nodos OSM → {len(localidades)} localidades en {salida.name} ({kb:.0f} KB)")
    print(f"descartes: {descartes['fuera']} fuera de Chile, {descartes['sin_comuna']} sin comuna (>{KM_MAX_COMUNA:g} km), {descartes['nombre_comuna']} con nombre de comuna, {recortadas} por el tope de {MAX_POR_COMUNA}/comuna")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--endpoint", default=ENDPOINT, help="URL del intérprete Overpass")
    parser.add_argument("--salida", type=Path, default=SALIDA)
    args = parser.parse_args()
    build(args.endpoint, args.salida)

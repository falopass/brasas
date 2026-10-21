"""Historia de incendios por comuna (OFI-28): cuánto se quema, temporada por temporada.

Lee el archivo versionado `web/data/incendios-nominados.json` (OFI-19; sin red, sin
claves), agrupa por comuna y escribe `web/data/historia-comunas.json`, que consume la
vista de riesgo (`web/js/views/riesgo.js`).

Uso:  python scripts/local/build_historia_comunas.py

Determinista: la misma entrada produce bytes idénticos (claves ordenadas en el JSON y
listas con orden propio). La comuna se normaliza con el mismo criterio que el resto del
repo (`backend/geo.py: _fold`: minúsculas, sin tildes, espacios simples); esa forma
normalizada es la clave de cada comuna, porque es lo que la vista puede calcular del
nombre territorial. Cuando el nombre de la capa calza el índice territorial (BCN) se
publica con esa escritura.
"""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "web" / "data" / "incendios-nominados.json"
INDEX = ROOT / "web" / "data" / "comunas-index.json"
OUT = ROOT / "web" / "data" / "historia-comunas.json"

TOP_MAX = 3  # incendios más grandes que se publican por comuna

NOTE = (
    "Incendios de 50 ha o más con punto de inicio registrado por CONAF-GEPRIF, "
    "temporadas 2002-2003 a 2023-2024, agrupados por la comuna del registro de CONAF. "
    "El punto de inicio puede caer en la comuna vecina: BRASA no reescribe la comuna "
    "que declara la fuente. Son los incendios grandes que quedaron en la capa, no el "
    "total de incendios ni de superficie quemada de la comuna: los menores de 50 ha no "
    "entran. La superficie es la registrada en la capa para cada punto de inicio."
)

# Escritura de la capa CONAF → forma normalizada del nombre territorial (BCN),
# mismo rol que NAME_VARIANTS de build_censo.py.
NAME_VARIANTS = {"llay-llay": "llaillay"}


def _fold(text: str) -> str:
    """Texto comparable: minúsculas, sin tildes y con espacios simples (backend/geo.py)."""
    normalized = unicodedata.normalize("NFKD", text.casefold())
    return " ".join("".join(ch for ch in normalized if not unicodedata.combining(ch)).split())


def build(items: list[dict], index_names: list[str]) -> dict[str, dict]:
    """Filas del JSON origen → agregado por comuna, con clave en el nombre normalizado."""
    canonical = {_fold(name): name for name in index_names}
    grouped: dict[str, dict] = {}
    display: dict[str, str] = {}
    for item in items:
        key = NAME_VARIANTS.get(_fold(item["comuna"]), _fold(item["comuna"]))
        display.setdefault(key, canonical.get(key, item["comuna"]))
        entry = grouped.setdefault(key, {"n": 0, "ha": 0.0, "seasons": {}, "top": []})
        entry["n"] += 1
        entry["ha"] += item["ha"]
        season = entry["seasons"].setdefault(item["season"], {"n": 0, "ha": 0.0})
        season["n"] += 1
        season["ha"] += item["ha"]
        entry["top"].append({"name": item["name"], "season": item["season"], "ha": item["ha"]})

    comunas = {}
    for key in sorted(grouped):
        entry = grouped[key]
        top = sorted(entry["top"], key=lambda t: (-t["ha"], t["season"], t["name"]))[:TOP_MAX]
        comunas[key] = {
            "comuna": display[key],
            "total_ha": round(entry["ha"], 1),
            "total_incendios": entry["n"],
            "temporadas": [{"season": s, "n": v["n"], "ha": round(v["ha"], 1)} for s, v in sorted(entry["seasons"].items())],
            "top": top,
        }
    return comunas


def payload(source: dict, index_names: list[str]) -> dict:
    """El archivo completo: la fuente del origen, la nota de método y el agregado."""
    return {"source": source["source"], "note": NOTE, "comunas": build(source["items"], index_names)}


def dumps(data: dict) -> str:
    """Serialización única del archivo: misma función en el script y en la guarda."""
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def main() -> None:
    source = json.loads(SRC.read_text(encoding="utf-8"))
    index_names = [c["name"] for c in json.loads(INDEX.read_text(encoding="utf-8"))]
    result = payload(source, index_names)

    canonical = {_fold(name) for name in index_names}
    for key, comuna in result["comunas"].items():
        if key not in canonical:
            print(f"  aviso: «{comuna['comuna']}» no calza el índice territorial; queda con la escritura de la capa")

    OUT.write_text(dumps(result), encoding="utf-8")
    total_ha = sum(c["total_ha"] for c in result["comunas"].values())
    print(
        f"{OUT.relative_to(ROOT)}: {len(result['comunas'])} comunas, "
        f"{sum(c['total_incendios'] for c in result['comunas'].values())} incendios, "
        f"{total_ha:,.1f} ha registradas"
    )


if __name__ == "__main__":
    main()

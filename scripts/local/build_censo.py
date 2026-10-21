"""Población, viviendas y hogares del Censo 2024 por comuna (OFI-07), insumo de exposición de RISK-03.

Fuente oficial: INE, capa `COMUNA_DPA_INDICADORES` del servicio `CENSO2024_V2_gdb`, la misma que
alimenta el «Dashboard de indicadores» enlazado desde https://censo2024.ine.gob.cl/resultados/.
El contenido del INE se rige por CC BY-SA 4.0 con reconocimiento al instituto
(https://www.ine.gob.cl/terminos-de-uso-y-licencia-de-datos-abiertos).

Uso:  python scripts/local/build_censo.py [--refresh]

Determinista y reanudable: la respuesta cruda se guarda en `data/cache/` (no se versiona) con la
fecha de descarga; si ya existe, se reutiliza y la salida es idéntica. `--refresh` vuelve a
descargarla. El resultado sí se versiona: `web/data/censo_2024.json`.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.nombres_comuna import normalizar  # noqa: E402

INDEX = ROOT / "web" / "data" / "comunas-index.json"
OUT = ROOT / "web" / "data" / "censo_2024.json"
RAW = ROOT / "data" / "cache" / "censo2024_comuna.json"

QUERY_URL = ("https://services5.arcgis.com/hUyD8u3TeZLKPe4T/arcgis/rest/services/"
             "CENSO2024_V2_gdb/FeatureServer/0/query")
SERVICE_URL = ("https://services5.arcgis.com/hUyD8u3TeZLKPe4T/arcgis/rest/services/"
               "CENSO2024_V2_gdb/FeatureServer/0")
PARAMS = {"where": "1=1", "returnGeometry": "false", "orderByFields": "CUT", "f": "json",
          "outFields": "CUT,COMUNA,Ind_005_TPob,Ind_001_TViv,Ind_002_THog"}

LICENSE = ("CC BY-SA 4.0, reconocimiento al Instituto Nacional de Estadísticas (INE): "
           "https://www.ine.gob.cl/terminos-de-uso-y-licencia-de-datos-abiertos")


def download() -> dict:
    """Capa completa (346 filas < límite de 2000 por consulta). Devuelve caché + fecha."""
    response = httpx.get(QUERY_URL, params=PARAMS, timeout=60)
    response.raise_for_status()
    data = response.json()
    if "error" in data:
        sys.exit(f"La capa del INE respondió con error: {data['error']}")
    raw = {"fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "features": data["features"]}
    RAW.parent.mkdir(parents=True, exist_ok=True)
    RAW.write_text(json.dumps(raw, ensure_ascii=False))
    return raw


def build(raw: dict) -> dict:
    index = {c["code"]: c["name"] for c in json.loads(INDEX.read_text())}
    fetched_at = raw["fetched_at"]
    comunas, missing, skipped, seen = [], [], [], set()
    for feature in raw["features"]:
        attr = feature["attributes"]
        code, poblacion = attr["CUT"], attr["Ind_005_TPob"]
        if code not in index:                      # fuera del territorio de BRASA (Antártica)
            skipped.append(attr)
            continue
        if not isinstance(poblacion, int) or poblacion <= 0:
            missing.append(code)                   # sin dato: se omite, nunca un 0 inventado
            continue
        seen.add(code)
        ine_name = attr["COMUNA"].strip()
        if normalizar(ine_name) != normalizar(index[code]):
            print(f"  aviso: {code} el INE la llama «{ine_name}», el índice «{index[code]}»")
        comunas.append({"code": code, "name": index[code], "poblacion": poblacion,
                        "viviendas": attr["Ind_001_TViv"], "hogares": attr["Ind_002_THog"],
                        "source": QUERY_URL, "fetched_at": fetched_at})
    comunas.sort(key=lambda c: c["code"])

    notes = ["Capa COMUNA_DPA_INDICADORES del servicio CENSO2024_V2_gdb del INE "
             "(dashboard oficial de resultados del Censo 2024). Censo de derecho: "
             "personas contadas donde residen habitualmente.",
             "Variantes de nombre del INE sobre el mismo CUT: «Marchihue» = Marchigüe, "
             "«Trehuaco» = Treguaco."]
    for attr in skipped:
        notes.append(f"Se omite {attr['CUT']} {attr['COMUNA'].title()}: fuera del territorio "
                     f"de BRASA (población {attr['Ind_005_TPob']}, viviendas {attr['Ind_001_TViv']}).")
    missing += sorted(set(index) - seen - set(missing))   # ni siquiera vienen en la capa
    if missing:
        notes.append("Comunas del índice sin dato de población en la capa, omitidas: "
                     + ", ".join(str(c) for c in missing) + ".")
    return {"source": SERVICE_URL, "license": LICENSE, "fetched_at": fetched_at,
            "totals": {"poblacion": sum(c["poblacion"] for c in comunas),
                       "viviendas": sum(c["viviendas"] for c in comunas),
                       "hogares": sum(c["hogares"] for c in comunas)},
            "notes": notes, "comunas": comunas}


def main() -> None:
    refresh = argparse.ArgumentParser()
    refresh.add_argument("--refresh", action="store_true", help="descargar la capa de nuevo")
    args = refresh.parse_args()
    raw = download() if args.refresh or not RAW.exists() else json.loads(RAW.read_text())
    print(f"capa del INE: {len(raw['features'])} filas, descargada {raw['fetched_at']}")
    result = build(raw)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(f"{OUT.relative_to(ROOT)}: {len(result['comunas'])} comunas, "
          f"{result['totals']['poblacion']:,} personas, "
          f"{result['totals']['viviendas']:,} viviendas")


if __name__ == "__main__":
    main()

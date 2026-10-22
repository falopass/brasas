"""Temporada de incendios 2025-26 por comuna y por región (OFI-30), insumo de Historia.

Fuente oficial: GEPRIF-CONAF, `reporte/incendios_totales_25_26.csv` del repositorio público
`deigeprif/public` (https://github.com/deigeprif/public), documentado en
`docs/research/fuentes-meteologix-geprif.md`. Uso público con cita a CONAF.

Uso:  python scripts/local/build_temporada_2526.py [--refresh]

Determinista y reanudable: el CSV crudo se guarda en `data/cache/` (no se versiona); si ya
existe se reutiliza y la salida es idéntica. `--refresh` lo vuelve a descargar. El resultado
sí se versiona: `web/data/temporada-2526.json`.

Mapeo de columnas verificado sobre el encabezado real del CSV (2026-10):
`comuna`, `region`, `reg_order` (1= norte … 16 = sur), `sup_total` (hectáreas, formato
chileno «1.234,56»), `f_inicio` («YYYY-MM-DD HH:MM»), `estado`.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]

sys.path.insert(0, str(ROOT))

from scripts.nombres_comuna import normalizar  # noqa: E402

INDEX = ROOT / "web" / "data" / "comunas-index.json"
OUT = ROOT / "web" / "data" / "temporada-2526.json"
RAW = ROOT / "data" / "cache" / "incendios_totales_25_26.csv"

CSV_URL = ("https://raw.githubusercontent.com/deigeprif/public/main/reporte/"
           "incendios_totales_25_26.csv")
LICENSE = ("Datos de CONAF GEPRIF, uso público con cita a CONAF; "
           "ver docs/research/fuentes-meteologix-geprif.md")
# Variantes del CSV de CONAF sobre el mismo territorio del índice (BCN). «Valparaíso
# Insular» agrupa las comunas insulares de la región de Valparaíso (Isla de Pascua, Juan
# Fernández): se pliega a «Valparaíso» para mantener las 16 regiones administrativas.
REGION_VARIANTS = {"VALPARAISO INSULAR": "Valparaíso"}


def normalized(name: str) -> str:
    """Mayúsculas sin tildes, para comparar el nombre de CONAF con el del índice territorial."""
    return "".join(c for c in unicodedata.normalize("NFD", name)
                   if unicodedata.category(c) != "Mn").upper().strip()


def hectares(raw: str) -> float:
    """Superficie en formato chileno («1.234,56», a veces «0,67» o entero)."""
    return float(raw.strip().replace(".", "").replace(",", "."))


def download() -> datetime:
    """Descarga el CSV a la caché cruda y devuelve la fecha de descarga."""
    response = httpx.get(CSV_URL, timeout=90)
    response.raise_for_status()
    RAW.parent.mkdir(parents=True, exist_ok=True)
    RAW.write_text(response.text, encoding="utf-8")
    return datetime.now(timezone.utc)


def load_rows(path: Path) -> list[dict]:
    """Filas del CSV como dicts; exige las columnas que el mapeo necesita."""
    text = path.read_text(encoding="utf-8")
    reader = csv.DictReader(io.StringIO(text))
    needed = {"comuna", "region", "reg_order", "sup_total", "f_inicio"}
    missing = needed - set(reader.fieldnames or [])
    if missing:
        sys.exit(f"El CSV no trae las columnas esperadas {sorted(missing)}; "
                 f"encabezados reales: {reader.fieldnames}")
    return list(reader)


def month(row: dict) -> str:
    """«YYYY-MM» del inicio; vacío si la fila no trae fecha parseable."""
    return row["f_inicio"].strip()[:7]


def peak_month(by_month: dict) -> str | None:
    """Mes con más hectáreas; desempata el más reciente por orden alfabético inverso."""
    if not by_month:
        return None
    return max(by_month, key=lambda m: (by_month[m], m))


def build(rows: list[dict], fetched_at: str) -> dict:
    index = json.loads(INDEX.read_text(encoding="utf-8"))
    by_name = {normalized(c["name"]): c for c in index}
    # Nombre canónico de cada región según el índice, cruzado por `reg_order` del CSV.
    region_norm = {}
    for c in index:
        region_norm.setdefault(normalized(c["region"]), c["region"])

    comunas = {}
    sin_comuna = {}
    regiones = {}
    for row in rows:
        ha = hectares(row["sup_total"])
        region_raw = normalized(row["region"])
        region_name = REGION_VARIANTS.get(region_raw, region_norm.get(region_raw))
        if region_name is None:  # región desconocida: no se descarta en silencio
            region_name = row["region"].strip()
        order = int(row["reg_order"]) if row["reg_order"].strip().isdigit() else 99
        reg = regiones.setdefault(
            region_name, {"name": region_name, "order": order,
                          "incendios": 0, "hectareas": 0.0, "por_mes": defaultdict(float)})
        reg["order"] = min(reg["order"], order)
        reg["incendios"] += 1
        reg["hectareas"] += ha
        reg["por_mes"][month(row)] += ha

        entry = by_name.get(normalizar(row["comuna"]).upper())
        if entry is None or entry["region"] != region_name:
            key = (row["comuna"].strip(), region_name)
            out = sin_comuna.setdefault(key, {"name": key[0], "region": region_name,
                                              "incendios": 0, "hectareas": 0.0})
            out["incendios"] += 1
            out["hectareas"] += ha
            continue
        code = entry["code"]
        com = comunas.setdefault(code, {"code": code, "name": entry["name"],
                                        "region": entry["region"], "incendios": 0,
                                        "hectareas": 0.0, "max_ha": 0.0,
                                        "por_mes": defaultdict(float)})
        com["incendios"] += 1
        com["hectareas"] += ha
        com["max_ha"] = max(com["max_ha"], ha)
        com["por_mes"][month(row)] += ha

    filas_comunas = [
        {"code": c["code"], "name": c["name"], "region": c["region"],
         "incendios": c["incendios"], "hectareas": round(c["hectareas"], 2),
         "mes_peak": peak_month(c["por_mes"]), "max_ha": round(c["max_ha"], 2)}
        for c in comunas.values()]
    orden_region = {r["name"]: r["order"] for r in regiones.values()}
    filas_comunas.sort(key=lambda c: (orden_region[c["region"]], -c["hectareas"]))

    filas_regiones = []
    for r in regiones.values():
        top = max((c for c in comunas.values() if c["region"] == r["name"]),
                  key=lambda c: c["hectareas"], default=None)
        filas_regiones.append(
            {"name": r["name"], "order": r["order"], "incendios": r["incendios"],
             "hectareas": round(r["hectareas"], 2), "mes_peak": peak_month(r["por_mes"]),
             "comuna_top": top["name"] if top else None})
    filas_regiones.sort(key=lambda r: r["order"])

    totales = {"incendios": sum(r["incendios"] for r in filas_regiones),
               "hectareas": round(sum(r["hectareas"] for r in filas_regiones), 2)}
    top = max(comunas.values(), key=lambda c: c["hectareas"], default=None)
    totales["mes_peak"] = peak_month(
        {m: sum(r["por_mes"][m] for r in regiones.values())
         for m in {m for r in regiones.values() for m in r["por_mes"]}})
    totales["comuna_top"] = top["name"] if top else None

    return {"source": CSV_URL, "license": LICENSE, "fetched_at": fetched_at,
            "temporada": "2025-2026", "totales": totales,
            "regiones": [{k: v for k, v in r.items() if k != "order"}
                         for r in filas_regiones],
            "comunas": filas_comunas,
            "sin_comuna": sorted(
                [{"name": s["name"], "region": s["region"], "incendios": s["incendios"],
                  "hectareas": round(s["hectareas"], 2)} for s in sin_comuna.values()],
                key=lambda s: -s["hectareas"])}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true", help="descargar el CSV de nuevo")
    args = parser.parse_args()
    if args.refresh or not RAW.exists():
        fetched = download().isoformat(timespec="seconds")
        print(f"CSV de GEPRIF-CONAF descargado a {RAW.relative_to(ROOT)}")
    else:
        fetched = datetime.fromtimestamp(RAW.stat().st_mtime, timezone.utc) \
            .isoformat(timespec="seconds")
    rows = load_rows(RAW)
    print(f"{len(rows)} incendios en el CSV crudo")
    result = build(rows, fetched)
    suma = round(sum(r["hectareas"] for r in result["regiones"]), 2)
    if suma != result["totales"]["hectareas"]:
        sys.exit(f"Las hectáreas por región ({suma}) no cuadran con el total "
                 f"nacional ({result['totales']['hectareas']}); no se escribe el JSON")
    print(f"{len(result['regiones'])} regiones, {len(result['comunas'])} comunas, "
          f"{result['totales']['incendios']} incendios, "
          f"{result['totales']['hectareas']:,.1f} ha")
    if result["sin_comuna"]:
        print(f"  sin_comuna: {len(result['sin_comuna'])} nombres sin calce "
              f"({sum(s['incendios'] for s in result['sin_comuna'])} incendios)")
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"escrito {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

"""Campamentos catastrados por comuna (OFI-25), insumo de exposición de RISK-03.

Fuente oficial: MINVU, capa `Catastros_campamentos` del FeatureServer público del Geoportal
(`geoide.minvu.cl/server/rest/services/Catastros/Catastros_campamentos/FeatureServer`),
el Catastro Nacional de Campamentos. El ítem no declara licencia: se usa el agregado por
comuna citando al MINVU, con la salvedad escrita en el JSON y en `docs/FUENTES.md`
(decisión del dueño; si el MINVU responde con una licencia, se anota aquí).

Uso:  python scripts/local/build_campamentos.py [--refresh]

Determinista y reanudable: la respuesta cruda se guarda en `data/cache/` (no se versiona) con
la fecha de descarga; si ya existe, se reutiliza y la salida es idéntica. `--refresh` vuelve
a descargarla. El resultado sí se versiona: `web/data/campamentos.json`.

Solo sale **agregado por comuna**: número de campamentos con `EST = "VIGENTE"` (los 95 con
«VIGENTE SIN PRESENCIA TERRITORIAL CON GESTIONES PENDIENTES» no tienen terreno que exponerse
al fuego) y hogares catastrados (`HOGARESCAT`; `HOGARESCEN` es el censo viejo del campamento
y no siempre viene). Nunca nombres, folios ni coordenadas: un punto de campamento señala
hogares vulnerables y la política del proyecto es minimizar (SEC-01..SEC-05).
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
OUT = ROOT / "web" / "data" / "campamentos.json"
RAW = ROOT / "data" / "cache" / "minvu_campamentos.json"

QUERY_URL = ("https://geoide.minvu.cl/server/rest/services/Catastros/"
             "Catastros_campamentos/FeatureServer/0/query")
SERVICE_URL = ("https://geoide.minvu.cl/server/rest/services/Catastros/"
               "Catastros_campamentos/FeatureServer")
PARAMS = {"where": "EST='VIGENTE'", "returnGeometry": "false", "f": "json",
          "orderByFields": "COM", "outFields": "COM,REG,HOGARESCAT",
          "resultRecordCount": 2000}

LICENSE = ("Sin licencia declarada en el ítem del Geoportal (campo license vacío); se usa "
           "citando al MINVU y solo el agregado por comuna. Consulta de reutilización "
           "enviada por el dueño (OFI-25): si llega una licencia, reemplazar esta nota.")


def download() -> dict:
    """Capa completa de campamentos vigentes (~1250 filas < límite de 2000 por consulta)."""
    response = httpx.get(QUERY_URL, params=PARAMS, timeout=60)
    response.raise_for_status()
    data = response.json()
    if "error" in data:
        sys.exit(f"La capa del MINVU respondió con error: {data['error']}")
    if data.get("exceededTransferLimit"):
        sys.exit("La consulta superó el límite de transferencia: ajustar paginación.")
    raw = {"fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "features": data["features"]}
    RAW.parent.mkdir(parents=True, exist_ok=True)
    RAW.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return raw


def build(raw: dict) -> dict:
    index = {normalizar(c["name"]): c for c in json.loads(INDEX.read_text(encoding="utf-8"))}
    fetched_at = raw["fetched_at"]
    agregados: dict[str, dict] = {}
    missing = []
    for feature in raw["features"]:
        attr = feature["attributes"]
        nombre = (attr.get("COM") or "").strip()
        comuna = index.get(normalizar(nombre))
        if comuna is None:
            missing.append(nombre)                    # nombre MINVU sin calce en el índice
            continue
        hogares = attr.get("HOGARESCAT")
        fila = agregados.setdefault(
            comuna["code"], {"code": comuna["code"], "name": comuna["name"],
                             "region": comuna["region"],
                             "n_campamentos": 0, "n_hogares": 0})
        fila["n_campamentos"] += 1
        if isinstance(hogares, (int, float)):         # hay filas sin catastro de hogares
            fila["n_hogares"] += int(hogares)
    comunas = sorted(agregados.values(), key=lambda c: c["code"])

    notes = ["Capa `Catastros_campamentos` del MINVU (Catastro Nacional de Campamentos), "
             "solo registros con EST = 'VIGENTE'. Hogares: suma de HOGARESCAT (hogares "
             "catastrados); las filas sin ese dato cuentan el campamento pero no hogares. "
             "Agregado por comuna: sin nombres, folios ni coordenadas."]
    if missing:
        notes.append("Nombres del MINVU sin calce en el índice territorial, omitidos: "
                     + ", ".join(sorted(set(missing))) + ".")
    return {"generated_at": fetched_at, "source": QUERY_URL,
            "source_url": SERVICE_URL, "license": LICENSE,
            "comunas": comunas, "notes": notes}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true",
                        help="vuelve a descargar la capa aunque haya caché")
    args = parser.parse_args()
    raw = download() if args.refresh or not RAW.exists() else json.loads(RAW.read_text(encoding="utf-8"))
    out = build(raw)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(out['comunas'])} comunas con campamentos vigentes "
          f"({sum(c['n_campamentos'] for c in out['comunas'])} campamentos) en {OUT.name}")


if __name__ == "__main__":
    main()

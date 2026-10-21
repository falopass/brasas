"""Incendios nominados ≥50 ha, temporadas 2002-2003 a 2023-2024 (OFI-19), para la vista Historia.

Fuente oficial: capa `PUNTOS_DE_INICIO_2002_2024_MAYOR_A_50_HA` del FeatureServer de CONAF-GEPRIF
(el hub público del Departamento de Estudios e Investigación, https://deigeprif.com), consulta
anónima verificada en `docs/research/fuentes-meteologix-geprif.md`. Los ítems de GEPRIF declaran
los datos «de uso público» con la obligación de citar a CONAF como fuente.

Uso:  python scripts/local/build_incendios_nominados.py [--refresh]

Determinista y reanudable: cada página cruda se guarda en `data/cache/geprif_puntos_inicio/`
(no se versiona) con su fecha de descarga; si ya existe, se reutiliza. `--refresh` vuelve a
descargarlas. El resultado sí se versiona: `web/data/incendios-nominados.json`.

La capa repite algunas claves nombre+temporada+comuna (focos distintos que recibieron el mismo
nombre, o el mismo punto registrado dos veces). Para la lista pública se publica una sola fila
por clave: la de mayor superficie registrada.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]

sys.path.insert(0, str(ROOT))

from scripts.nombres_comuna import VARIANTES  # noqa: E402

OUT = ROOT / "web" / "data" / "incendios-nominados.json"
CACHE = ROOT / "data" / "cache" / "geprif_puntos_inicio"

SERVICE_URL = "https://services5.arcgis.com/A1ELWse9bRAi2JiV/arcgis/rest/services/PUNTOS_DE_INICIO_2002_2024_MAYOR_A_50_HA/FeatureServer/0"
QUERY_URL = f"{SERVICE_URL}/query"
OUT_FIELDS = "Temporada,Región,Comuna,Nombre,Superficie,Inicio,Duración_"
PAGE = 2000  # maxRecordCount de la capa

SEASON_RE = re.compile(r"^(\d{4})-(\d{4})$")
SEASON_MIN, SEASON_MAX = 2002, 2023  # años de inicio de temporada válidos (2023-2024 es la última)

LICENSE = "Datos de uso público; citar a CONAF como fuente (declaración de los ítems ArcGIS de GEPRIF-DEI, https://deigeprif.com)"


def clean(text: object) -> str:
    """Texto sin espacios sobrantes (bordes y repeticiones internas)."""
    return " ".join(str(text or "").split())


def season_of(value: object) -> str | None:
    """Normaliza «2002-2003» y valida que sea una temporada del rango publicado."""
    m = SEASON_RE.match(clean(value))
    if not m or int(m.group(2)) != int(m.group(1)) + 1:
        return None
    return m.group(0) if SEASON_MIN <= int(m.group(1)) <= SEASON_MAX else None


def normalize(feature: dict) -> dict | None:
    """Un punto de la capa → fila del JSON, o None si le falta algo esencial.

    Coordenadas del punto en WGS84 (se piden con outSR=4326); la superficie queda con un
    decimal (0,1 ha = 1.000 m², más que suficiente para una lista nominal).
    """
    attr = feature.get("attributes") or {}
    geom = feature.get("geometry") or {}
    name, comuna = clean(attr.get("Nombre")), clean(attr.get("Comuna"))
    comuna = VARIANTES.get(comuna.upper(), comuna)
    season = season_of(attr.get("Temporada"))
    ha, lon, lat = attr.get("Superficie"), geom.get("x"), geom.get("y")
    if not (
        name and comuna and season and isinstance(ha, (int, float)) and isinstance(lon, (int, float)) and isinstance(lat, (int, float))
    ):
        return None
    return {
        "name": name,
        "comuna": comuna,
        "season": season,
        "ha": round(float(ha), 1),
        "lat": round(float(lat), 6),
        "lon": round(float(lon), 6),
    }


def dedupe(items: list[dict]) -> list[dict]:
    """Una fila por nombre+temporada+comuna: queda la de mayor superficie registrada."""
    best: dict[tuple[str, str, str], dict] = {}
    for item in items:
        key = (item["name"].upper(), item["season"], item["comuna"].upper())
        if key not in best or item["ha"] > best[key]["ha"]:
            best[key] = item
    return sorted(best.values(), key=lambda i: (i["season"], -i["ha"], i["name"], i["comuna"]))


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
        "resultRecordCount": str(PAGE),
        "resultOffset": str(offset),
        "f": "json",
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


def coverage_of(items: list[dict]) -> dict[str, str]:
    """Rango de temporadas que traen los datos, para que la nota y la vista no prometan más."""
    seasons = sorted({item["season"] for item in items})
    if not seasons:
        raise ValueError("sin temporadas: no hay nada que publicar")
    return {"from": seasons[0], "to": seasons[-1]}


def future_seasons(pages: list[dict]) -> dict[str, int]:
    """Temporadas válidas posteriores a SEASON_MAX en las páginas crudas, con su conteo.

    `season_of` las descarta sin distinguirlas de un dato mal escrito. Si la capa oficial
    crece, hay que decidir la fuente antes de publicar; el rango no se queda viejo callado.
    """
    found: dict[str, int] = {}
    for page in pages:
        for feature in page["features"]:
            m = SEASON_RE.match(clean((feature.get("attributes") or {}).get("Temporada")))
            if m and int(m.group(2)) == int(m.group(1)) + 1 and int(m.group(1)) > SEASON_MAX:
                found[m.group(0)] = found.get(m.group(0), 0) + 1
    return found


def build(pages: list[dict]) -> dict:
    """Páginas crudas → payload versionado, con deduplicación y nota de forma."""
    future = future_seasons(pages)
    if future:
        detalle = ", ".join(f"{season} ({n})" for season, n in sorted(future.items()))
        raise ValueError(
            f"la capa ya trae temporadas posteriores al rango publicado ({detalle}): decide la fuente y sube SEASON_MAX antes de regenerar"
        )
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
    items = dedupe(items)
    coverage = coverage_of(items)
    notes = [
        "Puntos de inicio de incendios de 50 ha o más registrados por CONAF-GEPRIF, "
        f"temporadas {coverage['from']} a {coverage['to']}. La superficie es la registrada en la capa "
        "para ese punto de inicio.",
        f"La capa repite algunas claves nombre+temporada+comuna ({rows - len(items)} "
        "registros): se publica una fila por clave, la de mayor superficie.",
    ]
    if skipped:
        notes.append(f"Se omitieron {skipped} registros sin nombre, comuna, temporada válida, superficie o coordenadas.")
    return {
        "source": {"name": "CONAF-GEPRIF", "url": QUERY_URL, "attribution": LICENSE, "fetched_at": fetched_at},
        "note": " ".join(notes),
        "coverage": coverage,
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
    print(
        f"{OUT.relative_to(ROOT)}: {len(result['items'])} incendios nominados "
        f"({sum(len(p['features']) for p in pages)} registros en la capa)"
    )


if __name__ == "__main__":
    main()

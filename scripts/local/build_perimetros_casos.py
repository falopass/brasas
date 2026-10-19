"""Perímetros oficiales de CONAF para los casos de Historia (CONT-08).

Fuente oficial: capa `PERÍMETROS_HISTORICOS_2014_2024_CON_SEMANA_DEL_AÑO`
(«COMPILADO OPERATIVO 2014-2025») del FeatureServer de CONAF-GEPRIF (el hub
público del Departamento de Estudios e Investigación, https://deigeprif.com),
consulta anónima verificada en `docs/research/fuentes-meteologix-geprif.md` y
detallada en `docs/investigacion/INV-03-perimetros.md`. Los ítems de GEPRIF
declaran los datos «de uso público» con la obligación de citar a CONAF.

Uso:  python scripts/local/build_perimetros_casos.py [--refresh]

Por cada caso de `web/data/cases.json` se consulta la capa con un filtro
espacial (envolvente del `bbox` del caso) y de temporada, y se emparejan los
polígonos con estas reglas:

- `Temporada` del polígono igual a la del caso (temporada de ocurrencia
  julio–junio: un incendio de febrero de 2023 es «2022-2023»).
- `inicio` dentro de `start_utc - DATE_PAD_DAYS` a `end_utc + DATE_PAD_DAYS`
  (tolerancia explícita: el inicio oficial puede ser días antes o después del
  primer dato satelital del caso).
- En casos de un solo incendio (`scope: fire`) se exige además que el nombre
  oficial comparta una palabra significativa con el título del caso, porque la
  envolvente suele cubrir incendios vecinos de la misma temporada (Las Máquinas
  2017 convive con Santa Cruz, La Palmilla, etc.). En complejos y episodios no
  se filtra por nombre: cada polígono es un foco distinto que se unió al caso.

Caso sin polígono que calce → no se escribe archivo ni se aproxima nada; queda
registrado en la salida del script y en INV-03.

Determinista y reanudable: la respuesta cruda por caso se guarda en
`data/cache/geprif_perimetros/` (no se versiona) con su fecha de descarga;
`--refresh` vuelve a descargarla. El resultado sí se versiona:
`web/data/cases/<case-id>.perimeter.json` (GeoJSON WGS84, simplificado en el
servidor con `maxAllowableOffset`, que consume `web/js/views/casos.js`).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
CASES_JSON = ROOT / "web" / "data" / "cases.json"
OUT_DIR = ROOT / "web" / "data" / "cases"
CACHE = ROOT / "data" / "cache" / "geprif_perimetros"

SERVICE_URL = (
    "https://services5.arcgis.com/A1ELWse9bRAi2JiV/arcgis/rest/services/PERÍMETROS_HISTORICOS_2014_2024_CON_SEMANA_DEL_AÑO/FeatureServer/0"
)
QUERY_URL = f"{SERVICE_URL}/query"
OUT_FIELDS = "FID,Nombre,Región,inicio,SEMANA,Temporada,HA,TIPOLOGÍA"
PAGE = 2000  # maxRecordCount típico de la capa
# Simplificación en grados de outSR 4326 según la escala del caso: un incendio único se mira
# de cerca (~50 m), un episodio regional se muestra a zoom país/región (~170 m) y junta
# decenas de polígonos; con menos detalle el JSON seguiría pesando varios MB.
SIMPLIFY_DEG = {"fire": 0.0005, "complex": 0.001, "episode": 0.002, "season": 0.004}
COORD_DECIMALS = 5  # ~1 m de precisión en el GeoJSON publicado
DATE_PAD_DAYS = 5  # tolerancia alrededor de start_utc/end_utc del caso

LICENSE = "Datos de uso público; citar a CONAF como fuente (declaración de los ítems ArcGIS de GEPRIF-DEI, https://deigeprif.com)"

# Palabras del título de un caso que no sirven para reconocer un incendio.
STOPWORDS = {"INCENDIO", "INCENDIOS", "MEGAINCENDIO", "FORESTAL", "GRAN", "GRANDE", "DE", "DEL", "EL", "LA", "LAS", "LOS", "EN", "Y"}
NAME_PREFIX_RE = re.compile(r"^\d+\s*-\s*")  # la capa nombra «320 - LAS MAQUINAS»


def clean(text: object) -> str:
    """Texto sin espacios sobrantes (bordes y repeticiones internas)."""
    return " ".join(str(text or "").split())


def norm_text(text: object) -> str:
    """Mayúsculas sin tildes, para comparar nombres («Las Máquinas» → «LAS MAQUINAS»)."""
    decomposed = unicodedata.normalize("NFD", clean(text))
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn").upper()


def tokens(text: object) -> set[str]:
    """Palabras significativas (≥4 letras, no genéricas ni números) de un nombre o título."""
    return {t for t in re.findall(r"[A-ZÑ]+", norm_text(text)) if len(t) >= 4 and t not in STOPWORDS}


def parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def season_of(moment: datetime) -> str:
    """Temporada de ocurrencia julio–junio: feb-2023 → «2022-2023», ago-2023 → «2023-2024»."""
    year = moment.year if moment.month >= 7 else moment.year - 1
    return f"{year}-{year + 1}"


def feature_name(props: dict) -> str:
    """Nombre oficial sin el correlativo «320 - » que antepone la capa."""
    return NAME_PREFIX_RE.sub("", clean(props.get("Nombre")))


def feature_start(props: dict) -> date | None:
    """Fecha de inicio oficial (la capa la guarda como fecha, milisegundos epoch)."""
    ms = props.get("inicio")
    if not isinstance(ms, (int, float)):
        return None
    return datetime.fromtimestamp(ms / 1000, timezone.utc).date()


def case_window(case: dict) -> tuple[date, date]:
    """Ventana explícita de empareje: inicio oficial dentro de [start-5d, end+5d]."""
    start = parse_utc(case["start_utc"]).date()
    end = parse_utc(case["end_utc"]).date()
    return start - timedelta(days=DATE_PAD_DAYS), end + timedelta(days=DATE_PAD_DAYS)


def matches(case: dict, props: dict) -> bool:
    """Un polígono de la capa pertenece al caso si cumple temporada + fecha (+ nombre en incendios únicos)."""
    if clean(props.get("Temporada")) != season_of(parse_utc(case["start_utc"])):
        return False
    start = feature_start(props)
    if start is None:
        return False
    since, until = case_window(case)
    if not (since <= start <= until):
        return False
    if case.get("scope") == "fire":
        return bool(tokens(case.get("title")) & tokens(feature_name(props)))
    return True


def round_ring(ring: list) -> list:
    return [[round(x, COORD_DECIMALS), round(y, COORD_DECIMALS)] for x, y in ring]


def round_geometry(geom: dict) -> dict | None:
    """Polygon/MultiPolygon con coordenadas redondeadas; otra cosa no sirve de perímetro."""
    if not isinstance(geom, dict):
        return None
    if geom.get("type") == "Polygon" and geom.get("coordinates"):
        return {"type": "Polygon", "coordinates": [round_ring(r) for r in geom["coordinates"]]}
    if geom.get("type") == "MultiPolygon" and geom.get("coordinates"):
        return {"type": "MultiPolygon", "coordinates": [[round_ring(r) for r in poly] for poly in geom["coordinates"]]}
    return None


def normalize(feature: dict) -> dict | None:
    """Feature de la capa (f=geojson) → feature publicable, o None si le falta lo esencial."""
    props = feature.get("properties") or {}
    geom = round_geometry(feature.get("geometry"))
    ha = props.get("HA")
    if geom is None or not isinstance(ha, (int, float)):
        return None
    return {
        "type": "Feature",
        "geometry": geom,
        "properties": {
            "fid": props.get("FID"),
            "nombre": feature_name(props),
            "region": clean(props.get("Región")),
            "inicio": feature_start(props).isoformat() if feature_start(props) else None,
            "temporada": clean(props.get("Temporada")),
            "ha": round(float(ha), 1),
            "tipologia": clean(props.get("TIPOLOGÍA")) or None,
        },
    }


def fetch_features(case: dict, refresh: bool) -> dict:
    """Candidatos del caso: envolvente del bbox ∩ temporada del caso; crudo cacheado en disco."""
    path = CACHE / f"{case['id']}.json"
    if path.exists() and not refresh:
        return json.loads(path.read_text(encoding="utf-8"))
    features, offset, exceeded = [], 0, True
    while exceeded:
        params = {
            "where": f"Temporada='{season_of(parse_utc(case['start_utc']))}'",
            "geometry": ",".join(str(v) for v in case["bbox"]),
            "geometryType": "esriGeometryEnvelope",
            "inSR": "4326",
            "spatialRel": "esriSpatialRelIntersects",
            "outFields": OUT_FIELDS,
            "returnGeometry": "true",
            "outSR": "4326",
            "maxAllowableOffset": str(SIMPLIFY_DEG.get(case.get("scope"), 0.001)),
            "geometryPrecision": str(COORD_DECIMALS),
            "resultRecordCount": str(PAGE),
            "resultOffset": str(offset),
            "f": "geojson",
        }
        response = httpx.get(QUERY_URL, params=params, timeout=90)
        response.raise_for_status()
        data = response.json()
        if "error" in data:
            sys.exit(f"La capa de GEPRIF respondió con error en {case['id']}: {data['error']}")
        page = data.get("features", [])
        features.extend(page)
        exceeded = bool(data.get("exceededTransferLimit")) or len(page) == PAGE
        offset += PAGE
    raw = {"fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "features": features}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return raw


def build_case(case: dict, raw: dict) -> dict | None:
    """Candidatos crudos → GeoJSON publicable del caso, o None si nada calza (no se inventa)."""
    matched = [f for f in raw["features"] if matches(case, f.get("properties") or {})]
    features = [f for f in (normalize(f) for f in matched) if f is not None]
    if not features:
        return None
    features.sort(key=lambda f: (f["properties"]["inicio"] or "", -f["properties"]["ha"]))
    since, until = case_window(case)
    return {
        "type": "FeatureCollection",
        "case_id": case["id"],
        "source": {
            "name": "CONAF — GEPRIF",
            "layer": "PERÍMETROS_HISTORICOS_2014_2024_CON_SEMANA_DEL_AÑO",
            "url": QUERY_URL,
            "attribution": LICENSE,
        },
        "license": LICENSE,
        "fetched_at": raw["fetched_at"],
        "match": {
            "temporada": season_of(parse_utc(case["start_utc"])),
            "inicio_desde": since.isoformat(),
            "inicio_hasta": until.isoformat(),
            "por_nombre": case.get("scope") == "fire",
            "simplificacion_deg": SIMPLIFY_DEG.get(case.get("scope"), 0.001),
        },
        "features": features,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--refresh", action="store_true", help="descargar la capa de nuevo")
    args = parser.parse_args()

    catalog = json.loads(CASES_JSON.read_text(encoding="utf-8"))
    matched, missed = [], []
    for case in catalog["cases"]:
        raw = fetch_features(case, args.refresh)
        result = build_case(case, raw)
        out = OUT_DIR / f"{case['id']}.perimeter.json"
        if result is None:
            missed.append((case["id"], len(raw["features"])))
            if out.exists():
                out.unlink()  # la capa ya no ofrece un perímetro que calce: el archivo sobra
            continue
        out.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
        ha = sum(f["properties"]["ha"] for f in result["features"])
        matched.append((case["id"], len(result["features"]), ha))

    for cid, n, ha in matched:
        print(f"{cid}: {n} perímetro(s) oficial(es), {ha:,.0f} ha")
    for cid, n in missed:
        print(f"{cid}: sin perímetro oficial que calce ({n} candidatos en el bbox/temporada)")
    print(f"{len(matched)} caso(s) con perímetro, {len(missed)} sin perímetro")


if __name__ == "__main__":
    main()

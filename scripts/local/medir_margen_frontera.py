"""Cuántos focos entran por el margen de 0,16° de la frontera (QA-75).

El filtro territorial de FIRMS acepta un punto si cae dentro de una comuna o a menos de
0,16° de una (unos 18 km en latitud). La tolerancia existe por la costa simplificada y los
fiordos, pero aplicada a la frontera también admite focos de Argentina, Bolivia y Perú.
Este script mide, sobre las observaciones que BRASA ya guardó, la distancia de cada punto
al territorio chileno y la reparte en tramos, por fuente. No cambia el filtro: mide y
propone.

La distancia se calcula contra la unión de las comunas (BCN) con ``Point.distance`` en
grados y se convierte a km con la latitud del punto. La base se copia a un temporal y se
abre en solo lectura. Sin red.

Uso:  python scripts/local/medir_margen_frontera.py [--db data/demo/work.db]
        [--json observaciones.json] [--limit N] [--md docs/investigacion/INV-28-margen-frontera.md]
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import sqlite3
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterator

from shapely import make_valid, prepare
from shapely.geometry import Point
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.geo import territory  # noqa: E402

KM_PER_DEG = 111.32
BANDS = ("dentro", "0–1", "1–2", "2–5", "5–10", "10–18", "más de 18 km")
SOURCE_ORDER = ("GOES19_FDCF", "GOES16_FDCF", "VIIRS_*", "MODIS_*")
EMPTY = "No hay detecciones que medir."


def band(km: float) -> str:
    """Tramo de distancia en km. Los límites superiores son inclusivos."""
    if km <= 0:
        return BANDS[0]
    for limit, name in ((1, "0–1"), (2, "1–2"), (5, "2–5"), (10, "5–10"), (18, "10–18")):
        if km <= limit:
            return name
    return BANDS[-1]


def source_group(source: str) -> str:
    """GOES por producto exacto; VIIRS y MODIS agrupados, que son varios productos."""
    source = (source or "").strip()
    if source.startswith("VIIRS"):
        return "VIIRS_*"
    if source.startswith("MODIS"):
        return "MODIS_*"
    return source or "(sin fuente)"


@lru_cache(maxsize=1)
def _union():
    """Unión de las comunas, preparada para consultas rápidas de cobertura."""
    geom = unary_union([make_valid(g) for g in territory()._geoms])
    prepare(geom)
    return geom


def distance_km(lat: float, lon: float) -> float:
    """Distancia al territorio en km, con la escala de longitud de la latitud del punto."""
    point = Point(lon, lat)
    union = _union()
    if union.covers(point):
        return 0.0
    return union.distance(point) * KM_PER_DEG * math.cos(math.radians(lat))


def _assigned_comuna(row: dict[str, Any], lat: float, lon: float) -> tuple[int | None, str | None]:
    """Comuna guardada; si falta, la que asignaría el filtro con 0,16°."""
    code = row.get("comuna_code")
    if code is not None:
        try:
            comuna = territory().by_code.get(int(code))
        except (TypeError, ValueError):
            comuna = None
        if comuna:
            return comuna.code, comuna.name
    hit = territory().locate(lat, lon, tolerance_deg=0.16)
    return (hit.code, hit.name) if hit else (None, None)


def measure(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Histograma por fuente y los diez puntos más alejados."""
    by_source: dict[str, dict[str, int]] = {}
    points = []
    for row in rows:
        lat, lon = float(row["lat"]), float(row["lon"])
        km = distance_km(lat, lon)
        source = source_group(str(row.get("source") or ""))
        counts = by_source.setdefault(source, dict.fromkeys(BANDS, 0))
        counts[band(km)] += 1
        code, name = _assigned_comuna(row, lat, lon)
        points.append({"source": source, "lat": lat, "lon": lon, "distance_km": round(km, 1), "comuna_code": code, "comuna": name})
    top = sorted(points, key=lambda p: (-p["distance_km"], p["lat"], p["lon"]))[:10]
    return {"total": len(rows), "by_source": by_source, "top": top}


def _table(result: dict[str, Any]) -> list[str]:
    lines = ["| Fuente | " + " | ".join(BANDS) + " | Total |", "|---|" + "---:|" * (len(BANDS) + 1)]
    for source in sorted(result["by_source"], key=lambda s: (SOURCE_ORDER.index(s) if s in SOURCE_ORDER else 99, s)):
        counts = result["by_source"][source]
        lines.append(f"| {source} | " + " | ".join(str(counts[b]) for b in BANDS) + f" | {sum(counts.values())} |")
    totals = {b: sum(c[b] for c in result["by_source"].values()) for b in BANDS}
    lines.append("| **Total** | " + " | ".join(str(totals[b]) for b in BANDS) + f" | {result['total']} |")
    return lines


def _top_table(result: dict[str, Any]) -> list[str]:
    lines = ["| # | Fuente | Lat | Lon | km | Comuna |", "|---:|---|---:|---:|---:|---|"]
    for i, point in enumerate(result["top"], 1):
        lines.append(
            f"| {i} | {point['source']} | {point['lat']:.4f} | {point['lon']:.4f} | "
            f"{point['distance_km']:.1f} | {point['comuna'] or '(sin comuna)'} |"
        )
    return lines


def render(result: dict[str, Any]) -> str:
    lines = [f"Margen de frontera — {result['total']} detecciones · {result['source']}", ""]
    lines += _table(result)
    lines += ["", "Diez puntos más alejados:", ""]
    lines += _top_table(result)
    return "\n".join(lines)


def _reading(result: dict[str, Any]) -> list[str]:
    counts = {b: sum(c[b] for c in result["by_source"].values()) for b in BANDS}
    outside = result["total"] - counts["dentro"]
    within = sum(counts[b] for b in BANDS[1:6])
    beyond = counts[BANDS[-1]]
    lines = [f"- Total: {result['total']} detecciones."]
    if outside:
        lines.append(f"- Fuera del territorio: {outside} ({100 * outside / result['total']:.1f}%).")
        lines.append(f"- Dentro del margen de 18 km: {within}.")
        lines.append(f"- Más de 18 km: {beyond}.")
        source, source_counts = max(result["by_source"].items(), key=lambda kv: sum(v for b, v in kv[1].items() if b != "dentro"))
        n_source = sum(v for b, v in source_counts.items() if b != "dentro")
        lines.append(f"- La fuente con más detecciones fuera del territorio es `{source}` ({n_source} de {sum(source_counts.values())}).")
    else:
        lines.append("- No hay detecciones fuera del territorio en esta muestra: el margen no se puede medir con estos datos.")
    if result.get("demo"):
        lines.append("- Base de demo: el número no es representativo; repetir contra producción.")
    return lines


def render_markdown(result: dict[str, Any]) -> str:
    limit = f" · `--limit {result['limit']}` (las más recientes)" if result.get("limit") else ""
    lines = [
        "# INV-28 · Margen de 0,16° en la frontera: cuántos focos entran",
        "",
        f"> **Fecha:** {result['generated'][:10]}. **Fuente:** `{result['source']}`{limit}. "
        "**No se cambió el filtro:** `COASTAL_TOLERANCE_DEG = 0,16` sigue igual.",
        "",
    ]
    if result.get("demo"):
        lines += [
            "> **Medido sobre la base de demo; repetir contra producción.** La base de demo tiene "
            "un solo incidente de ejemplo en Quilpué, así que no alcanza para medir la frontera. "
            "El número que decide es el de `data/work.db` o un respaldo de producción.",
            "",
        ]
    lines += [
        "## Metodología",
        "",
        "Para cada detección de `work.observations` (o de la lista JSON):",
        "",
        "1. Se calcula la distancia al territorio chileno como la distancia euclidiana en grados "
        "entre el punto y la unión de las comunas BCN (`unary_union` + `Point.distance`).",
        "2. Se convierte a km con la latitud del punto: `111,32 × cos(lat)` km por grado. Es la "
        "escala local de longitud; la frontera corre de norte a sur, que es la dirección que importa.",
        "3. Se clasifica en tramos: `dentro` (0 km), `0–1`, `1–2`, `2–5`, `5–10`, `10–18` y `más de 18 km`.",
        "4. La comuna del listado es la guardada en `comuna_code`; si es null, se muestra la que asignaría el filtro con 0,16°.",
        "",
        "Sin red: la base se copia a un temporal y se abre en solo lectura. `--limit N` mide las N "
        "filas más recientes (en el JSON, las primeras N).",
        "",
        "## Resultado",
        "",
    ]
    lines += _table(result)
    lines += ["", "### Los diez puntos más alejados", ""]
    lines += _top_table(result)
    lines += ["", "## Lectura", ""]
    lines += _reading(result)
    lines += [
        "",
        "## Tres recomendaciones",
        "",
        "### 1. Dejar la tolerancia en 0,16° y marcar el borde",
        "",
        "**Qué se gana:** no se pierde ninguna isla, fiordo ni píxel costero; la ingesta no cambia "
        "y el borde queda medido y visible para decidir después.",
        "",
        "**Qué se pierde:** los focos de Argentina, Bolivia y Perú siguen entrando y contándose "
        "como chilenos; el número no baja, solo se etiqueta.",
        "",
        "### 2. Bajarla a 0,03° (~3,3 km)",
        "",
        "**Qué se gana:** corta la mayor parte de la franja: los focos a más de ~3 km del "
        "territorio dejan de entrar, y con ellos buena parte del ruido extranjero.",
        "",
        "**Qué se pierde:** la costa simplificada y los fiordos del sur vuelven a perder píxeles "
        "válidos; islas pequeñas y bordes costeros pueden quedar fuera. Antes de adoptarla hay "
        "que revisar la costa, que es la razón original de la tolerancia.",
        "",
        "### 3. Separar la tolerancia de costa y de frontera",
        "",
        "**Qué se gana:** 0,16° donde hace falta (costa, fiordos, islas) y 0,03° en el borde "
        "terrestre; conserva lo bueno de las dos anteriores.",
        "",
        "**Qué se pierde:** más complejidad: hace falta una geometría de frontera o una prueba de "
        "distancia al borde terrestre, mantenerla y probarla; hay riesgo de error en los tripoints "
        "y en la costa-frontera del sur.",
        "",
        "La decisión no se toma en este informe: el filtro queda intacto.",
        "",
        "## Cómo repetir contra producción",
        "",
        "```bash",
        "python scripts/local/medir_margen_frontera.py --db data/work.db \\",
        "    --md docs/investigacion/INV-28-margen-frontera.md",
        "```",
        "",
        "Con un respaldo de producción, `--db respaldo-work.db`. Para una muestra rápida, `--limit 50000`.",
        "",
        "## Límites",
        "",
        "- La distancia se mide al polígono de comunas BCN, no a la línea internacional: la "
        "generalización del polígono puede dejar dentro puntos que en el terreno son argentinos, "
        "y al revés.",
        "- La conversión `111,32 × cos(lat)` es la escala de longitud; para puntos al norte o al "
        "sur del territorio subestima la distancia (hasta ~5% en el extremo norte y más en el "
        "sur). Los tramos son gruesos, así que el efecto no cambia la lectura.",
        "- `comuna_code` se guarda con la tolerancia por omisión de `Territory.locate` (0,01°), "
        "no con 0,16°; por eso muchos puntos del margen quedan sin comuna guardada. El listado "
        "muestra la comuna que asignaría el filtro.",
        "- La base de demo no alcanza: hay que repetir contra producción.",
        "",
    ]
    return "\n".join(lines)


def _copy_db(src: Path, dst: Path) -> None:
    """Copia consistente vía la API de respaldo de SQLite (sirve aunque el origen esté en WAL)."""
    source = sqlite3.connect(src, timeout=30)
    try:
        with sqlite3.connect(dst) as target:
            source.backup(target)
    finally:
        source.close()


@contextmanager
def open_readonly(db_path: Path) -> Iterator[sqlite3.Connection]:
    """Copia work.db a un temporal y la abre en solo-lectura."""
    tmp = Path(tempfile.mkdtemp(prefix="brasa-margen-"))
    conn = None
    try:
        _copy_db(db_path, tmp / "work.db")
        conn = sqlite3.connect(f"file:{tmp / 'work.db'}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        yield conn
    finally:
        if conn is not None:
            conn.close()
        shutil.rmtree(tmp, ignore_errors=True)


def load_db(db_path: Path, limit: int | None = None) -> tuple[list[dict[str, Any]], bool]:
    """Filas de observaciones, de la más reciente a la más antigua. ``demo`` si es la base de ejemplo."""
    sql = "SELECT id, source, lat, lon, comuna_code FROM observations ORDER BY observed_at DESC"
    params: list[Any] = []
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    with open_readonly(db_path) as conn:
        rows = [dict(row) for row in conn.execute(sql, params)]
    demo = "demo" in db_path.parts or any(str(row.get("id") or "").startswith("demo:") for row in rows)
    return rows, demo


def load_json(path: Path, limit: int | None = None) -> list[dict[str, Any]]:
    """Lista de observaciones en JSON: ``[{"source": ..., "lat": ..., "lon": ...}, ...]``."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("el JSON debe ser una lista de observaciones")
    rows = []
    for item in data[:limit] if limit else data:
        if not isinstance(item, dict):
            continue
        try:
            lat, lon = float(item["lat"]), float(item["lon"])
        except (KeyError, TypeError, ValueError):
            continue
        rows.append(
            {
                "id": item.get("id"),
                "source": item.get("source") or "(sin fuente)",
                "lat": lat,
                "lon": lon,
                "comuna_code": item.get("comuna_code"),
            }
        )
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--db", default="data/demo/work.db", help="ruta a work.db (se copia y se abre en solo lectura; por omisión data/demo/work.db)"
    )
    group.add_argument("--json", metavar="RUTA", help="lista de observaciones en JSON, en vez de --db")
    parser.add_argument("--md", metavar="RUTA", help="escribe el informe Markdown en esta ruta")
    parser.add_argument("--limit", type=int, metavar="N", help="mide solo las primeras N filas (en la base, las más recientes)")
    args = parser.parse_args(argv)
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit debe ser mayor que 0")
    if args.json:
        path = Path(args.json)
        if not path.exists():
            print(f"No existe {path}.", file=sys.stderr)
            return 2
        try:
            rows = load_json(path, args.limit)
        except (OSError, ValueError) as exc:
            print(f"No se pudo leer {path}: {exc}", file=sys.stderr)
            return 2
        demo, source = False, str(path)
    else:
        db_path = Path(args.db)
        if not db_path.exists():
            print(f"No existe {db_path} (corre la ingesta primero o pasa --db).", file=sys.stderr)
            return 2
        try:
            rows, demo = load_db(db_path, args.limit)
        except sqlite3.DatabaseError as exc:
            print(f"No se pudo leer la base ({exc}). ¿Es una copia de work.db?", file=sys.stderr)
            return 2
        source = str(db_path)
    if not rows:
        print(EMPTY, file=sys.stderr)
        return 0
    result = measure(rows)
    result.update(
        {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "source": source, "limit": args.limit, "demo": demo}
    )
    print(render(result))
    if args.md:
        out = Path(args.md)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render_markdown(result), encoding="utf-8")
        print(f"\nInforme escrito en {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

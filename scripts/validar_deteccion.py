"""Validación de la detección contra los incendios informados por CONAF (QA-03).

Responde con números: qué porcentaje de los incendios del reporte público de CONAF (GEPRIF)
detectó BRASA, por tramo de superficie, y con cuántos minutos de ventaja o atraso frente a la
hora de detección oficial (``detected_at`` = ``f_deteccion``). Además cuenta los incidentes
abiertos («anomalia»/«posible») sin un incendio de CONAF cerca: son candidatos a falso positivo
—pueden ser quemas autorizadas, industria o incendios aún no informados—, no una condena.

La base se copia a un directorio temporal con la API de respaldo de SQLite y la copia se abre en
modo solo-lectura: jamás se escribe en el original y sirve aunque esté en WAL. Sin red.
Solo usa la biblioteca estándar: corre con cualquier Python 3.10+.

Uso:  python scripts/validar_deteccion.py --db data/demo/brasa.db [--season 2025-2026] [--km 10] [--hours 6] [--json]
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
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

EARTH_RADIUS_KM = 6371.0088
HOURS_BEFORE = 6                        # ventana fija hacia atrás: BRASA suele ver el foco antes del reporte
OPEN_STATES = ("anomalia", "posible")   # sin confirmación oficial: los únicos que pueden sobrar
TRAMOS = ("<1 ha", "1-10 ha", "10-100 ha", ">100 ha", "sin superficie")
NO_DATA = "No hay incendios con hora de detección para esa temporada."
CANDIDATES_NOTE = ("candidatos a falso positivo: pueden ser quemas autorizadas, fuentes de calor "
                   "industriales o incendios aún no informados por CONAF")


def parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def stamp(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    # Misma fórmula que backend/geo.py, copiada para no exigir shapely al correr el script.
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def tramo(area: float | None) -> str:
    if area is None:
        return "sin superficie"
    if area < 1:
        return "<1 ha"
    if area < 10:
        return "1-10 ha"
    if area <= 100:
        return "10-100 ha"
    return ">100 ha"


def percentile(values: list[float], p: float) -> float | None:
    """Percentil p (0-100) por interpolación lineal; None si no hay datos."""
    if not values:
        return None
    ordered = sorted(values)
    k = (len(ordered) - 1) * p / 100
    low = int(k)
    if low >= len(ordered) - 1:
        return ordered[-1]
    return ordered[low] + (ordered[low + 1] - ordered[low]) * (k - low)


def _copy_db(src: Path, dst: Path) -> None:
    """Copia consistente vía la API de respaldo de SQLite (sirve aunque el origen esté en uso)."""
    source = sqlite3.connect(src, timeout=30)
    try:
        with sqlite3.connect(dst) as target:
            source.backup(target)
    finally:
        source.close()


@contextmanager
def open_readonly(db_path: Path) -> Iterator[sqlite3.Connection]:
    """Copia brasa.db y work.db a un temporal y las abre en solo-lectura (work adjunta)."""
    tmp = Path(tempfile.mkdtemp(prefix="brasa-validar-"))
    conn = None
    try:
        main_copy = tmp / "brasa.db"
        _copy_db(db_path, main_copy)
        work_path = db_path.with_name("work.db")
        conn = sqlite3.connect(f"file:{main_copy}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        if work_path.exists():
            work_copy = tmp / "work.db"
            _copy_db(work_path, work_copy)
            conn.execute("ATTACH DATABASE ? AS work", (f"file:{work_copy}?mode=ro",))
        yield conn
    finally:
        if conn is not None:
            conn.close()
        shutil.rmtree(tmp, ignore_errors=True)


def fires(conn: sqlite3.Connection, season: str | None) -> list[dict[str, Any]]:
    sql = ("SELECT id, name, area_ha, lat, lon, detected_at, season FROM official_fires "
           "WHERE detected_at IS NOT NULL")
    params: list[Any] = []
    if season:
        sql += " AND season = ?"
        params.append(season)
    return [dict(row) for row in conn.execute(sql, params)]


def first_observation(conn: sqlite3.Connection, fire: dict[str, Any], km: float, hours: float) -> str | None:
    """Primera observación a ≤ km del incendio, dentro de [detección −6 h, detección +hours h]."""
    detected = parse_utc(fire["detected_at"])
    lo = stamp(detected - timedelta(hours=HOURS_BEFORE))
    hi = stamp(detected + timedelta(hours=hours))
    pad_lat = km / 111.0
    pad_lon = km / (111.0 * max(math.cos(math.radians(fire["lat"])), 0.01))
    rows = conn.execute(
        "SELECT observed_at, lat, lon FROM observations "
        "WHERE observed_at >= ? AND observed_at <= ? AND lat BETWEEN ? AND ? AND lon BETWEEN ? AND ? "
        "ORDER BY observed_at",
        (lo, hi, fire["lat"] - pad_lat, fire["lat"] + pad_lat,
         fire["lon"] - pad_lon, fire["lon"] + pad_lon))
    for row in rows:
        if haversine_km(fire["lat"], fire["lon"], row["lat"], row["lon"]) <= km:
            return row["observed_at"]
    return None


def count_candidates(conn: sqlite3.Connection, km: float) -> tuple[int, int]:
    """Incidentes abiertos y cuántos no tienen ningún incendio de CONAF a ≤ km."""
    official = conn.execute("SELECT lat, lon FROM official_fires").fetchall()
    open_incidents = conn.execute(
        f"SELECT id, lat, lon FROM incidents WHERE status IN ({','.join('?' * len(OPEN_STATES))})",
        OPEN_STATES).fetchall()
    far = sum(1 for inc in open_incidents
              if all(haversine_km(inc["lat"], inc["lon"], f["lat"], f["lon"]) > km for f in official))
    return len(open_incidents), far


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    detected = [r["ventaja_min"] for r in rows if r["detectado"]]
    return {"n": len(rows), "detectados": len(detected),
            "pct": round(100 * len(detected) / len(rows)) if rows else 0,
            "p50_min": percentile(detected, 50), "p90_min": percentile(detected, 90)}


def validate(db_path: Path, season: str | None = None, km: float = 10, hours: float = 6) -> dict[str, Any] | None:
    """Calcula la validación completa; None si no hay incendios con hora de detección."""
    with open_readonly(db_path) as conn:
        results = []
        for fire in fires(conn, season):
            first = first_observation(conn, fire, km, hours)
            ventaja = (round((parse_utc(first) - parse_utc(fire["detected_at"])).total_seconds() / 60, 1)
                       if first else None)
            results.append({**fire, "detectado": first is not None, "ventaja_min": ventaja})
        if not results:
            return None
        open_n, candidates = count_candidates(conn, km)
    by_season: dict[str, list[dict[str, Any]]] = {}
    for r in results:
        by_season.setdefault(r["season"] or "sin temporada", []).append(r)
    return {
        "temporada": season, "km": km, "horas_antes": HOURS_BEFORE, "horas_despues": hours,
        "tramos": [{"tramo": t, **_summary([r for r in results if tramo(r["area_ha"]) == t])} for t in TRAMOS],
        "resumen": _summary(results),
        "por_temporada": [{"temporada": s, **_summary(rs)} for s, rs in sorted(by_season.items())],
        "incidentes_abiertos": open_n,
        "candidatos_falso_positivo": candidates,
        "incendios": results,
    }


def _fmt(value: float | None) -> str:
    return f"{value:g}" if value is not None else "—"


def render(result: dict[str, Any]) -> str:
    lines = [f"Temporada: {result['temporada'] or 'todas'} · radio: {result['km']:g} km · "
             f"ventana: detección CONAF −{result['horas_antes']:g} h a +{result['horas_despues']:g} h", ""]
    lines += ["| Tramo | Incendios | Detectados | % | ventaja p50 (min) | ventaja p90 (min) |",
              "|---|---:|---:|---:|---:|---:|"]
    for t in result["tramos"]:
        pct = f"{t['pct']}%" if t["n"] else "—"
        lines.append(f"| {t['tramo']} | {t['n']} | {t['detectados']} | {pct} | "
                     f"{_fmt(t['p50_min'])} | {_fmt(t['p90_min'])} |")
    total = result["resumen"]
    lines.append(f"| **Total** | {total['n']} | {total['detectados']} | {total['pct']}% | "
                 f"{_fmt(total['p50_min'])} | {_fmt(total['p90_min'])} |")
    lines += ["", "Ventaja = primera observación BRASA − detección CONAF, en minutos "
              "(negativo = BRASA llegó antes)."]
    for s in result["por_temporada"]:
        lines.append(f"Resumen {s['temporada']}: {s['detectados']}/{s['n']} detectados ({s['pct']}%)"
                     f" · mediana {_fmt(s['p50_min'])} min · p90 {_fmt(s['p90_min'])} min")
    lines.append(f"Incidentes abiertos («posible»/«anomalía»): {result['incidentes_abiertos']} · "
                 f"sin incendio de CONAF a ≤ {result['km']:g} km: {result['candidatos_falso_positivo']} "
                 f"({CANDIDATES_NOTE})")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", default="data/brasa.db", help="ruta a brasa.db (se abre en solo lectura)")
    parser.add_argument("--season", help="temporada a evaluar, por ejemplo 2025-2026 (por omisión: todas)")
    parser.add_argument("--km", type=float, default=10, help="radio de correspondencia en km (por omisión 10)")
    parser.add_argument("--hours", type=float, default=6,
                        help="horas hacia adelante de la detección oficial (por omisión 6; hacia atrás siempre 6)")
    parser.add_argument("--json", action="store_true", help="imprime el resultado en JSON")
    args = parser.parse_args(argv)
    db_path = Path(args.db)
    if not db_path.exists():
        print(f"No existe {db_path}.", file=sys.stderr)
        return 2
    try:
        result = validate(db_path, args.season, args.km, args.hours)
    except sqlite3.OperationalError as exc:
        print(f"No se pudo leer la base ({exc}). ¿Existe work.db junto a {db_path}?", file=sys.stderr)
        return 2
    if result is None:
        print(NO_DATA, file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())

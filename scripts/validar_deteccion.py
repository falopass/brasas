"""Validación de la detección contra los incendios informados por CONAF (QA-03).

Responde con números la pregunta central del proyecto: qué porcentaje de los incendios del
reporte público de CONAF (GEPRIF) detectó BRASA, por tramo de superficie, y con cuántos
minutos de ventaja o atraso frente a la hora de detección (``detected_at`` = ``f_deteccion``)
y de aviso (``alerted_at`` = ``f_aviso``) oficiales. Además cuenta los incidentes abiertos
(«anomalia»/«posible») sin un incendio de CONAF cerca: son candidatos a falsa alarma —pueden
ser quemas autorizadas, industria o incendios aún no informados—, no una condena. Los resume
por región del territorio BCN (DET-08) para decidir con datos si hace falta un umbral o una
máscara regional, por ejemplo en el norte.

La base se copia a un directorio temporal con la API de respaldo de SQLite y la copia se abre
en modo solo-lectura: jamás se escribe en el original y sirve aunque esté en WAL. Sin red.

Uso:  python scripts/validar_deteccion.py --db work.db [--km 3] [--before-h 24] [--after-h 6] [--json salida.json]
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
import tempfile
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.geo import haversine_km, territory  # noqa: E402
from scripts.nombres_comuna import normalizar  # noqa: E402

TRAMOS = ("<1 ha", "1-10 ha", "10-100 ha", ">=100 ha", "sin superficie")
OPEN_STATES = ("anomalia", "posible")  # sin confirmación oficial: los únicos que pueden sobrar
CAND_KM, CAND_H = 5.0, 24.0  # «posible» sin CONAF a ≤ 5 km en ±24 h: candidato a falsa alarma
NO_REGION = "sin región"  # el punto no cayó en ninguna comuna del territorio BCN
NO_DATA = "No hay incendios de CONAF en la base."


def parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def stamp(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def tramo(area: float | None) -> str:
    if area is None:
        return "sin superficie"
    if area < 1:
        return "<1 ha"
    if area < 10:
        return "1-10 ha"
    if area < 100:
        return "10-100 ha"
    return ">=100 ha"


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


def _stats(values: list[float]) -> dict[str, Any]:
    return {"n": len(values), "p50": percentile(values, 50), "p90": percentile(values, 90)}


@contextmanager
def open_work_copy(db_path: Path) -> Iterator[sqlite3.Connection]:
    """Copia work.db a un temporal (API de respaldo: sirve aunque esté en WAL) y la abre en solo-lectura."""
    tmp = Path(tempfile.mkdtemp(prefix="brasa-validar-"))
    conn = None
    try:
        copy = tmp / "work.db"
        source = sqlite3.connect(db_path, timeout=30)
        try:
            with sqlite3.connect(copy) as target:
                source.backup(target)
        finally:
            source.close()
        conn = sqlite3.connect(f"file:{copy}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        yield conn
    finally:
        if conn is not None:
            conn.close()
        shutil.rmtree(tmp, ignore_errors=True)


def load_fires(conn: sqlite3.Connection, season: str | None) -> list[dict[str, Any]]:
    sql = "SELECT id, name, status, started_at, detected_at, alerted_at, area_ha, lat, lon, comuna, region, season FROM official_fires"
    params: tuple = ()
    if season:
        sql += " WHERE season = ?"
        params = (season,)
    rows = conn.execute(sql + " ORDER BY started_at", params).fetchall()
    fires = [dict(row) for row in rows]
    for fire in fires:
        # Ancla de la ventana: f_deteccion cuando CONAF la informa; si falta, f_inicio.
        fire["anchor_kind"] = "detected_at" if fire["detected_at"] else "started_at"
        fire["anchor_dt"] = parse_utc(fire["detected_at"] or fire["started_at"])
    return fires


def load_incidents(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Cada incidente con su primera detección: la más antigua de sus observaciones enlazadas
    (o ``first_seen_at`` si no tiene enlaces, por ejemplo en un respaldo antiguo)."""
    rows = conn.execute(
        "SELECT i.id, i.status, i.lat, i.lon, i.first_seen_at, MIN(o.observed_at) AS first_obs_at "
        "FROM incidents i "
        "LEFT JOIN incident_observations io ON io.incident_id = i.id "
        "LEFT JOIN observations o ON o.id = io.observation_id "
        "GROUP BY i.id"
    ).fetchall()
    incidents = []
    for row in rows:
        inc = dict(row)
        inc["first_at"] = inc["first_obs_at"] or inc["first_seen_at"]
        inc["first_dt"] = parse_utc(inc["first_at"])
        incidents.append(inc)
    return incidents


def resolve_comunas(fires: list[dict[str, Any]]) -> list[str]:
    """Nombre de comuna de CONAF → código territorial (coincidencia exacta tras normalizar).

    ``normalizar`` aplica las variantes conocidas de las fuentes («MARCHIHUE» = Marchigüe)
    antes de comparar. Asigna ``comuna_code`` en cada fila y devuelve los nombres que no
    resolvieron (o que resolvieron a más de una comuna): la fila no se descarta, solo queda
    sin código.
    """
    names = {f["comuna"] for f in fires if f["comuna"]}
    missing: set[str] = set()
    try:
        terr = territory()
    except Exception:  # sin web/data/comunas.geojson (por ejemplo, corriendo fuera del repo)
        terr = None
    for name in sorted(names):
        found = terr.comunas_named(normalizar(name)) if terr is not None else []
        if len(found) == 1:
            for fire in fires:
                if fire["comuna"] == name:
                    fire["comuna_code"] = found[0].code
        else:
            missing.add(name)
    return sorted(missing)


def match_fire(
    fire: dict[str, Any], incidents: list[dict[str, Any]], km: float, before_h: float, after_h: float
) -> tuple[dict[str, Any], float] | None:
    """El incidente con primera detección más temprana a ≤ km, dentro de
    [ancla − before_h, ancla + after_h]."""
    lo = fire["anchor_dt"] - timedelta(hours=before_h)
    hi = fire["anchor_dt"] + timedelta(hours=after_h)
    best: tuple[dict[str, Any], float] | None = None
    for inc in incidents:
        if not lo <= inc["first_dt"] <= hi:
            continue
        dist = haversine_km(fire["lat"], fire["lon"], inc["lat"], inc["lon"])
        if dist <= km and (best is None or inc["first_dt"] < best[0]["first_dt"]):
            best = (inc, dist)
    return best


def count_candidates(incidents: list[dict[str, Any]], fires: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Incidentes «anomalia»/«posible» sin incendio de CONAF a ≤ CAND_KM en ±CAND_H.

    Es un proxy de falsa alarma: quemas autorizadas, calor industrial o focos que CONAF
    aún no informa también entran aquí.
    """
    span = timedelta(hours=CAND_H)
    out = []
    for inc in incidents:
        if inc["status"] not in OPEN_STATES:
            continue
        near = any(
            haversine_km(inc["lat"], inc["lon"], f["lat"], f["lon"]) <= CAND_KM and abs(inc["first_dt"] - f["anchor_dt"]) <= span
            for f in fires
        )
        if not near:
            out.append(inc)
    return out


def candidates_by_region(incidents: list[dict[str, Any]], candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Resumen por región (DET-08): para cada región del territorio BCN, cuántos incidentes
    abiertos tiene, cuántos quedaron sin CONAF cerca y la tasa, más las 3 comunas con más casos.

    La región se obtiene ubicando el punto del incidente con ``territory().locate``; lo que no
    cae en comuna chilena (mar, altiplano fuera del país) queda en «sin región». Lista vacía
    cuando no hay incidentes abiertos: es «sin datos», no un cero.
    """
    try:
        terr = territory()
    except Exception:  # sin web/data/comunas.geojson (por ejemplo, corriendo fuera del repo)
        terr = None
    cand_ids = {c["id"] for c in candidates}
    buckets: dict[str, dict[str, Any]] = {}
    for inc in incidents:
        if inc["status"] not in OPEN_STATES:
            continue
        comuna = terr.locate(inc["lat"], inc["lon"]) if terr is not None else None
        bucket = buckets.setdefault(comuna.region if comuna else NO_REGION, {"abiertos": 0, "candidatos": 0, "comunas": {}})
        bucket["abiertos"] += 1
        if inc["id"] in cand_ids:
            bucket["candidatos"] += 1
            if comuna is not None:
                bucket["comunas"][comuna.name] = bucket["comunas"].get(comuna.name, 0) + 1
    out = [
        {
            "region": region,
            "abiertos": b["abiertos"],
            "candidatos": b["candidatos"],
            "pct": round(100 * b["candidatos"] / b["abiertos"]),
            "top_comunas": [{"comuna": n, "n": c} for n, c in sorted(b["comunas"].items(), key=lambda kv: (-kv[1], kv[0]))[:3]],
        }
        for region, b in buckets.items()
    ]
    out.sort(key=lambda r: (-r["candidatos"], -r["pct"], r["region"]))
    return out


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    detected = [r for r in rows if r["detected"]]
    return {"n": len(rows), "detectados": len(detected), "pct": round(100 * len(detected) / len(rows)) if rows else 0}


def validate(
    db_path: Path, km: float = 3.0, before_h: float = 24.0, after_h: float = 6.0, season: str | None = None
) -> dict[str, Any] | None:
    """Calcula la validación completa sobre una copia de work.db; None si no hay incendios."""
    with open_work_copy(db_path) as conn:
        fires = load_fires(conn, season)
        incidents = load_incidents(conn)
    if not fires:
        return None
    unmatched = resolve_comunas(fires)
    for fire in fires:
        hit = match_fire(fire, incidents, km, before_h, after_h)
        fire["detected"] = hit is not None
        fire["ventaja_deteccion_min"] = fire["ventaja_aviso_min"] = None
        if hit:
            inc, dist = hit
            fire["incident_id"], fire["incident_first_at"], fire["dist_km"] = inc["id"], inc["first_at"], round(dist, 2)
            if fire["detected_at"]:
                fire["ventaja_deteccion_min"] = round((inc["first_dt"] - parse_utc(fire["detected_at"])).total_seconds() / 60, 1)
            if fire["alerted_at"]:
                fire["ventaja_aviso_min"] = round((inc["first_dt"] - parse_utc(fire["alerted_at"])).total_seconds() / 60, 1)
    con_hora = [f for f in fires if f["detected_at"]]
    sin_hora = [f for f in fires if not f["detected_at"]]
    candidates = count_candidates(incidents, fires)
    open_n = sum(1 for i in incidents if i["status"] in OPEN_STATES)
    undetected = [f for f in fires if not f["detected"]]
    return {
        "db": str(db_path),
        "season": season,
        "parametros": {
            "km": km,
            "before_h": before_h,
            "after_h": after_h,
            "candidato_km": CAND_KM,
            "candidato_h": CAND_H,
            "ancla": "detected_at (f_deteccion) si existe; si no, started_at (f_inicio)",
        },
        "resumen": _summary(con_hora),
        "tramos": [{"tramo": t, **_summary([f for f in con_hora if tramo(f["area_ha"]) == t])} for t in TRAMOS],
        "ventaja_min": {
            "vs_deteccion": _stats([f["ventaja_deteccion_min"] for f in con_hora if f["ventaja_deteccion_min"] is not None]),
            "vs_aviso": _stats([f["ventaja_aviso_min"] for f in con_hora if f.get("ventaja_aviso_min") is not None]),
        },
        "sin_hora_conaf": {
            "n": len(sin_hora),
            "detectados": sum(1 for f in sin_hora if f["detected"]),
            "incendios": [{"id": f["id"], "name": f["name"], "detected": f["detected"]} for f in sin_hora],
        },
        "incidentes_abiertos": open_n,
        "candidatos_falsa_alarma": [
            {"id": i["id"], "status": i["status"], "first_at": i["first_at"], "lat": i["lat"], "lon": i["lon"]} for i in candidates
        ],
        "candidatos_por_region": candidates_by_region(incidents, candidates),
        "sin_comuna_reconocida": unmatched,
        "sin_incidente_cercano": [
            {
                "id": f["id"],
                "name": f["name"],
                "comuna": f["comuna"],
                "area_ha": f["area_ha"],
                "ancla": f["anchor_kind"],
                "hora": f["detected_at"] or f["started_at"],
            }
            for f in undetected
        ],
        "incendios": fires,
    }


def _fmt(value: float | None) -> str:
    return f"{value:g}" if value is not None else "—"


def render(result: dict[str, Any]) -> str:
    p = result["parametros"]
    lines = [
        f"Validación BRASA vs CONAF — {result['db']}" + (f" · temporada {result['season']}" if result["season"] else ""),
        f"Radio: {p['km']:g} km · ventana: [ancla −{p['before_h']:g} h, ancla +{p['after_h']:g} h] · "
        f"ancla = f_deteccion (o f_inicio cuando falta)",
        "",
    ]
    lines += ["| Superficie | Incendios | Detectados | % |", "|---|---:|---:|---:|"]
    for t in result["tramos"]:
        pct = f"{t['pct']}%" if t["n"] else "—"
        lines.append(f"| {t['tramo']} | {t['n']} | {t['detectados']} | {pct} |")
    total = result["resumen"]
    lines.append(f"| **Total (con f_deteccion)** | {total['n']} | {total['detectados']} | {total['pct']}% |")
    lines += [
        "",
        "Ventaja = primera detección BRASA − hora CONAF, en minutos (negativo = BRASA llegó antes):",
        "| Referencia | n | p50 | p90 |",
        "|---|---:|---:|---:|",
    ]
    for key, label in (("vs_deteccion", "f_deteccion"), ("vs_aviso", "f_aviso")):
        s = result["ventaja_min"][key]
        lines.append(f"| {label} | {s['n']} | {_fmt(s['p50'])} | {_fmt(s['p90'])} |")
    sh = result["sin_hora_conaf"]
    lines += [
        "",
        f"Sin hora de CONAF (sin f_deteccion; se evalúan sobre f_inicio, aparte): {sh['n']} · con incidente cercano: {sh['detectados']}",
    ]
    lines.append(
        f"Incidentes abiertos («anomalía»/«posible»): {result['incidentes_abiertos']} · "
        f"sin incendio de CONAF a ≤ {p['candidato_km']:g} km en ±{p['candidato_h']:g} h: "
        f"{len(result['candidatos_falsa_alarma'])} (candidatos a falsa alarma: quemas autorizadas, "
        f"calor industrial o focos aún no informados)"
    )
    if result["candidatos_por_region"]:
        lines += [
            "",
            "Candidatos por región (lo que no cae en comuna chilena queda en «sin región»):",
            "| Región | Abiertos | Sin CONAF cerca | % | Comunas con más casos |",
            "|---|---:|---:|---:|---|",
        ]
        for r in result["candidatos_por_region"]:
            comunas = ", ".join(f"{c['comuna']} ({c['n']})" for c in r["top_comunas"]) or "—"
            lines.append(f"| {r['region']} | {r['abiertos']} | {r['candidatos']} | {r['pct']}% | {comunas} |")
    else:
        lines.append("Sin incidentes abiertos: no hay datos para el resumen por región.")
    if result["sin_comuna_reconocida"]:
        conteo = Counter(f["comuna"] for f in result["incendios"])
        lines += [
            "",
            "Sin comuna reconocida — nombres sin calce en el territorio BCN (la fila no se "
            "descartó, pero queda fuera de las tasas por región):",
            "| Comuna (CONAF) | Incendios |",
            "|---|---:|",
        ]
        for name in result["sin_comuna_reconocida"]:
            lines.append(f"| {name} | {conteo[name]} |")
    if result["sin_incidente_cercano"]:
        lines += ["", "Incendios de CONAF sin incidente cercano:"]
        for f in result["sin_incidente_cercano"]:
            area = f"{f['area_ha']:g} ha" if f["area_ha"] is not None else "sin superficie"
            comuna = f["comuna"] or "sin comuna"
            lines.append(f"- {f['id']} · {f['name']} ({comuna}, {area}, {f['ancla']} {f['hora']})")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", required=True, type=Path, help="ruta a una copia de work.db (se abre en solo lectura)")
    parser.add_argument("--km", type=float, default=3, help="radio de correspondencia en km (por omisión 3)")
    parser.add_argument("--before-h", type=float, default=24, help="horas antes del ancla que abarca la ventana (por omisión 24)")
    parser.add_argument("--after-h", type=float, default=6, help="horas después del ancla que abarca la ventana (por omisión 6)")
    parser.add_argument("--season", help="evaluar solo una temporada, por ejemplo 2025-2026 (por omisión: todas)")
    parser.add_argument("--json", type=Path, metavar="RUTA", help="además de la tabla, guarda el resultado en JSON")
    args = parser.parse_args(argv)
    if not args.db.exists():
        print(f"No existe {args.db}.", file=sys.stderr)
        return 2
    try:
        result = validate(args.db, args.km, args.before_h, args.after_h, args.season)
    except sqlite3.OperationalError as exc:
        print(f"No se pudo leer la base ({exc}). ¿Es un work.db de BRASA?", file=sys.stderr)
        return 2
    if result is None:
        print(NO_DATA, file=sys.stderr)
        return 2
    print(render(result))
    if args.json:
        args.json.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

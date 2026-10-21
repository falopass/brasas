"""Banco de reproducción de casos (QA-02): pasa las detecciones GOES de un caso por `incidents.update`.

Carga `web/data/cases/<id>.goes.json`, agrupa las filas por barrido y las reinyecta en orden
temporal sobre una base desechable (`data/replay.db` + `data/replay.work.db`, ignoradas por git;
nunca `data/brasa.db` ni `data/work.db`). Al terminar imprime por incidente cuántos minutos pasaron
entre su primera detección y su llegada a «posible», más el total de incidentes, fusiones y el
tiempo de reloj. Es la medida base de FIX-15. Sin red.

Uso:  python scripts/replay_case.py <case-id> [--limit N] [--json RUTA]

Con --json el resultado completo se guarda en RUTA, incluido el bloque «resumen»:
«incidentes», «con_posible» y «minutos_hasta_posible» = {"min", "mediana", "max"}
en minutos sobre los incidentes que llegaron a «posible» (None si ninguno llegó).
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend import incidents  # noqa: E402
from backend.db import Database  # noqa: E402
from backend.geo import territory  # noqa: E402

CONF_FROM_CODE = {2: "alta", 1: "media", 0: "baja"}  # backend/cases.py
REACHED_POSIBLE = {"posible", "reportado", "confirmado", "controlado"}

INSERT_OBS = (
    "INSERT INTO observations(id, source, sensor, satellite, resolution_m, lat, lon, observed_at, "
    "frp_mw, brightness_k, confidence, comuna_code, run_id, ingested_at) "
    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,NULL,?)"
)


def parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def stamp(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def replay(goes_path: Path, db_path: Path, limit: int | None = None) -> dict:
    """Reproduce el caso y devuelve la tabla de incidentes, fusiones y el tiempo de reloj."""
    data = json.loads(Path(goes_path).read_text(encoding="utf-8"))
    start = parse_utc(data["start_utc"])
    scans = sorted(data["scans"], key=lambda s: s["t"])
    if limit is not None:
        scans = scans[:limit]
    match = re.search(r"GOES-(\d+)", data.get("source", ""))
    satellite = f"GOES-{match.group(1)}" if match else "GOES"
    source = f"{satellite.replace('-', '')}_FDCF"
    by_minute: dict[int, list[tuple[int, list]]] = {}
    for index, row in enumerate(data["rows"]):
        by_minute.setdefault(row[0], []).append((index, row))

    work_path = db_path.with_name(db_path.stem + ".work.db")
    for stale in (db_path, work_path):
        for suffix in ("", "-wal", "-shm"):
            stale.with_name(stale.name + suffix).unlink(missing_ok=True)
    db = Database(db_path, work_path)

    posible_at: dict[str, datetime] = {}  # id → ciclo en que el incidente llegó a «posible» o más
    seen_merges: set[str] = set()
    detections = 0
    comunas = territory()
    clock = time.monotonic()
    for i, scan in enumerate(scans):
        when = parse_utc(scan["t"])
        minute = int(round((when - start).total_seconds() / 60))
        inserts, batch = [], []
        for index, (m, lat, lon, frp, bright, conf) in by_minute.get(minute, []):
            oid = f"{data.get('case_id', 'caso')}:{m}:{index}"
            at = stamp(start + timedelta(minutes=m))
            comuna = comunas.locate(lat, lon)
            code = comuna.code if comuna else None
            inserts.append((oid, source, "ABI", satellite, 2000, lat, lon, at, frp, bright, CONF_FROM_CODE[conf], code, at))
            batch.append({"id": oid, "lat": lat, "lon": lon, "observed_at": at, "resolution_m": 2000, "comuna_code": code})
        if inserts:
            with db.connect() as conn:
                conn.executemany(INSERT_OBS, inserts)
        for inc in incidents.update(db, batch, now=when):
            if inc["status"] in REACHED_POSIBLE and inc["id"] not in posible_at:
                posible_at[inc["id"]] = when
        # Una fusión borra el id: el incidente que absorbe hereda el momento «posible» del absorbido.
        for merge in db.query("SELECT dead_id, live_id FROM incident_merges"):
            if merge["dead_id"] in seen_merges:
                continue
            seen_merges.add(merge["dead_id"])
            dead_at = posible_at.get(merge["dead_id"])
            if dead_at and dead_at < posible_at.get(merge["live_id"], datetime.max.replace(tzinfo=timezone.utc)):
                posible_at[merge["live_id"]] = dead_at
        detections += len(batch)
        if (i + 1) % 200 == 0:
            print(f"  {i + 1}/{len(scans)} barridos…", flush=True)
    elapsed = time.monotonic() - clock

    table = [
        {
            "id": inc["id"],
            "first_seen_at": inc["first_seen_at"],
            "minutes_to_posible": (
                round((posible_at[inc["id"]] - parse_utc(inc["first_seen_at"])).total_seconds() / 60) if inc["id"] in posible_at else None
            ),
            "n_obs": inc["n_obs"],
            "status": inc["status"],
        }
        for inc in db.query("SELECT * FROM incidents ORDER BY first_seen_at")
    ]
    mins = [r["minutes_to_posible"] for r in table if r["minutes_to_posible"] is not None]
    result = {
        "case_id": data.get("case_id"),
        "scans": len(scans),
        "detections": detections,
        "incidents": table,
        "merges": db.one("SELECT COUNT(*) AS n FROM incident_merges")["n"],
        "resumen": {
            "incidentes": len(table),
            "con_posible": len(mins),
            "minutos_hasta_posible": ({"min": min(mins), "mediana": statistics.median(mins), "max": max(mins)} if mins else None),
        },
        "elapsed_s": elapsed,
    }
    db.close_all()  # suelta el archivo: en Windows una conexión abierta impide recrear la base
    return result


def print_report(result: dict) -> None:
    rows = result["incidents"]
    print(f"\nCaso: {result['case_id']} · {result['scans']} barridos · {result['detections']} detecciones\n")
    print(f"{'incidente':<10}{'primera detección':<19}{'min→posible':>12}{'obs':>6}  estado")
    for r in rows:
        mins = str(r["minutes_to_posible"]) if r["minutes_to_posible"] is not None else "—"
        print(f"{r['id'][:8]:<10}{r['first_seen_at'][:16].replace('T', ' '):<19}{mins:>12}{r['n_obs']:>6}  {r['status']}")
    print(f"\n{len(rows)} incidentes · {result['merges']} fusiones · {result['detections']} detecciones · {result['elapsed_s']:.1f} s")
    resumen = result["resumen"]["minutos_hasta_posible"]
    if resumen:
        print(
            f"min→posible: mín {resumen['min']} · mediana {resumen['mediana']} · máx {resumen['max']} min "
            f"({result['resumen']['con_posible']} de {len(rows)} incidentes llegaron a «posible»)"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("case_id")
    parser.add_argument("--limit", type=int, default=None, help="procesa solo los primeros N barridos")
    parser.add_argument("--json", type=Path, default=None, metavar="RUTA", help="guarda el resultado completo (tabla + resumen) en RUTA")
    args = parser.parse_args()
    goes = ROOT / "web" / "data" / "cases" / f"{args.case_id}.goes.json"
    if not goes.exists():
        raise SystemExit(f"No existe {goes.relative_to(ROOT)}. Los .goes.json los genera scripts/build_case_goes.py.")
    result = replay(goes, ROOT / "data" / "replay.db", args.limit)
    print_report(result)
    if args.json:
        args.json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Resumen guardado en {args.json}")


if __name__ == "__main__":
    main()

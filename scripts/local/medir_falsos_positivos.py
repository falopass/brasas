"""Cuántas detecciones quedaron en «anomalia», por región y franja horaria (DET-08).

El norte grande (Arica a Atacama) combina desierto muy caliente de día, minería y plantas
solares: sospechamos que GOES (ABI) marca ahí más ruido que en el resto del país. Antes de
proponer un umbral regional hay que medir: este script cuenta, por región, cuántas
detecciones de ``work.observations`` terminaron en un incidente «anomalia» —la evidencia no
alcanzó para subir de estado— frente a las que llegaron a un estado con evidencia
(«posible», «reportado», «confirmado», «controlado», «extinguido»).

**«anomalia» no equivale a falso positivo**: una detección aislada puede ser un incendio real
pequeño, una quema autorizada o calor industrial. Es un candidato a ruido, no una condena.

La región sale del ``comuna_code`` guardado al ingerir (territorio BCN); las detecciones sin
comuna (mar, bordes) se agrupan aparte. «Diurna» es 08:00 a 19:59 hora de Chile
(``observed_at`` está en UTC; se convierte con America/Santiago).

La base se copia a un directorio temporal con la API de respaldo de SQLite y la copia se abre
en modo solo-lectura: jamás se escribe en el original y sirve aunque esté en WAL. Sin red.

Uso:  python scripts/local/medir_falsos_positivos.py [--db data/work.db]
        [--from 2026-01-01] [--to 2026-03-31] [--sensor ABI] [--json salida.json]
"""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.geo import territory  # noqa: E402

CHILE_TZ = ZoneInfo("America/Santiago")
DIURNO = range(8, 20)  # «de día»: 08:00 a 19:59 hora local de Chile
CON_EVIDENCIA = ("posible", "reportado", "confirmado", "controlado", "extinguido")
SIN_COMUNA = "(sin comuna)"
EMPTY = "No hay detecciones que medir."


def _parse(text: str) -> datetime:
    """ISO → instante UTC. Acepta «Z» y fechas sin hora (medianoche)."""
    moment = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    return (moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def _stamp(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


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
    tmp = Path(tempfile.mkdtemp(prefix="brasa-falsos-"))
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


def _pct(part: int, total: int) -> float | None:
    return round(100 * part / total, 1) if total else None


def _row(obs: sqlite3.Row) -> dict[str, Any]:
    estado = obs["estado"] or "sin_incidente"
    return {"estado": "anomalia" if estado == "anomalia" else ("evidencia" if estado in CON_EVIDENCIA else estado),
            "comuna_code": obs["comuna_code"],
            "diurna": _parse(obs["observed_at"]).astimezone(CHILE_TZ).hour in DIURNO}


def measure(db_path: Path, desde: str | None = None, hasta: str | None = None,
            sensor: str | None = None) -> dict[str, Any]:
    """Conteos por región sobre una copia de work.db. ``desde`` es inclusivo; ``hasta``
    también, y una fecha sin hora («2026-03-31») incluye ese día completo."""
    where, params = [], []
    if desde:
        where.append("o.observed_at >= ?")
        params.append(_stamp(_parse(desde)))
    if hasta:
        end = _parse(hasta)
        if "T" not in hasta.strip():  # solo fecha: el límite exclusivo es el día siguiente
            end += timedelta(days=1)
            where.append("o.observed_at < ?")
        else:
            where.append("o.observed_at <= ?")
        params.append(_stamp(end))
    if sensor:
        where.append("o.sensor = ?")
        params.append(sensor)
    sql = ("SELECT o.observed_at, o.comuna_code, i.status AS estado FROM observations o "
           "LEFT JOIN incident_observations io ON io.observation_id = o.id "
           "LEFT JOIN incidents i ON i.id = io.incident_id")
    if where:
        sql += " WHERE " + " AND ".join(where)
    with open_readonly(db_path) as conn:
        rows = [_row(r) for r in conn.execute(sql, params)]

    terr = territory()
    north_first = {code: i for i, code in
                   enumerate(sorted(terr.regions, key=lambda c: -terr.regions[c]["bbox"][3]))}

    def acc() -> dict[str, int]:
        return {"n": 0, "diurnas": 0, "anomalia": 0, "anomalia_dia": 0, "n_dia": 0,
                "anomalia_noche": 0, "n_noche": 0, "sin_incidente": 0}

    regiones: dict[int | None, dict[str, Any]] = {}
    comunas: dict[int | None, dict[str, Any]] = {}
    region_name: dict[int | None, str] = {}
    comuna_name: dict[int | None, str] = {}
    comuna_region: dict[int | None, str] = {}
    for row in rows:
        code = row["comuna_code"]
        comuna = terr.by_code.get(code) if code is not None else None
        rcode = comuna.region_code if comuna else None
        regiones.setdefault(rcode, acc())
        comunas.setdefault(code, acc())
        region_name[rcode] = comuna.region if comuna else SIN_COMUNA
        comuna_name[code] = comuna.name if comuna else SIN_COMUNA
        comuna_region[code] = comuna.region if comuna else "—"
        for cell in (regiones[rcode], comunas[code]):
            cell["n"] += 1
            if row["diurna"]:
                cell["diurnas"] += 1
            if row["estado"] == "anomalia":
                cell["anomalia"] += 1
                cell["anomalia_dia" if row["diurna"] else "anomalia_noche"] += 1
            cell["n_dia" if row["diurna"] else "n_noche"] += 1
            cell["sin_incidente"] += 1 if row["estado"] == "sin_incidente" else 0

    def out_region(name: str, c: dict[str, Any]) -> dict[str, Any]:
        return {"region": name, "n": c["n"], "pct_diurnas": _pct(c["diurnas"], c["n"]),
                "anomalia": c["anomalia"], "pct_anomalia": _pct(c["anomalia"], c["n"]),
                "pct_anomalia_dia": _pct(c["anomalia_dia"], c["n_dia"]),
                "pct_anomalia_noche": _pct(c["anomalia_noche"], c["n_noche"]),
                "sin_incidente": c["sin_incidente"]}

    total = acc()
    for c in regiones.values():
        for key in total:
            total[key] += c[key]
    top = sorted(comunas.items(), key=lambda kv: (-kv[1]["anomalia"], -kv[1]["n"]))[:5]
    return {
        "db": str(db_path),
        "generado": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "filtros": {"desde": desde, "hasta": hasta, "sensor": sensor},
        "total": total["n"],
        "regiones": [out_region(region_name[code], regiones[code])
                     for code in sorted(regiones, key=lambda c: north_first.get(c, 999))],
        "comunas_top": [{"comuna": comuna_name[code], "region": comuna_region[code],
                         "anomalia": comunas[code]["anomalia"], "n": comunas[code]["n"]}
                        for code, _ in top],
        "totales": out_region("Total", total),
    }


def _fmt(value: float | None) -> str:
    return f"{value:.1f}%" if value is not None else "—"


def render(result: dict[str, Any]) -> str:
    f = result["filtros"]
    periodo = f"{f['desde'] or 'inicio'} a {f['hasta'] or 'hoy'}"
    t = result["totales"]
    lines = [f"«Anomalia» por región — {result['db']} · generado {result['generado']}",
             f"Periodo: {periodo} · sensor: {f['sensor'] or 'todos'} · "
             f"diurna = 08:00 a 19:59 hora de Chile", "",
             "| Región | Detecciones | % diurnas | «anomalia» | % «anomalia» | % anom. de día | % anom. de noche |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for r in result["regiones"]:
        lines.append(f"| {r['region']} | {r['n']} | {_fmt(r['pct_diurnas'])} | {r['anomalia']} | "
                     f"{_fmt(r['pct_anomalia'])} | {_fmt(r['pct_anomalia_dia'])} | "
                     f"{_fmt(r['pct_anomalia_noche'])} |")
    lines.append(f"| **Total** | {t['n']} | {_fmt(t['pct_diurnas'])} | {t['anomalia']} | "
                 f"{_fmt(t['pct_anomalia'])} | {_fmt(t['pct_anomalia_dia'])} | "
                 f"{_fmt(t['pct_anomalia_noche'])} |")
    sin_inc = sum(r["sin_incidente"] for r in result["regiones"])
    if sin_inc:
        lines.append(f"\nDetecciones sin incidente enlazado: {sin_inc} (entran en los totales).")
    if result["comunas_top"]:
        lines += ["", "Comunas con más «anomalia» (máx. 5):", "",
                  "| Comuna | Región | «anomalia» | Detecciones |", "|---|---|---:|---:|"]
        for c in result["comunas_top"]:
            lines.append(f"| {c['comuna']} | {c['region']} | {c['anomalia']} | {c['n']} |")
    lines += ["", "Lectura: «anomalia» = la evidencia no alcanzó para subir de estado. NO equivale a "
                  "falso positivo: puede ser un incendio real pequeño, una quema autorizada o calor "
                  "industrial/solar. Una región con % alto de día y bajo de noche es candidata a "
                  "ruido por superficie caliente."]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", default="data/work.db",
                        help="ruta a work.db (se copia y se abre en solo lectura; por omisión data/work.db)")
    parser.add_argument("--from", dest="desde", metavar="ISO",
                        help="solo detecciones desde esta fecha/hora UTC (inclusivo)")
    parser.add_argument("--to", dest="hasta", metavar="ISO",
                        help="hasta esta fecha/hora UTC (inclusivo; una fecha sin hora incluye el día completo)")
    parser.add_argument("--sensor", help="solo un sensor, por ejemplo ABI, VIIRS o MODIS")
    parser.add_argument("--json", metavar="RUTA", help="además de la tabla, escribe el resultado en JSON")
    args = parser.parse_args(argv)
    db_path = Path(args.db)
    if not db_path.exists():
        print(f"No existe {db_path} (corre la ingesta primero o pasa --db).", file=sys.stderr)
        return 2
    try:
        result = measure(db_path, args.desde, args.hasta, args.sensor)
    except ValueError as exc:
        print(f"Fecha inválida ({exc}). Usa ISO, por ejemplo 2026-01-31 o 2026-01-31T12:00:00Z.", file=sys.stderr)
        return 2
    except sqlite3.OperationalError as exc:
        print(f"No se pudo leer la base ({exc}). ¿Es una copia de work.db?", file=sys.stderr)
        return 2
    if not result["total"]:
        print(f"{EMPTY} La base está vacía o los filtros no dejaron nada.", file=sys.stderr)
        return 0
    print(render(result))
    if args.json:
        Path(args.json).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

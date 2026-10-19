"""Calibración de los niveles de riesgo contra los incendios informados por CONAF (RISK-13, QA-20).

Responde con números: cuántos incendios del reporte público de CONAF (GEPRIF) empezaron en días
de cada nivel —la regla 30-30-30 sola (``level``), la combinada con el FWI (``level_combined``) y
la clase del FWI (``fwi_level``)— por macrozona, y con qué frecuencia coinciden con el Botón Rojo.
Sirve para decidir si los umbrales actuales (backend/risk.py) describen bien Chile; este script
solo mide y propone: cualquier cambio de umbral se decide aparte, en el backlog.

Cada incendio es un «evento comuna-día»: varios incendios el mismo día en la misma comuna cuentan
una vez. ``started_at`` está en UTC y el día se evalúa en hora de Chile (America/Santiago), la misma
convención con la que se guarda ``risk_daily.date``.

Macrozonas (por ``region_code`` del territorio BCN):
- norte: Arica y Parinacota (15), Tarapacá (1), Antofagasta (2), Atacama (3), Coquimbo (4)
- centro: Valparaíso (5), Metropolitana (13), O'Higgins (6), Maule (7)
- sur: Ñuble (16), Biobío (8), La Araucanía (9), Los Ríos (14), Los Lagos (10)
- austral: Aysén (11), Magallanes (12)

La base se copia a un directorio temporal con la API de respaldo de SQLite y la copia se abre en
modo solo-lectura: jamás se escribe en el original y sirve aunque esté en WAL. Sin red.

Uso:  python scripts/calibrar_riesgo.py --db data/work.db [--json reporte.json]
"""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.geo import _fold, territory  # noqa: E402
from backend.risk import LEVELS, local_day  # noqa: E402

# (clave, etiqueta, region_code según el territorio BCN que usa la app)
MACROZONAS: list[tuple[str, str, tuple[int, ...]]] = [
    ("norte", "Norte (Arica y Parinacota a Coquimbo)", (15, 1, 2, 3, 4)),
    ("centro", "Centro (Valparaíso a Maule)", (5, 13, 6, 7)),
    ("sur", "Sur (Ñuble a Los Lagos)", (16, 8, 9, 14, 10)),
    ("austral", "Austral (Aysén y Magallanes)", (11, 12)),
]
MACRO_ORDER = [key for key, _, _ in MACROZONAS]
SIN_MACRO = "sin macrozona"
REGION_TO_MACRO = {code: key for key, _, codes in MACROZONAS for code in codes}

# Clases de nivel comparadas: (columna de risk_daily, título para el informe)
CLASSES = [("level", "Nivel 30-30-30"), ("level_combined", "Nivel combinado (30-30-30 + FWI)"),
           ("fwi_level", "Clase FWI")]


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
    tmp = Path(tempfile.mkdtemp(prefix="brasa-calibrar-"))
    conn = None
    try:
        work_copy = tmp / "work.db"
        _copy_db(db_path, work_copy)
        conn = sqlite3.connect(f"file:{work_copy}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        yield conn
    finally:
        if conn is not None:
            conn.close()
        shutil.rmtree(tmp, ignore_errors=True)


def _rate(part: int, total: int) -> float | None:
    return round(part / total, 4) if total else None


def _level_order(level: str) -> tuple[int, str]:
    return (LEVELS.index(level) if level in LEVELS else len(LEVELS), level)


def _comuna_lookup() -> tuple[dict[str, int], set[str]]:
    """Nombre normalizado → código de comuna; y los nombres que calzan con más de una."""
    lookup: dict[str, int] = {}
    ambiguous: set[str] = set()
    for comuna in territory().comunas:
        key = _fold(comuna.name)
        if key in lookup and lookup[key] != comuna.code:
            ambiguous.add(key)
        lookup[key] = comuna.code
    return lookup, ambiguous


def _macrozona(comuna_code: int) -> str:
    comuna = territory().by_code.get(comuna_code)
    if comuna is None:
        return SIN_MACRO
    return REGION_TO_MACRO.get(comuna.region_code, SIN_MACRO)


def calibrate(db_path: Path) -> dict[str, Any]:
    """Cálculo completo sobre una copia de work.db."""
    lookup, ambiguous = _comuna_lookup()
    with open_readonly(db_path) as conn:
        fires = conn.execute("SELECT id, comuna, region, started_at FROM official_fires").fetchall()
        risk_days = conn.execute(
            "SELECT comuna_code, date, level, level_combined, fwi_level FROM risk_daily").fetchall()
        boton = conn.execute("SELECT comuna_code, date FROM boton_rojo WHERE hours > 0").fetchall()

    # Incendios → eventos comuna-día (fecha en hora de Chile).
    events: set[tuple[int, str]] = set()
    used = sin_fecha = sin_comuna = 0
    unmatched: dict[tuple[str, str], int] = {}
    for fire in fires:
        started = fire["started_at"]
        name = (fire["comuna"] or "").strip()
        try:
            day = local_day(started) if started else None
        except (TypeError, ValueError):
            day = None
        if day is None:
            sin_fecha += 1
            continue
        if not name:
            sin_comuna += 1
            continue
        code = lookup.get(_fold(name))
        if code is None or _fold(name) in ambiguous:
            unmatched[(name, fire["region"] or "")] = unmatched.get((name, fire["region"] or ""), 0) + 1
            continue
        used += 1
        events.add((code, day))

    risk_keys = {(row["comuna_code"], row["date"]) for row in risk_days}
    br_keys = {(row["comuna_code"], row["date"]) for row in boton}

    # Por clase y macrozona: días con dato y días con incendio, por nivel.
    levels: dict[str, dict[str, dict[str, dict[str, int]]]] = {
        col: {macro: {} for macro in MACRO_ORDER + [SIN_MACRO]} for col, _ in CLASSES}
    missing: dict[str, dict[str, int]] = {col: {} for col, _ in CLASSES}
    for row in risk_days:
        macro = _macrozona(row["comuna_code"])
        has_fire = (row["comuna_code"], row["date"]) in events
        for col, _ in CLASSES:
            value = row[col]
            if value is None:
                missing[col][macro] = missing[col].get(macro, 0) + 1
                continue
            cell = levels[col][macro].setdefault(value, {"dias": 0, "con_incendio": 0})
            cell["dias"] += 1
            cell["con_incendio"] += 1 if has_fire else 0

    by_class: dict[str, list[dict[str, Any]]] = {}
    for col, _title in CLASSES:
        rows_out = []
        for macro in MACRO_ORDER + [SIN_MACRO]:
            cells = levels[col][macro]
            if not cells:
                continue
            total_dias = sum(c["dias"] for c in cells.values())
            total_fires = sum(c["con_incendio"] for c in cells.values())
            base = _rate(total_fires, total_dias)
            for level in sorted(cells, key=_level_order):
                tasa = _rate(cells[level]["con_incendio"], cells[level]["dias"])
                rows_out.append({"macrozona": macro, "nivel": level, "dias": cells[level]["dias"],
                                 "con_incendio": cells[level]["con_incendio"], "tasa": tasa,
                                 "lift": round(tasa / base, 2) if tasa is not None and base else None})
            rows_out.append({"macrozona": macro, "nivel": "(base)", "dias": total_dias,
                             "con_incendio": total_fires, "tasa": base, "lift": None})
        by_class[col] = rows_out

    # Concordancia con el Botón Rojo: universo = días comuna con riesgo o con Botón Rojo.
    concordance: dict[str, dict[str, dict[str, int]]] = {
        macro: {"con": {"dias": 0, "con_incendio": 0}, "sin": {"dias": 0, "con_incendio": 0}}
        for macro in MACRO_ORDER + [SIN_MACRO]}
    for code, day in risk_keys | br_keys:
        macro = _macrozona(code)
        side = "con" if (code, day) in br_keys else "sin"
        concordance[macro][side]["dias"] += 1
        concordance[macro][side]["con_incendio"] += 1 if (code, day) in events else 0
    boton_rojo = []
    for macro in MACRO_ORDER + [SIN_MACRO]:
        con, sin = concordance[macro]["con"], concordance[macro]["sin"]
        if not con["dias"] and not sin["dias"]:
            continue
        tasa_con, tasa_sin = _rate(con["con_incendio"], con["dias"]), _rate(sin["con_incendio"], sin["dias"])
        boton_rojo.append({"macrozona": macro, "dias_con_br": con["dias"],
                           "con_incendio_br": con["con_incendio"], "tasa_con_br": tasa_con,
                           "dias_sin_br": sin["dias"], "con_incendio_sin": sin["con_incendio"],
                           "tasa_sin_br": tasa_sin,
                           "lift": round(tasa_con / tasa_sin, 2)
                                   if tasa_con is not None and tasa_sin else None})

    return {
        "db": str(db_path),
        "generado": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "conteo": {
            "incendios_conaf": len(fires),
            "incendios_usados": used,
            "descartados_sin_fecha": sin_fecha,
            "descartados_sin_comuna": sin_comuna,
            "sin_calce_comuna": sum(unmatched.values()),
            "eventos_comuna_dia": len(events),
            "agrupados_mismo_dia": used - len(events),
            "eventos_sin_dato_riesgo": len(events - risk_keys),
            "dias_riesgo": len(risk_days),
            "dias_boton_rojo": len(br_keys),
        },
        "macrozonas": {key: {"label": label, "regiones": list(codes)} for key, label, codes in MACROZONAS},
        "niveles": {col: by_class[col] for col, _ in CLASSES},
        "dias_sin_dato": {col: missing[col] for col, _ in CLASSES},
        "boton_rojo": boton_rojo,
        "comunas_sin_calce": [{"comuna": name, "region": region, "incendios": n}
                              for (name, region), n in sorted(unmatched.items())],
    }


def _pct(value: float | None) -> str:
    return f"{value * 100:.1f}%" if value is not None else "—"


def _num(value: float | None) -> str:
    return f"{value:g}" if value is not None else "—"


def render(result: dict[str, Any]) -> str:
    c = result["conteo"]
    lines = [f"Base: {result['db']} · generado {result['generado']}", "",
             f"Incendios CONAF: {c['incendios_conaf']} · usados: {c['incendios_usados']} "
             f"(eventos comuna-día: {c['eventos_comuna_dia']}, "
             f"agrupados mismo día: {c['agrupados_mismo_dia']})",
             f"Descartados: sin fecha {c['descartados_sin_fecha']} · sin comuna {c['descartados_sin_comuna']} · "
             f"comuna sin calce {c['sin_calce_comuna']}",
             f"Días comuna con nivel calculado: {c['dias_riesgo']} · con Botón Rojo: {c['dias_boton_rojo']} · "
             f"eventos en día sin dato de riesgo: {c['eventos_sin_dato_riesgo']}", "",
             "Macrozonas: " + " · ".join(f"{label}" for _, label, _ in MACROZONAS), ""]

    for col, title in CLASSES:
        lines += [f"## {title}", "",
                  "| Macrozona | Nivel | Días con dato | Días con incendio | Tasa | Lift |",
                  "|---|---|---:|---:|---:|---:|"]
        for row in result["niveles"][col]:
            lines.append(f"| {row['macrozona']} | {row['nivel']} | {row['dias']} | "
                         f"{row['con_incendio']} | {_pct(row['tasa'])} | {_num(row['lift'])} |")
        sin_dato = ", ".join(f"{macro}: {n}" for macro, n in sorted(result["dias_sin_dato"][col].items()))
        if sin_dato:
            lines.append(f"\nDías sin dato de esta clase: {sin_dato}")
        lines.append("")

    lines += ["## Concordancia con el Botón Rojo (CONAF)", "",
              "| Macrozona | Días con BR | con incendio | Tasa | Días sin BR | con incendio | Tasa | Lift |",
              "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for row in result["boton_rojo"]:
        lines.append(f"| {row['macrozona']} | {row['dias_con_br']} | {row['con_incendio_br']} | "
                     f"{_pct(row['tasa_con_br'])} | {row['dias_sin_br']} | {row['con_incendio_sin']} | "
                     f"{_pct(row['tasa_sin_br'])} | {_num(row['lift'])} |")

    if result["comunas_sin_calce"]:
        lines += ["", "## Incendios con comuna no reconocida", "",
                  "| Comuna (CONAF) | Región (CONAF) | Incendios |", "|---|---|---:|"]
        for item in result["comunas_sin_calce"]:
            lines.append(f"| {item['comuna']} | {item['region']} | {item['incendios']} |")
    lines += ["", "Lift = tasa del nivel / tasa base de la macrozona (días con dato de esa clase). "
              "No es causal: el nivel describe condiciones, no probabilidad de incendio."]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--db", default="data/work.db", help="ruta a una copia de work.db (se abre en solo lectura)")
    parser.add_argument("--json", metavar="RUTA", help="además de las tablas, escribe el resultado en JSON")
    args = parser.parse_args(argv)
    db_path = Path(args.db)
    if not db_path.exists():
        print(f"No existe {db_path}.", file=sys.stderr)
        return 2
    try:
        result = calibrate(db_path)
    except sqlite3.OperationalError as exc:
        print(f"No se pudo leer la base ({exc}). ¿Es una copia de work.db?", file=sys.stderr)
        return 2
    print(render(result))
    if args.json:
        Path(args.json).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

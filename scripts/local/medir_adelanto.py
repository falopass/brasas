"""Medida de adelanto de BRASA sobre casos reales (QA-02/QA-03): publica web/data/calibracion.json.

Corre el banco de reproducción (``scripts/replay_case.py``, como módulo) sobre el caso
indicado —por omisión Viña del Mar 2024— o sobre todos los ``*.goes.json`` de
``web/data/cases/`` con ``todos``, contra una base desechable en un directorio temporal, y
escribe ``web/data/calibracion.json`` con, por incidente, los minutos entre su primera
detección y su llegada a «posible», más la mediana y el peor caso. Es lo que muestra la
sección «Qué tan rápido llega BRASA» de la vista Calidad.

Con ``todos`` el JSON trae además ``cases`` (la medida por caso) y ``coverage``: cuántos
incidentes entraron en la medida (``n_medidos``) y cuántos quedaron fuera por no llegar a
«posible» (``n_sin_posible``), sobre el total (``n_incidentes``).

Un incidente que nunca llega a «posible» queda con ``min_to_posible: null`` y no entra en la
mediana ni en el peor caso. «Posible» es criterio de la agrupación de BRASA, no de CONAF, y
la reproducción corre sin la latencia de red de la ingesta real: es una medida retrospectiva
de un caso, no una promesa de tiempo de aviso. Sin red.

El ``id`` de cada incidente es una etiqueta estable (``<caso>-<n>``, en orden de primera
detección), no el id de la base del replay: esa base es desechable y su uuid cambia en cada
corrida, así que publicarlo reescribiría el archivo entero sin que cambie ninguna cifra y no
se podría revisar qué se movió al volver a medir.

Uso:  python scripts/local/medir_adelanto.py [caso|todos] [--todos] [--out web/data/calibracion.json]
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import replay_case  # noqa: E402

METHOD = (
    "Minutos desde la primera detección satelital agrupada hasta que el incidente pasa a "
    "«posible» con la regla de agrupación vigente, medidos reproduciendo el caso "
    "(scripts/replay_case.py) sobre una base desechable."
)


def measure(goes_path: Path) -> dict:
    """Reproduce el caso y devuelve el contenido de calibracion.json."""
    data = json.loads(goes_path.read_text(encoding="utf-8"))
    match = re.search(r"GOES-(\d+)", data.get("source", ""))
    satellite = f"GOES-{match.group(1)}" if match else "GOES"
    with tempfile.TemporaryDirectory(prefix="brasa-adelanto-") as tmp:
        result = replay_case.replay(goes_path, Path(tmp) / "replay.db")
    minutes = [i["minutes_to_posible"] for i in result["incidents"] if i["minutes_to_posible"] is not None]
    return {
        "case_id": result["case_id"],
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": f"NOAA {satellite} FDC · dominio público",
        "method": METHOD,
        "incidents": [
            {
                "id": f"{result['case_id']}-{n:03d}",
                "first_seen_at": i["first_seen_at"],
                "min_to_posible": i["minutes_to_posible"],
                "n_obs": i["n_obs"],
            }
            for n, i in enumerate(result["incidents"], 1)
        ],
        "summary": {
            "n_incidents": len(result["incidents"]),
            "median_min": statistics.median(minutes) if minutes else None,
            "max_min": max(minutes) if minutes else None,
        },
    }


def combine(results: list[dict]) -> dict:
    """Une las medidas de varios casos: resumen conjunto, detalle por caso y cobertura.

    La lista plana ``incidents`` reúne los incidentes de todos los casos con su ``case_id``;
    ``summary`` es la medida conjunta sobre ellos y ``cases`` conserva la medida por caso.
    """
    incidents = [dict(inc, case_id=r["case_id"]) for r in results for inc in r["incidents"]]
    minutes = [i["min_to_posible"] for i in incidents if i["min_to_posible"] is not None]
    satellites = sorted({s for r in results for s in re.findall(r"GOES-\d+", r["source"])})
    return {
        "case_id": "varios-casos",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": f"NOAA {', '.join(satellites) or 'GOES'} FDC · dominio público",
        "method": METHOD,
        "incidents": incidents,
        "summary": {
            "n_incidents": len(incidents),
            "median_min": statistics.median(minutes) if minutes else None,
            "max_min": max(minutes) if minutes else None,
        },
        "cases": [{"case_id": r["case_id"], "incidents": r["incidents"], "summary": r["summary"]} for r in results],
        "coverage": {
            "n_incidentes": len(incidents),
            "n_medidos": len(minutes),
            "n_sin_posible": len(incidents) - len(minutes),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "case_id",
        nargs="?",
        default="vina-del-mar-2024",
        help="caso en web/data/cases/<id>.goes.json, o «todos» para medir todos los del directorio (omisión: vina-del-mar-2024)",
    )
    parser.add_argument("--todos", action="store_true", help="equivale a pasar «todos»: mide todos los *.goes.json de web/data/cases/")
    parser.add_argument("--out", metavar="RUTA", help="dónde escribir el JSON (omisión: web/data/calibracion.json)")
    args = parser.parse_args(argv)
    if args.todos or args.case_id == "todos":
        paths = sorted((ROOT / "web" / "data" / "cases").glob("*.goes.json"))
        if not paths:
            print("No hay *.goes.json en web/data/cases/. Los genera scripts/build_case_goes.py.", file=sys.stderr)
            return 2
        results = []
        for path in paths:
            print(f"Midiendo {path.name}…", flush=True)
            results.append(measure(path))
        result = combine(results)
    else:
        goes = ROOT / "web" / "data" / "cases" / f"{args.case_id}.goes.json"
        if not goes.exists():
            print(f"No existe {goes.relative_to(ROOT)}. Los .goes.json los genera scripts/build_case_goes.py.", file=sys.stderr)
            return 2
        result = measure(goes)
    out = Path(args.out) if args.out else ROOT / "web" / "data" / "calibracion.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    s = result["summary"]
    print(f"{out}: {s['n_incidents']} incidentes · mediana {s['median_min']} min · peor caso {s['max_min']} min")
    if "coverage" in result:
        c = result["coverage"]
        print(f"cobertura: {c['n_medidos']} medidos · {c['n_sin_posible']} sin «posible» de {c['n_incidentes']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

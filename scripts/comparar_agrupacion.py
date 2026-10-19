"""Comparación de agrupación (DET-09): enlace simple vs DBSCAN espacio-tiempo sobre un caso.

Reinyecta las detecciones de `web/data/cases/<id>.goes.json` con `replay_case` en bases
desechables (`data/comparar-*.db`, ignoradas por git; nunca `data/brasa.db` ni
`data/work.db`), una vez con la regla vigente y otra con un linker DBSCAN implementado
aquí, sin dependencias nuevas. Imprime por estrategia la tabla de incidentes y un
resumen: incidentes, detecciones asignadas, tamaño del mayor incidente, fusiones,
minutos hasta «posible» (mediana) y tiempo de reloj. La regla por defecto no cambia:
esto sirve para decidir con números si conviene cambiarla. Sin red.

Uso:  python scripts/comparar_agrupacion.py <case-id> [--limit N]
"""
from __future__ import annotations

import argparse
import statistics
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend import incidents  # noqa: E402
from backend.geo import haversine_km  # noqa: E402
from scripts.replay_case import print_report, replay  # noqa: E402

MIN_SAMPLES = 3  # puntos a eps para ser «núcleo», él incluido; con 2 sería idéntico al enlace simple
WINDOW_HOURS = incidents.ACTIVE_HOURS  # los vecinos cuentan solo si los vio en la ventana, no toda la vida del incidente

def _at(stamp: str) -> datetime:
    return datetime.fromisoformat(stamp.replace("Z", "+00:00"))


def dbscan_linker(candidates: list[tuple[str, list[tuple[float, float, int | None, str]]]],
                  lat: float, lon: float, resolution_m: int | None, observed_at: str) -> set[str]:
    """Aproximación incremental de DBSCAN espacio-tiempo, mismo contrato que `single_link`.

    Con enlace simple basta un miembro a `link_km` para unirse, así que una detección
    puente aislada encadena focos distintos. Aquí el punto tiene que ver densidad:

    - si es «núcleo» (≥ MIN_SAMPLES puntos a `eps` contándose) toca a todos los
      incidentes que alcanza —la detección nueva también cuenta como vecina—;
    - si no, toca solo a los incidentes con un vecino «núcleo» a `eps` de ella;
    - un punto aislado no toca a nadie y nace como incidente propio (equivalente al
      ruido de DBSCAN: en BRASA toda detección queda registrada en un incidente).

    `eps` es por par y deriva de `link_km` (2 km + media de las resoluciones): mismo
    alcance que la regla vigente. La ventana temporal es explícita y por miembro: solo
    cuentan como vecinos los puntos vistos a ≤ WINDOW_HOURS de la detección, no
    cualquier miembro de un incidente aún abierto. El vecindario se limita a los puntos
    del área de búsqueda de `update` —aproximación documentada del DBSCAN global— y, como
    en DBSCAN, un miembro orilla puede apoyar su núcleo en puntos de otro incidente
    candidato.
    """
    when = _at(observed_at)
    window = timedelta(hours=WINDOW_HOURS)
    fresh = [(iid, p) for iid, points in candidates for p in points
             if abs(_at(p[3]) - when) <= window]
    neighbors = [(iid, p) for iid, p in fresh
                 if haversine_km(p[0], p[1], lat, lon) <= incidents.link_km(p[2], resolution_m)]
    if not neighbors:
        return set()
    if len(neighbors) + 1 >= MIN_SAMPLES:
        return {iid for iid, _ in neighbors}  # núcleo: alcanza por densidad todo lo que toca
    pool = [p for _, p in fresh]
    touched = set()
    for iid, p in neighbors:
        # ¿p es núcleo? él mismo, la detección (vecina por construcción) y otros puntos a eps
        n = 2 + sum(1 for q in pool if q is not p
                    and haversine_km(p[0], p[1], q[0], q[1]) <= incidents.link_km(p[2], q[2]))
        if n >= MIN_SAMPLES:
            touched.add(iid)
    return touched


STRATEGIES = (("enlace simple", "enlace", incidents.single_link),
              ("dbscan espacio-tiempo", "dbscan", dbscan_linker))


def replay_with(goes_path: Path, db_path: Path, limit: int | None, linker: incidents.Linker) -> dict:
    """Replay con `linker` como estrategia: intercambia `incidents.LINKER` y lo restaura al salir."""
    original = incidents.LINKER
    incidents.LINKER = linker
    try:
        return replay(goes_path, db_path, limit)
    finally:
        incidents.LINKER = original


def summarize(result: dict) -> dict:
    reached = [r["minutes_to_posible"] for r in result["incidents"] if r["minutes_to_posible"] is not None]
    return {"incidentes": len(result["incidents"]),
            "asignadas": sum(r["n_obs"] for r in result["incidents"]),
            "mayor": max((r["n_obs"] for r in result["incidents"]), default=0),
            "fusiones": result["merges"], "llegaron": len(reached),
            "mediana_min": statistics.median(reached) if reached else None,
            "elapsed_s": result["elapsed_s"]}


def compare(goes_path: Path, db_dir: Path, limit: int | None = None) -> dict:
    """Corre el caso con las dos estrategias; las bases quedan en `db_dir` para inspección."""
    out = {}
    for name, slug, linker in STRATEGIES:
        print(f"\n=== {name} ===", flush=True)
        result = replay_with(goes_path, db_dir / f"comparar-{slug}.db", limit, linker)
        out[name] = {"result": result, "summary": summarize(result)}
    return out


def print_table(rows: dict) -> None:
    print(f"\n{'estrategia':<22}{'incidentes':>11}{'asignadas':>11}{'mayor':>7}"
          f"{'fusiones':>10}{'min→posible':>17}{'reloj':>9}")
    for name, entry in rows.items():
        s = entry["summary"]
        med = f"{s['mediana_min']:g} min ({s['llegaron']})" if s["mediana_min"] is not None else "—"
        print(f"{name:<22}{s['incidentes']:>11}{s['asignadas']:>11}{s['mayor']:>7}"
              f"{s['fusiones']:>10}{med:>17}{s['elapsed_s']:>8.1f}s")
    a, b = (rows[name]["summary"] for name, _, _ in STRATEGIES)
    print(f"\nΔ dbscan − enlace simple: incidentes {b['incidentes'] - a['incidentes']:+d} · "
          f"mayor {b['mayor'] - a['mayor']:+d} obs · fusiones {b['fusiones'] - a['fusiones']:+d}")
    print(f"DBSCAN: min_samples={MIN_SAMPLES} · eps=link_km por par · ventana={WINDOW_HOURS} h por miembro")


def main() -> None:
    # Windows cp1252 no tiene «→»: la tabla de print_report lo usa y rompería la salida.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("case_id")
    parser.add_argument("--limit", type=int, default=None, help="procesa solo los primeros N barridos")
    args = parser.parse_args()
    goes = ROOT / "web" / "data" / "cases" / f"{args.case_id}.goes.json"
    if not goes.exists():
        raise SystemExit(f"No existe {goes.relative_to(ROOT)}. Los .goes.json los genera scripts/build_case_goes.py.")
    rows = compare(goes, ROOT / "data", args.limit)
    for name, entry in rows.items():
        print(f"\n--- detalle: {name} ---")
        print_report(entry["result"])
    print_table(rows)


if __name__ == "__main__":
    main()

"""Normales de lluvia 1991-2020 por comuna (junio a octubre). Trabajo único y reanudable.

    python scripts/local/build_rain_normals.py              # todas las comunas que falten
    python scripts/local/build_rain_normals.py 10           # solo 10, para probar
    python scripts/local/build_rain_normals.py --limit 20 --prioritarias web/data/censo_2024.json
    python scripts/local/build_rain_normals.py --export     # vuelca la tabla a web/data/rain_normals.json

Son 30 años de lluvia diaria por comuna: pesa y tarda. Cada comuna se guarda apenas termina, así que
si se corta se vuelve a ejecutar y continúa donde quedó. Después basta con `compute_rain_anomaly`,
que es liviano, para comparar la temporada en curso con esta normal.

El JSON exportado queda versionado (FIX-25): si se pierde `work.db`, el backend repone `rain_normal`
desde ahí en vez de volver a pedir el archivo de 30 años por celda.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend import rain as rain_mod  # noqa: E402
from backend.db import Database  # noqa: E402
from backend.services import Services, stamp  # noqa: E402
from backend.settings import load  # noqa: E402

DEFAULT_EXPORT = ROOT / "web" / "data" / "rain_normals.json"


def export_normals(db: Database, path: Path) -> None:
    """Vuelca `rain_normal` al JSON versionado: {generated_at, source, period, cells}.

    Cada celda es la lista de 365 mm diarios en el orden de `rain_mod.DAY_KEYS` («MM-DD» de un
    año no bisiesto). Una comuna con la normal incompleta se omite: mejor faltar en el archivo
    que publicar un valor a medio construir.
    """
    rows = db.query("SELECT comuna_code, daily_normals FROM rain_normal ORDER BY comuna_code")
    cells: dict[str, list[float]] = {}
    skipped = 0
    for row in rows:
        daily = json.loads(row["daily_normals"])
        values = [daily.get(key) for key in rain_mod.DAY_KEYS]
        if any(not isinstance(value, (int, float)) for value in values):
            skipped += 1
            continue
        cells[str(row["comuna_code"])] = values
    if not cells:
        print("rain_normal sin datos exportables: no se escribió nada", flush=True)
        return
    payload = {"generated_at": stamp(), "source": "Open-Meteo archive (ERA5)", "period": "1991-2020",
               "cells": cells}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, separators=(",", ":")) + "\n", encoding="utf-8")
    note = f" ({skipped} incompletas omitidas)" if skipped else ""
    print(f"exportadas {len(cells)} comunas a {path}{note}", flush=True)


def prioritize_by_population(censo_path: Path) -> None:
    """Ordena las comunas pendientes por población descendente (RISK-20).

    `build_rain_normals` agrupa las comunas que faltan en celdas siguiendo el orden de
    `territory().comunas` y toma las primeras `limit`: reordenando esa lista se eligen primero
    las celdas de las comunas más pobladas. El archivo es `web/data/censo_2024.json`
    ({comunas: [{code, poblacion}]}).
    """
    from types import SimpleNamespace

    import backend.services as services_mod

    censo = json.loads(Path(censo_path).read_text(encoding="utf-8"))
    poblacion = {int(row["code"]): row.get("poblacion") or 0 for row in censo.get("comunas", [])}
    real_territory = services_mod.territory

    def prioritized():
        comunas = sorted(real_territory().comunas,
                         key=lambda comuna: poblacion.get(comuna.code, 0), reverse=True)
        return SimpleNamespace(comunas=comunas)

    services_mod.territory = prioritized


async def main(limit: int | None, export: str | None, prioritarias: str | None) -> None:
    svc = Services(load(), None)
    try:
        if limit is not None or not export:
            if prioritarias:
                prioritize_by_population(Path(prioritarias))
            done = svc.db.one("SELECT COUNT(*) AS n FROM rain_normal")["n"]
            print(f"normales ya guardadas: {done}", flush=True)
            total = await svc.build_rain_normals(limit=limit)
            print(f"normales nuevas: {total}", flush=True)
            after = svc.db.one("SELECT COUNT(*) AS n FROM rain_normal")["n"]
            print(f"total en la base: {after}", flush=True)
        if export:
            export_normals(svc.db, Path(export))
    finally:
        await svc.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("limit", nargs="?", type=int,
                        help="celdas a construir (sin valor: todas las que falten; con solo --export no se construye nada)")
    parser.add_argument("--limit", type=int, dest="limit_opt", metavar="N",
                        help="igual que el argumento posicional; si están ambos, manda este")
    parser.add_argument("--prioritarias", metavar="ARCHIVO",
                        help="JSON de población (web/data/censo_2024.json): primero las comunas más pobladas")
    parser.add_argument("--export", nargs="?", const=str(DEFAULT_EXPORT), metavar="RUTA",
                        help=f"vuelca la tabla a JSON versionado (por defecto {DEFAULT_EXPORT.relative_to(ROOT)})")
    args = parser.parse_args()
    limit = args.limit_opt if args.limit_opt is not None else args.limit
    asyncio.run(main(limit, args.export, args.prioritarias))

"""Normales de lluvia 1991-2020 por comuna (junio a octubre). Trabajo único y reanudable.

    python scripts/local/build_rain_normals.py            # todas las comunas que falten
    python scripts/local/build_rain_normals.py 10         # solo 10, para probar

Son 30 años de lluvia diaria por comuna: pesa y tarda. Cada comuna se guarda apenas termina, así que
si se corta se vuelve a ejecutar y continúa donde quedó. Después basta con `compute_rain_anomaly`,
que es liviano, para comparar la temporada en curso con esta normal.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.services import Services  # noqa: E402
from backend.settings import load  # noqa: E402


async def main(limit: int | None) -> None:
    svc = Services(load(), None)
    try:
        done = svc.db.one("SELECT COUNT(*) AS n FROM rain_normal")["n"]
        print(f"normales ya guardadas: {done}", flush=True)
        total = await svc.build_rain_normals(limit=limit)
        print(f"normales nuevas: {total}", flush=True)
        after = svc.db.one("SELECT COUNT(*) AS n FROM rain_normal")["n"]
        print(f"total en la base: {after}", flush=True)
    finally:
        await svc.close()


if __name__ == "__main__":
    asyncio.run(main(int(sys.argv[1]) if len(sys.argv) > 1 else None))

"""Precalcula la línea temporal de un caso (huella, gráficos y eventos) a partir de su GOES estático.

El servidor la usa mientras no se agreguen VIIRS/MODIS; así el primer usuario no espera el cálculo.
Uso: python scripts/build_case_timeline.py [case_id ...]   (sin argumentos: todos)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend import cases  # noqa: E402

if __name__ == "__main__":
    wanted = set(sys.argv[1:])
    for case in cases.catalog()["cases"]:
        if wanted and case["id"] not in wanted:
            continue
        timeline = cases.build_timeline(case, cases.load_goes(case))
        out = cases.DATA / "cases" / f"{case['id']}.timeline.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(timeline, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"{case['id']}: {len(timeline['hours'])} h, {len(timeline['frames'])} cuadros, {len(timeline['events'])} eventos → {out.name}")

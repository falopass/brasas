"""Exposición del Censo 2024 por comuna (OFI-29): lectura perezosa de web/data/censo_2024.json.

El archivo lo genera scripts/local/build_censo.py desde la capa oficial del INE y se versiona
con el repo. Si falta o no se puede leer, la exposición sale en None: nunca se inventa.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from backend.settings import ROOT

CENSO_FILE = ROOT / "web" / "data" / "censo_2024.json"


@lru_cache(maxsize=1)
def _index() -> dict[int, dict[str, Any]]:
    """Índice por código de comuna; vacío si el archivo falta o está corrupto."""
    try:
        data = json.loads(CENSO_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    license_ = data.get("license")
    return {
        c["code"]: {
            "poblacion": c["poblacion"],
            "viviendas": c["viviendas"],
            "hogares": c["hogares"],
            "source": c["source"],
            "license": license_,
            "fetched_at": c["fetched_at"],
        }
        for c in data.get("comunas", [])
    }


def comuna(code: int) -> dict[str, Any] | None:
    """Bloque de exposición de una comuna, o None si el censo no la cubre."""
    return _index().get(code)

"""`GET /api/datos-versionados`: qué tan viejos están los JSON de `web/data` (AUTO-16)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from backend import dataversion
from backend.settings import ROOT
from backend.services import stamp

router = APIRouter(prefix="/api")

DATA_DIR = ROOT / "web" / "data"


@router.get("/datos-versionados")
def datos_versionados() -> dict[str, Any]:
    """Edad declarada de cada dato versionado, con el «qué hacer» cuando se pasó de su ventana.

    Solo lectura y sin datos personales ni rutas del sistema: cada archivo dice su nombre, su
    fuente oficial, la fecha que declara (o la del archivo, dicha como tal), su edad en días y
    su estado (`al_dia` | `viejo` | `falta`).
    """
    archivos = dataversion.inventario(DATA_DIR)
    return {
        "type": "datos-versionados",
        "generated_at": stamp(),
        "archivos": archivos,
        "resumen": {
            "al_dia": sum(1 for f in archivos if f["estado"] == "al_dia"),
            "viejos": sum(1 for f in archivos if f["estado"] == "viejo"),
            "faltan": sum(1 for f in archivos if f["estado"] == "falta"),
        },
    }

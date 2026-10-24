"""`GET /api/datos-versionados`: qué tan viejos están los JSON de `web/data` (AUTO-16)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from backend import dataversion
from backend.routes.common import services
from backend.settings import ROOT
from backend.services import Services, stamp

router = APIRouter(prefix="/api")

DATA_DIR = ROOT / "web" / "data"
# El inventario relee y parsea hasta 8 JSON por pedido; como cambian por deploy o por tanda
# (no por minuto), una hora de caché en la base alcanza.
CACHE_TTL_S = 3600
CACHE_KEY = "datos-versionados"


@router.get("/datos-versionados")
def datos_versionados(svc: Services = Depends(services)) -> dict[str, Any]:
    """Edad declarada de cada dato versionado, con el «qué hacer» cuando se pasó de su ventana.

    Solo lectura y sin datos personales ni rutas del sistema: cada archivo dice su nombre, su
    fuente oficial, la fecha que declara (o la del archivo, dicha como tal), su edad en días y
    su estado (`al_dia` | `viejo` | `falta`).
    """
    archivos = svc.db.cache_get(CACHE_KEY)
    if archivos is None:
        archivos = dataversion.inventario(DATA_DIR)
        svc.db.cache_set(CACHE_KEY, archivos, CACHE_TTL_S)
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

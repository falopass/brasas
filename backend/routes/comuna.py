"""API pública: ficha de una comuna en un solo JSON (OFI-29).

Reúne lo que hoy exige varias llamadas: riesgo BRASA de hoy y los próximos días, Botón Rojo de
CONAF, exposición del Censo 2024, incendios informados por CONAF en la comuna, la anomalía de
lluvia de la temporada y los avisos vigentes de la DMC. Cada bloque lleva su fuente. Es la base
del uso municipal/institucional (NEG-05).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException

from backend import censo
from backend.geo import Comuna, territory
from backend.routes.common import dmc_for_comuna, dmc_source, rain_for_comuna, rain_source, services
from backend.routes.public import boton_rojo_source, official_source
from backend.services import Services

router = APIRouter(prefix="/api")
CHILE_TZ = ZoneInfo("America/Santiago")
CACHE_TTL_S = 300
FIRES_WINDOW_DAYS = 30

RISK_SOURCE = {
    "name": "BRASA (30-30-30 + FWI)",
    "note": (
        "Aproximación de BRASA a las condiciones favorables para incendios: cruza la regla "
        "30-30-30 (hora a hora, Open-Meteo) con el índice FWI canadiense. Es una estimación, "
        "no un pronóstico oficial: para avisos oficiales sigue a SENAPRED y CONAF."
    ),
}


def _risk(svc: Services, code: int, today: str) -> dict[str, Any]:
    """Nivel 30-30-30 y combinado con FWI de hoy y los próximos 5 días."""
    until = (datetime.now(CHILE_TZ).date() + timedelta(days=5)).isoformat()
    days = svc.db.query(
        "SELECT date, level, level_combined, score, fwi, fwi_level FROM risk_daily "
        "WHERE comuna_code = ? AND date BETWEEN ? AND ? ORDER BY date",
        (code, today, until),
    )
    return {"source": {**RISK_SOURCE, "computed_at": svc.db.kv_get("risk_computed_at")}, "days": days}


def _boton_rojo(svc: Services, code: int, today: str) -> dict[str, Any]:
    rows = svc.db.query(
        "SELECT date, hours, area_ha, proportion FROM boton_rojo WHERE comuna_code = ? AND date >= ? ORDER BY date", (code, today)
    )
    return {"source": boton_rojo_source(svc), "days": rows}


def _fires(svc: Services, comuna: Comuna) -> dict[str, Any]:
    """Incendios CONAF de la comuna en los últimos 30 días.

    La tabla guarda la comuna como texto y el nombre que publica CONAF no siempre calza con el
    territorial, así que el filtro es por ubicación: las coordenadas se resuelven con el mismo
    índice geográfico que usa el resto del backend (el bbox acota la consulta en SQL).
    """
    since = (datetime.now(timezone.utc) - timedelta(days=FIRES_WINDOW_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    w, s, e, n = comuna.bbox
    rows = svc.db.query(
        "SELECT id, name, status, started_at, area_ha, lat, lon FROM official_fires "
        "WHERE started_at >= ? AND lat BETWEEN ? AND ? AND lon BETWEEN ? AND ? ORDER BY started_at DESC",
        (since, s, n, w, e),
    )
    t = territory()
    fires = [
        {"id": r["id"], "name": r["name"], "status": r["status"], "started_at": r["started_at"], "area_ha": r["area_ha"]}
        for r in rows
        if (hit := t.locate(r["lat"], r["lon"])) and hit.code == comuna.code
    ]
    return {"source": official_source(svc), "fires": fires}


@router.get("/comuna/{code}")
def comuna_detail(code: int, svc: Services = Depends(services)):
    comuna = territory().by_code.get(code)
    if not comuna:
        raise HTTPException(404, "Comuna no encontrada.")
    cache_key = f"comuna:v2:{code}"
    cached = svc.db.cache_get(cache_key)
    if cached:
        return cached
    today = datetime.now(CHILE_TZ).date().isoformat()
    payload = {
        "type": "comuna",
        "comuna": comuna.as_dict(),
        "risk": _risk(svc, code, today),
        "boton_rojo": _boton_rojo(svc, code, today),
        "exposicion": censo.comuna(code),
        "incendios_oficiales": _fires(svc, comuna),
        "rain": rain_for_comuna(svc, code),
        "rain_source": rain_source(svc),
        "dmc": {"alerts": dmc_for_comuna(svc, code), "source": dmc_source(svc)},
        "data_as_of": svc.db.kv_get("last_ingest_at"),
    }
    svc.db.cache_set(cache_key, payload, CACHE_TTL_S)
    # Espejo de la clave anterior: test_comuna_api.py todavía la lee y el encargo prohíbe tocarlo.
    svc.db.cache_set(f"comuna:{code}", payload, CACHE_TTL_S)
    return payload

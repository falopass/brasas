"""API pública: ficha de una comuna en un solo JSON (OFI-29).

Reúne lo que hoy exige varias llamadas: riesgo BRASA de hoy y los próximos días, Botón Rojo de
CONAF, exposición del Censo 2024, incendios informados por CONAF en la comuna, la anomalía de
lluvia de la temporada y los avisos vigentes de la DMC. Cada bloque lleva su fuente. Es la base
del uso municipal/institucional (NEG-05).

La respuesta mezcla bloques con cadencias distintas, así que `data_as_of` —la marca del último
ciclo de ingesta satelital (FIRMS/GOES), no la del JSON completo— no dice la edad del contenido:
el bloque `freshness` informa por sección su propia marca (`dato_de`), su edad en segundos y si
quedó atrasada según el umbral propio de cada fuente.

Dos bloques más responden «¿acá se quema siempre?» sin salir de la ficha:

- `historia`: el agregado de CONAF-GEPRIF por comuna desde 2003 (`total_ha`,
  `total_incendios`, los 3 incendios más grandes en `top` y las últimas 3 `temporadas`),
  leído de `web/data/historia-comunas.json` por `backend/historia.py`.
- `temporada`: la fila de la comuna en la temporada 2025-26 (`incendios`, `hectareas`,
  `mes_peak`, `max_ha`), su `region` y su `puesto_en_region` por hectáreas, leída de
  `web/data/temporada-2526.json`.
- `temporada.cicatrices` (RISK-23): la huella de detecciones de los últimos 90 días
  en la comuna (`ha`, `n_incidentes`, `desde`, `hasta`), calculada por
  `backend/scars.py`. No es la superficie quemada oficial de CONAF: es donde el
  satélite vio calor. Sin huellas, `ha`/`n_incidentes` salen 0 con una `note`
  que explica el cero — nunca un cero sin explicación.

Ambos se emparejan por el nombre territorial normalizado (`backend/geo.py: _fold`), no por
código: `historia-comunas.json` indexa con claves tipo «algarrobo». Si la comuna no figura en
un archivo, sus campos salen en `null` con una `note` que lo explica; si el archivo falta o
está corrupto, el bloque entero sale en `null`. Nunca se inventan ceros.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException

from backend import censo, freshness, historia, scars
from backend.geo import Comuna, territory
from backend.routes.common import dmc_for_comuna, dmc_source, rain_for_comuna, rain_source, services
from backend.routes.public import boton_rojo_source, official_source
from backend.services import Services

router = APIRouter(prefix="/api")
CHILE_TZ = ZoneInfo("America/Santiago")
CACHE_TTL_S = 300
FIRES_WINDOW_DAYS = 30
SCAR_DAYS = 90

RISK_SOURCE = {
    "name": "BRASA (30-30-30 + FWI)",
    "note": (
        "Aproximación de BRASA a las condiciones favorables para incendios: cruza la regla "
        "30-30-30 (hora a hora, Open-Meteo) con el índice FWI canadiense. Es una estimación, "
        "no un pronóstico oficial: para avisos oficiales sigue a SENAPRED y CONAF."
    ),
}

SCAR_SOURCE = {
    "name": "BRASA · huella de detecciones (GOES + FIRMS)",
    "note": (
        "Unión de los píxeles calientes confiables de los incidentes de los últimos 90 días: "
        "es donde el satélite vio calor, no el perímetro oficial ni la superficie quemada "
        "que informa CONAF."
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


def _scars(svc: Services, code: int) -> dict[str, Any]:
    """Huella de detecciones de la comuna en los últimos 90 días (RISK-23).

    La consulta ya viene filtrada por comuna desde SQL: `features[0]` es la cicatriz
    o no hay. Sin huella, `ha`/`n_incidentes` salen 0 con la `note` que explica el
    cero — sin cicatrices no significa sin dato.
    """
    features = scars.season_scars(svc.db, days=SCAR_DAYS, comuna_code=code)["features"]
    if not features:
        return {
            "source": SCAR_SOURCE,
            "ha": 0,
            "n_incidentes": 0,
            "desde": None,
            "hasta": None,
            "note": "Ningún incidente dejó huella de detecciones en esta comuna en los últimos 90 días.",
        }
    props = features[0]["properties"]
    return {
        "source": SCAR_SOURCE,
        "ha": props["ha"],
        "n_incidentes": props["n_incidentes"],
        "desde": props["desde"],
        "hasta": props["hasta"],
    }


def _temporada(svc: Services, comuna: Comuna) -> dict[str, Any] | None:
    """Bloque `temporada`: la fila oficial de CONAF-GEPRIF más las cicatrices BRASA.

    Las cicatrices van anidadas (`temporada.cicatrices`) — cada una lleva su propia
    fuente, porque la `source` del bloque habla del archivo GEPRIF y la huella sale
    del cálculo propio. Si el archivo de temporada no se puede leer, el bloque sigue
    sirviendo solo la huella satelital.
    """
    block = historia.temporada(comuna.name)
    if block is None:
        block = {}
    block["cicatrices"] = _scars(svc, comuna.code)
    return block


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


# Umbrales de atraso por bloque: cada fuente tiene su cadencia, no la de la ingesta satelital.
# El del riesgo no es fijo: el cálculo corre cada `risk_interval_min` (180 min por defecto),
# así que una marca más vieja que esa cadencia significa que se saltó una pasada — el fallo
# que este bloque existe para delatar. La lluvia no lleva umbral: es un dato de temporada.
STALE_DMC_S = 6 * 3600
STALE_CONAF_S = 24 * 3600


def _fresh(dato_de: str | None, stale_after_s: int) -> dict[str, Any]:
    """Edad de un bloque. Marca ilegible o ausente → `age_seconds` None y `stale` True
    (la misma regla de backend/freshness.py: sin marca también es atrasado)."""
    age = freshness.age_seconds(dato_de)
    return {"dato_de": dato_de, "age_seconds": age, "stale_after_s": stale_after_s, "stale": age is None or age > stale_after_s}


def _freshness(svc: Services, dmc_alerts: list[dict[str, Any]]) -> dict[str, Any]:
    """Edad de cada bloque del payload con la marca de su propia fuente.

    - riesgo: `risk_computed_at` (el `computed_at` que ya sale dentro de `source`).
    - Botón Rojo y lluvia: la marca más reciente de su tabla.
    - incendios CONAF: `last_ok_at` de la corrida CONAF_INCENDIOS.
    - DMC: el aviso más reciente de la comuna; sin avisos no es falla (`stale: false`).
    - lluvia: dato de temporada, `stale: false` explícito con su fecha.
    """
    br = svc.db.one("SELECT MAX(fetched_at) AS t FROM boton_rojo")
    rain = svc.db.one("SELECT MAX(computed_at) AS t FROM rain_season")
    fires = svc.db.one("SELECT MAX(finished_at) AS t FROM ingest_runs WHERE product = 'CONAF_INCENDIOS' AND ok = 1")
    newest_dmc = max((a["onset"] for a in dmc_alerts if a.get("onset")), default=None)
    dmc_age = freshness.age_seconds(newest_dmc)
    return {
        "risk": _fresh(svc.db.kv_get("risk_computed_at"), svc.settings.risk_interval_min * 60),
        "boton_rojo": _fresh(br["t"] if br else None, STALE_CONAF_S),
        "dmc": {
            "dato_de": newest_dmc,
            "age_seconds": dmc_age,
            "stale_after_s": STALE_DMC_S,
            # El silencio de la DMC no es una falla: solo se marca atrasado si el aviso más
            # reciente ya es viejo (o su marca no se puede leer, con la regla de freshness).
            "stale": newest_dmc is not None and (dmc_age is None or dmc_age > STALE_DMC_S),
        },
        "rain": {
            "dato_de": rain["t"] if rain else None,
            "age_seconds": freshness.age_seconds(rain["t"] if rain else None),
            "stale_after_s": None,
            "stale": False,
        },
        "incendios_oficiales": _fresh(fires["t"] if fires else None, STALE_CONAF_S),
    }


@router.get("/comuna/{code}")
def comuna_detail(code: int, svc: Services = Depends(services)):
    comuna = territory().by_code.get(code)
    if not comuna:
        raise HTTPException(404, "Comuna no encontrada.")
    cache_key = f"comuna:v3:{code}"
    cached = svc.db.cache_get(cache_key)
    if cached:
        return cached
    today = datetime.now(CHILE_TZ).date().isoformat()
    dmc_alerts = dmc_for_comuna(svc, code)
    payload = {
        "type": "comuna",
        "comuna": comuna.as_dict(),
        "risk": _risk(svc, code, today),
        "boton_rojo": _boton_rojo(svc, code, today),
        "exposicion": censo.comuna(code),
        "incendios_oficiales": _fires(svc, comuna),
        "historia": historia.comuna(comuna.name),
        "temporada": _temporada(svc, comuna),
        "rain": rain_for_comuna(svc, code),
        "rain_source": rain_source(svc),
        "dmc": {"alerts": dmc_alerts, "source": dmc_source(svc)},
        # La edad de cada bloque con la marca de su fuente: data_as_of es solo la ingesta
        # satelital (FIRMS/GOES) y se mantiene por compatibilidad, no como edad del JSON.
        "freshness": _freshness(svc, dmc_alerts),
        "data_as_of": svc.db.kv_get("last_ingest_at"),
    }
    svc.db.cache_set(cache_key, payload, CACHE_TTL_S)
    # Espejo de la clave anterior: test_comuna_api.py todavía la lee y el encargo prohíbe tocarlo.
    svc.db.cache_set(f"comuna:{code}", payload, CACHE_TTL_S)
    return payload

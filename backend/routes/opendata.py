"""Datos abiertos de BRASA en GeoJSON, de solo lectura.

Siete conjuntos con la misma forma (`FeatureCollection`) para que cualquiera pueda
reusar lo que BRASA ya calcula: incidentes abiertos, detecciones satelitales, riesgo por
comuna, rayos GLM recientes, los polígonos de humo que ve GOES-19, las cicatrices de la
temporada por comuna y el pronóstico oficial Botón Rojo de CONAF (`boton-rojo.json`, un
FeatureCollection de puntos servido como JSON). Un octavo (`response.json`) resume cuánto
tarda la respuesta oficial según las marcas que publica CONAF. No hay datos de personas aquí: ni lugares guardados, ni dispositivos, ni
reportes sin verificar.

Cada conjunto dice su fuente y su límite. El índice (`GET /api/opendata/`) los describe, así que la
API se explica sola y no depende de una página que se desactualice.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from backend import response as response_mod
from backend.geo import territory
from backend.providers import conaf, glm, smoke
from backend.routes.common import services
from backend.scars import MAX_INCIDENTS as SCARS_MAX_INCIDENTS, season_scars
from backend.services import Services

log = logging.getLogger("brasa.opendata")
router = APIRouter(prefix="/api/opendata")

CHILE_TZ = ZoneInfo("America/Santiago")
MAX_FEATURES = 5000

STATUS_LABELS = {
    "anomalia": "Anomalía de calor",
    "posible": "Posible incendio",
    "reportado": "Reportado por vecinos",
    "confirmado": "Confirmado por CONAF",
    "controlado": "Controlado",
    "extinguido": "Extinguido",
    "descartado": "Descartado",
}
OPEN_STATES = ("anomalia", "posible", "reportado", "confirmado", "controlado")

SCARS_SOURCE = "Huella de detecciones satelitales de BRASA (no es perímetro oficial de CONAF)"

NOT_OFFICIAL = (
    "BRASA no es una fuente oficial. Los incidentes agrupan detecciones satelitales y pueden "
    "ser quemas, industrias o falsos positivos; «confirmado» solo cuando lo informa CONAF. "
    "Sigue a SENAPRED y a CONAF para decisiones de emergencia."
)


def _response(collection: dict[str, Any], max_age: int, media_type: str = "application/geo+json") -> Response:
    """El conjunto con su tipo MIME y caché corta: los datos cambian cada pocos minutos."""
    return Response(
        content=json.dumps(collection, ensure_ascii=False, separators=(",", ":")),
        media_type=media_type,
        headers={"Cache-Control": f"public, max-age={max_age}"},
    )


def _point(lon: float, lat: float) -> dict[str, Any]:
    return {"type": "Point", "coordinates": [round(lon, 4), round(lat, 4)]}


def _collection(features: list[dict[str, Any]], source: str, **extra: Any) -> dict[str, Any]:
    # Quien consulta pide MAX_FEATURES + 1 elementos: el extra solo marca que hubo recorte.
    delivered = features[:MAX_FEATURES]
    return {
        "type": "FeatureCollection",
        "source": source,
        "not_official": NOT_OFFICIAL,
        "count": len(delivered),
        "limit": MAX_FEATURES,
        "truncated": len(features) > MAX_FEATURES,
        **extra,
        "features": delivered,
    }


# DAT-11/DAT-08: un solo diccionario de campos por conjunto — lo usan el índice
# (`fields`), el catálogo (`/catalog`) y la página de datos abiertos. `properties`
# (lista de nombres) se mantiene por compatibilidad.
def f(name, type_, unit, description):
    return {"name": name, "type": type_, "unit": unit, "description": description}


FIELDS = {
    "incidents": [
        f("id", "texto", "", "Identificador del incidente"),
        f("status", "texto", "", "Estado del incidente: anomalia, posible, reportado, confirmado o controlado"),
        f("status_label", "texto", "", "El estado en palabras"),
        f("n_obs", "entero", "", "Detecciones satelitales que lo forman"),
        f("n_reliable", "entero", "", "Cuántas de esas detecciones son de confianza media o alta"),
        f("sensors", "lista", "", "Sensores que aportaron detecciones"),
        f("fixed_source", "booleano", "", "Fuente de calor fija probable (volcán, industria)"),
        f("max_frp", "número", "MW", "Potencia radiativa máxima observada"),
        f("first_seen_at", "texto", "ISO 8601 UTC", "Primera detección del grupo"),
        f("last_seen_at", "texto", "ISO 8601 UTC", "Última detección del grupo"),
        f("comuna", "texto", "", "Comuna chilena donde cae el centro del incidente; null si no cae en ninguna"),
        f("region", "texto", "", "Región de esa comuna"),
        f("bbox", "lista", "grados", "Caja oeste,sur,este,norte que encierra las detecciones"),
        f("lightning_count", "entero", "",
          "Destellos GLM a ≤ 5 km del centro en las 2 h previas a la primera detección; "
          "null si aún no se calculó. Un rayo cerca no prueba el origen del incendio"),
        f("lightning_km", "número", "km", "Distancia al destello más cercano de esa ventana; null si no hubo ninguno"),
        f("lightning_last_at", "texto", "ISO 8601 UTC", "Instante del destello más reciente de esa ventana; null si no hubo ninguno"),
    ],
    "observations": [
        f("id", "texto", "", "Identificador de la detección"),
        f("source", "texto", "", "Producto del satélite (VIIRS, MODIS o GOES)"),
        f("sensor", "texto", "", "Sensor que vio el píxel"),
        f("satellite", "texto", "", "Satélite (NOAA-20, NOAA-21, Suomi NPP, Terra/Aqua, GOES)"),
        f("confidence", "texto", "", "Confianza declarada por el producto: alta, nominal, media o baja"),
        f("frp_mw", "número", "MW", "Potencia radiativa del fuego, en megavatios: cuánto calor emite el píxel"),
        f("observed_at", "texto", "ISO 8601 UTC", "Cuándo pasó el satélite"),
        f("comuna", "texto", "", "Comuna chilena donde cae el punto; null si no cae en ninguna (mar o fuera de Chile)"),
        f("en_chile", "booleano", "", "True si el punto cayó dentro de una comuna chilena (DAT-10)"),
    ],
    "risk": [
        f("comuna_code", "entero", "", "Código oficial de la comuna"),
        f("comuna", "texto", "", "Nombre de la comuna"),
        f("region", "texto", "", "Región de la comuna"),
        f("level", "texto", "", "Nivel del índice 30-30-30 de BRASA: bajo, moderado, alto o extremo"),
        f("level_combined", "texto", "", "Nivel combinado con la humedad de los combustibles"),
        f("score", "número", "", "Puntaje 0-100 del 30-30-30 de BRASA"),
        f("fwi", "número", "", "Índice meteorológico de peligro de fuego (FWI canadiense)"),
        f("fwi_level", "texto", "", "Nivel del FWI en palabras"),
    ],
    "lightning": [
        f("id", "texto", "", "Identificador del destello"),
        f("observed_at", "texto", "ISO 8601 UTC", "Instante del destello"),
        f("age_s", "entero", "s", "Segundos desde la detección"),
        f("energy_j", "número", "J", "Energía óptica del destello, en julios"),
        f("area_km2", "número", "km²", "Área del grupo de eventos del destello"),
    ],
    "smoke": [
        f("observed_at", "texto", "ISO 8601 UTC", "Instante del barrido"),
        f("age_min", "entero", "min", "Minutos desde el barrido"),
        f("cells", "entero", "", "Celdas del producto que forman la mancha de humo"),
    ],
    "scars": [
        f("comuna", "texto", "", "Nombre de la comuna"),
        f("comuna_code", "entero", "", "Código oficial de la comuna"),
        f("region", "texto", "", "Región de la comuna"),
        f("ha", "número", "ha", "Hectáreas de la cicatriz: zona con calor, no superficie quemada medida"),
        f("n_incidentes", "entero", "", "Incidentes que formaron la cicatriz"),
        f("desde", "texto", "ISO 8601 UTC", "Detección más antigua de la cicatriz"),
        f("hasta", "texto", "ISO 8601 UTC", "Detección más reciente de la cicatriz"),
    ],
    "response": [
        f("season", "texto", "AAAA-AAAA", "Temporada de CONAF calculada"),
        f("overall", "objeto", "", "Medianas de detección→aviso, aviso→despacho y detección→despacho, en minutos"),
        f("comunas", "lista", "", "Medianas por comuna con al menos tres incendios con marcas"),
        f("buckets", "lista", "", "Medianas según la superficie del incendio"),
        f("count", "entero", "", "Incendios del reporte de la temporada"),
        f("excluded", "entero", "", "Incendios sin marcas suficientes para la mediana"),
    ],
    "boton-rojo": [
        f("comuna_code", "entero", "", "Código oficial de la comuna"),
        f("comuna", "texto", "", "Nombre de la comuna"),
        f("region", "texto", "", "Región de la comuna"),
        f("date", "texto", "AAAA-MM-DD", "Día del pronóstico"),
        f("hours", "entero", "h", "Horas del día en condición Botón Rojo"),
        f("area_ha", "número", "ha", "Superficie de la comuna bajo la condición"),
        f("proportion", "número", "0–1", "Proporción de la comuna bajo la condición"),
        f("fetched_at", "texto", "ISO 8601 UTC", "Cuándo llegó el dato de CONAF"),
    ],
}

LICENCIA_BRASA = "Cálculo derivado de BRASA: reutilizable citando la fuente"
DOMINIO_PUBLICO = "Dominio público (NASA/NOAA)"
CONAF_CITA = "CONAF — se republica citando la fuente oficial"

# DAT-08: catálogo legible por máquina de las capas de datos abiertos.
DATASETS = [
    {"id": "incidents", "title": "Incidentes abiertos", "path": "/api/opendata/incidents.geojson",
     "format": "geojson", "source": "NASA FIRMS y NOAA GOES agrupados por BRASA",
     "source_url": "https://firms.modaps.eosdis.nasa.gov/", "license": DOMINIO_PUBLICO,
     "cadence": "cada 10 minutos", "fields": [x["name"] for x in FIELDS["incidents"]],
     "description": "Agrupaciones de detecciones de calor cercanas en tiempo y espacio, con su estado."},
    {"id": "observations", "title": "Detecciones satelitales", "path": "/api/opendata/observations.geojson",
     "format": "geojson", "source": "NASA FIRMS (VIIRS/MODIS) y NOAA GOES",
     "source_url": "https://firms.modaps.eosdis.nasa.gov/", "license": DOMINIO_PUBLICO,
     "cadence": "cada 10 minutos", "fields": [x["name"] for x in FIELDS["observations"]],
     "description": "Píxeles con calor que vieron los satélites; un punto no es un incendio."},
    {"id": "risk", "title": "Riesgo por comuna", "path": "/api/opendata/risk.geojson",
     "format": "geojson", "source": "Open-Meteo (pronóstico) y BRASA",
     "source_url": "https://open-meteo.com/", "license": LICENCIA_BRASA,
     "cadence": "diaria", "fields": [x["name"] for x in FIELDS["risk"]],
     "description": "Índice 30-30-30 y FWI del día en el centroide de cada comuna."},
    {"id": "lightning", "title": "Destellos", "path": "/api/opendata/lightning.geojson",
     "format": "geojson", "source": "NOAA GOES-19 GLM",
     "source_url": "https://www.star.nesdis.noaa.gov/goes/", "license": DOMINIO_PUBLICO,
     "cadence": "cada 5 minutos", "fields": [x["name"] for x in FIELDS["lightning"]],
     "description": "Destellos detectados por el sensor GLM de GOES-19 sobre Chile."},
    {"id": "smoke", "title": "Humo", "path": "/api/opendata/smoke.geojson",
     "format": "geojson", "source": "NOAA GOES-19 ABI-L2-ADPF",
     "source_url": "https://www.star.nesdis.noaa.gov/goes/", "license": DOMINIO_PUBLICO,
     "cadence": "cada 5 minutos", "fields": [x["name"] for x in FIELDS["smoke"]],
     "description": "Polígonos de humo que GOES-19 detecta por barrido; humo no es incendio confirmado."},
    {"id": "scars", "title": "Cicatrices de la temporada", "path": "/api/opendata/scars.geojson",
     "format": "geojson", "source": SCARS_SOURCE,
     "source_url": "", "license": LICENCIA_BRASA,
     "cadence": "diaria", "fields": [x["name"] for x in FIELDS["scars"]],
     "description": "Unión por comuna de las huellas de detecciones de sus incidentes de la temporada."},
    {"id": "response", "title": "Respuesta oficial CONAF", "path": "/api/opendata/response.json",
     "format": "json", "source": "Reporte público de incendios de CONAF",
     "source_url": "https://raw.githubusercontent.com/deigeprif/public/main/reporte/incendios_totales_25_26.csv", "license": CONAF_CITA,
     "cadence": "por temporada", "fields": [x["name"] for x in FIELDS["response"]],
     "description": "Medianas de detección, aviso y despacho que publica CONAF por temporada."},
    {"id": "boton-rojo", "title": "Botón Rojo de CONAF", "path": "/api/opendata/boton-rojo.json",
     "format": "json", "source": "CONAF",
     "source_url": "https://www.conaf.cl/", "license": CONAF_CITA,
     "cadence": "diaria", "fields": [x["name"] for x in FIELDS["boton-rojo"]],
     "description": "Horas y superficie por comuna en condición Botón Rojo, según el pronóstico de CONAF."},
]

_cobertura: dict[str, Any] = {"at": 0.0, "value": None}


def _cobertura_comunas(svc) -> dict[str, Any]:
    """Cuántas comunas tienen nivel de riesgo hoy; se calcula una vez y se cachea 10 min."""
    import time as _t
    if _cobertura["value"] is None or _t.time() - _cobertura["at"] > 600:
        row = svc.db.one(
            "SELECT COUNT(DISTINCT comuna_code) AS n FROM risk_daily WHERE date = ?",
            (datetime.now(CHILE_TZ).date().isoformat(),))
        _cobertura["value"] = {"comunas_con_riesgo_hoy": row["n"] if row else 0}
        _cobertura["at"] = _t.time()
    return _cobertura["value"]


@router.get("/catalog")
def catalog(svc: Services = Depends(services)) -> dict[str, Any]:
    """Catálogo legible por máquina (DAT-08): cada capa con fuente, licencia, cadencia y campos."""
    return {
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "not_official": NOT_OFFICIAL,
        "cobertura": _cobertura_comunas(svc),
        "datasets": DATASETS,
    }


@router.get("")
def index() -> dict[str, Any]:
    """Índice de los conjuntos: qué hay, con qué parámetros y qué significa cada campo."""
    return {
        "name": "BRASA Chile · datos abiertos",
        "access": "solo lectura, sin registro ni clave",
        "not_official": NOT_OFFICIAL,
        "datasets": [
            {
                "id": "incidents",
                "url": "/api/opendata/incidents.geojson",
                "params": {
                    "hours": "1–336 (48 por defecto)",
                    "include_fixed": "true/false (fuentes fijas probables)",
                    "todo": "true/false (incluye también los puntos fuera de Chile)",
                },
                "geometry": "Point: centro de la evidencia del incidente",
                "fields": FIELDS["incidents"],
                "properties": [
                    "id",
                    "status",
                    "status_label",
                    "n_obs",
                    "n_reliable",
                    "sensors",
                    "fixed_source",
                    "max_frp",
                    "first_seen_at",
                    "last_seen_at",
                    "comuna",
                    "region",
                    "bbox",
                    "lightning_count",
                    "lightning_km",
                    "lightning_last_at",
                ],
                "source": "NASA FIRMS y NOAA GOES agrupados por BRASA",
            },
            {
                "id": "observations",
                "url": "/api/opendata/observations.geojson",
                "params": {
                    "hours": "1–72 (6 por defecto)",
                    "source": "filtro opcional por producto",
                    "todo": "true/false (incluye también los puntos fuera de Chile)",
                },
                "geometry": "Point: centro del píxel de la detección",
                "fields": FIELDS["observations"],
                "properties": ["id", "source", "sensor", "satellite", "confidence", "frp_mw", "observed_at", "comuna"],
                "source": "NASA FIRMS (VIIRS/MODIS) y NOAA GOES",
                "note": (
                    "Solo detecciones con comuna chilena: el satélite también ve puntos fuera del "
                    "territorio (países vecinos, mar y bordes) y esos no se publican, salvo con "
                    "todo=1. Con todo=1 cada punto trae `en_chile` y la colección `meta` explica "
                    "el recorte: el archivo crudo de la fuente sí los trae, se conservan por "
                    "transparencia pero no son incendios de Chile."
                ),
            },
            {
                "id": "risk",
                "url": "/api/opendata/risk.geojson",
                "params": {"day": "AAAA-MM-DD (hoy por defecto)"},
                "geometry": "Point: centroide de la comuna (el polígono está en el visor)",
                "fields": FIELDS["risk"],
                "properties": ["comuna_code", "comuna", "region", "level", "level_combined", "score", "fwi", "fwi_level"],
                "source": "Open-Meteo (pronóstico, centro de cada comuna) y BRASA",
            },
            {
                "id": "lightning",
                "url": "/api/opendata/lightning.geojson",
                "params": {"hours": "1–6 (1 por defecto)"},
                "geometry": "Point: centro óptico del destello detectado",
                "fields": FIELDS["lightning"],
                "properties": ["id", "observed_at", "age_s", "energy_j", "area_km2"],
                "source": "NOAA GOES-19 GLM (dominio público)",
            },
            {
                "id": "smoke",
                "url": "/api/opendata/smoke.geojson",
                "params": {"hours": "1–6 (1 por defecto)"},
                "geometry": "Polygon: mancha contigua de humo del barrido (10 min)",
                "fields": FIELDS["smoke"],
                "properties": ["observed_at", "age_min", "cells"],
                "source": "NOAA GOES-19 ABI-L2-ADPF (dominio público)",
            },
            {
                "id": "scars",
                "url": "/api/opendata/scars.geojson",
                "params": {"days": "1–180 (90 por defecto)"},
                "geometry": "Polygon o MultiPolygon: unión por comuna de las huellas de detecciones",
                "fields": FIELDS["scars"],
                "properties": ["comuna", "comuna_code", "region", "ha", "n_incidentes", "desde", "hasta"],
                "source": SCARS_SOURCE,
            },
            {
                "id": "response",
                "url": "/api/opendata/response.json",
                "params": {"season": "AAAA-AAAA (la más reciente en la tabla por defecto)"},
                "fields": FIELDS["response"],
                "properties": ["season", "overall", "comunas", "buckets", "count", "excluded"],
                "source": conaf.FIRES_SOURCE,
            },
            {
                "id": "boton-rojo",
                "url": "/api/opendata/boton-rojo.json",
                "params": {
                    "day": "AAAA-MM-DD (un solo día; todos los guardados por defecto)",
                    "days": "1–14 (14 por defecto: los días más recientes de la tabla)",
                },
                "geometry": "Point: centroide de la comuna (el polígono está en el visor)",
                "fields": FIELDS["boton-rojo"],
                "properties": ["comuna_code", "comuna", "region", "date", "hours", "area_ha", "proportion", "fetched_at"],
                "source": conaf.SOURCE,
            },
        ],
        "limits": {
            "max_features": MAX_FEATURES,
            "cached": "60 a 600 segundos por conjunto",
            "truncated": (
                "true cuando el conjunto tenía más de max_features elementos y se entregó "
                "recortado; pide una ventana más corta (hours menor) o filtra por source"
            ),
            "territorio": (
                "incidents y observations publican por defecto solo lo que cae en una comuna "
                "chilena: los satélites también ven Argentina, Bolivia y Perú, y esos puntos "
                "no son incendios de Chile. outside_chile cuenta las filas excluidas y todo=1 "
                "devuelve el conjunto completo"
            ),
            "response": "se calcula solo sobre la temporada pedida",
            "scars": (
                f"a lo sumo {SCARS_MAX_INCIDENTS} incidentes por ventana, los más recientes; "
                "si hubo más, incidents_note lo avisa en la respuesta. Incluye anomalías: "
                "la cicatriz es zona con calor, no superficie quemada con evidencia"
            ),
        },
        "license": (
            "Los datos de origen conservan su condición: CONAF y DMC son de sus organismos "
            "(la DMC los publica como dominio público); NASA y NOAA son de dominio público. "
            "El cálculo derivado de BRASA se puede reusar citando la fuente."
        ),
    }


@router.get("/incidents.geojson")
def incidents_geojson(
    hours: int = Query(48, ge=1, le=24 * 14),
    include_fixed: bool = Query(False, description="Incluir fuentes de calor fijas probables (volcanes, industria)"),
    todo: bool = Query(False, description="Incluir también los incidentes fuera del territorio chileno"),
    svc: Services = Depends(services),
):
    """Incidentes abiertos (agrupaciones de detecciones) de las últimas horas.

    FUEGO-12: solo sale lo que está en territorio chileno. Un incidente sin comuna
    (`comuna_code` nulo) no es un incendio de Chile y no se publica — sigue en la tabla,
    pero aquí no aparece — salvo que tenga `official_ref`: lo que informa CONAF no
    desaparece aunque su comuna no se haya podido emparejar. FUEGO-05: `todo=1` devuelve
    el conjunto completo y `outside_chile` cuenta las filas que el recorte deja fuera.
    """
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    states = ",".join("?" * len(OPEN_STATES))
    where = f"status IN ({states}) AND last_seen_at >= ?"
    params: list[Any] = [*OPEN_STATES, since]
    if not include_fixed:
        where += " AND fixed_source = 0"
    sql = f"SELECT * FROM incidents WHERE {where}"
    if not todo:
        sql += " AND (comuna_code IS NOT NULL OR official_ref IS NOT NULL)"
    rows = svc.db.query(sql + " ORDER BY last_seen_at DESC LIMIT ?", (*params, MAX_FEATURES + 1))
    outside = (
        0
        if todo
        else svc.db.one(
            f"SELECT COUNT(*) AS n FROM incidents WHERE {where} AND comuna_code IS NULL AND official_ref IS NULL",
            tuple(params),
        )["n"]
    )
    t = territory()
    features = []
    for row in rows:
        comuna = t.by_code.get(row["comuna_code"])
        features.append(
            {
                "type": "Feature",
                "geometry": _point(row["lon"], row["lat"]),
                "properties": {
                    "id": row["id"],
                    "status": row["status"],
                    "status_label": STATUS_LABELS.get(row["status"], row["status"]),
                    "n_obs": row["n_obs"],
                    "n_reliable": row["n_reliable"],
                    "sensors": [s.strip() for s in row["sensors"].split(",") if s.strip()],
                    "fixed_source": bool(row["fixed_source"]),
                    "max_frp": row["max_frp"],
                    "first_seen_at": row["first_seen_at"],
                    "last_seen_at": row["last_seen_at"],
                    "comuna": comuna.name if comuna else None,
                    "region": comuna.region if comuna else None,
                    "bbox": [row["min_lon"], row["min_lat"], row["max_lon"], row["max_lat"]],
                    "lightning_count": row["lightning_count"],
                    "lightning_km": row["lightning_km"],
                    "lightning_last_at": row["lightning_last_at"],
                },
            }
        )
    extra: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "hours": hours,
        "outside_chile": outside,
    }
    if outside:
        extra["note"] = f"{outside} incidentes fuera del territorio chileno quedaron fuera; usa todo=1 para verlos."
    return _response(
        _collection(features, "NASA FIRMS y NOAA GOES agrupados por BRASA", **extra),
        max_age=60,
    )


@router.get("/observations.geojson")
def observations_geojson(
    hours: int = Query(6, ge=1, le=72),
    source: str | None = Query(None, max_length=64, description="Producto, por ejemplo VIIRS_NOAA20_NRT"),
    todo: bool = Query(False, description="Incluir también las detecciones fuera del territorio chileno"),
    svc: Services = Depends(services),
):
    """Detecciones satelitales recientes. Un punto no es un incendio: es una señal de calor.

    FUEGO-05: por defecto solo sale lo que cae en una comuna chilena (`comuna_code` no
    nulo). El satélite también ve Argentina, Bolivia y Perú, y esas señales no son
    incendios de Chile; `todo=1` las incluye para quien necesite el conjunto completo y
    `outside_chile` cuenta cuántas quedaron fuera.
    """
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    # El conjunto es de Chile: el satélite también ve fuera de las comunas (países vecinos,
    # mar y bordes) y esas detecciones llegan sin comuna; solo `todo=1` las publica.
    where = "observed_at >= ?"
    params: list[Any] = [since]
    if source:
        where += " AND source = ?"
        params.append(source)
    sql = f"SELECT id, source, sensor, satellite, confidence, frp_mw, observed_at, lat, lon, comuna_code FROM observations WHERE {where}"
    if not todo:
        sql += " AND comuna_code IS NOT NULL"
    rows = svc.db.query(sql + " ORDER BY observed_at DESC LIMIT ?", (*params, MAX_FEATURES + 1))
    outside = 0 if todo else svc.db.one(f"SELECT COUNT(*) AS n FROM observations WHERE {where} AND comuna_code IS NULL", tuple(params))["n"]
    t = territory()
    features = []
    for row in rows:
        comuna = t.by_code.get(row["comuna_code"])
        features.append(
            {
                "type": "Feature",
                "geometry": _point(row["lon"], row["lat"]),
                "properties": {
                    "id": row["id"],
                    "source": row["source"],
                    "sensor": row["sensor"],
                    "satellite": row["satellite"],
                    "confidence": row["confidence"],
                    "frp_mw": row["frp_mw"],
                    "observed_at": row["observed_at"],
                    "comuna": comuna.name if comuna else None,
                    "en_chile": row["comuna_code"] is not None,
                },
            }
        )
    extra: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "hours": hours,
        "outside_chile": outside,
        "meta": {
            "recorte": "polígono comunal BCN con tolerancia costera",
            "fuera_de_chile": outside,
            "total": len(features) + outside,
            "explicacion": (
                "Las detecciones sin comuna (países vecinos, mar y bordes) quedan fuera por "
                "defecto; todo=1 las incluye con en_chile=false. El archivo crudo de la fuente "
                "sí las trae: se conservan por transparencia, pero no son incendios de Chile."
            ),
        },
    }
    if outside:
        extra["note"] = f"{outside} detecciones fuera del territorio chileno quedaron fuera; usa todo=1 para verlas."
    return _response(
        _collection(features, "NASA FIRMS (VIIRS/MODIS) y NOAA GOES", **extra),
        max_age=60,
    )


@router.get("/risk.geojson")
def risk_geojson(day: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"), svc: Services = Depends(services)):
    """Riesgo por comuna de un día: el 30-30-30 y su combinación con el FWI, en el centroide."""
    target = day or datetime.now(CHILE_TZ).date().isoformat()
    try:
        datetime.fromisoformat(target)
    except ValueError:
        raise HTTPException(422, "La fecha debe tener el formato AAAA-MM-DD.") from None
    rows = svc.db.query(
        "SELECT comuna_code, level, level_combined, score, fwi, fwi_level FROM risk_daily WHERE date = ? LIMIT ?",
        (target, MAX_FEATURES + 1),
    )
    t = territory()
    features = []
    for row in rows:
        comuna = t.by_code.get(row["comuna_code"])
        if not comuna:
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": _point(comuna.center[0], comuna.center[1]),
                "properties": {**dict(row), "comuna": comuna.name, "region": comuna.region},
            }
        )
    return _response(
        _collection(
            features,
            "Open-Meteo y BRASA",
            date=target,
            method=(
                "30-30-30 horario en el centroide; el nivel combinado añade el FWI "
                "del mismo día. Es peligro de propagación, no probabilidad de ignición."
            ),
        ),
        max_age=600,
    )


# Un archivo GLM pesa varios MB y una ventana puede juntar cientos: 5 minutos por ventana.
_LIGHTNING_CACHE_S = 300
_LIGHTNING_CACHE: dict[int, tuple[float, list[dict[str, Any]]]] = {}

# Los destellos se guardan en la tabla `lightning` de work.db al bajarlos (DET-03): sirven
# para marcar si hubo rayos cerca del inicio de un incidente. Retención corta —no es un
# archivo histórico— y la purga viaja en la misma escritura. Sin tráfico a la capa no se
# guarda nada: la marca de los incidentes queda en cero, nunca inventada.
LIGHTNING_KEEP_HOURS = 48


def _save_flashes(db, flashes: list[dict[str, Any]]) -> None:
    """Persiste el lote recién bajado y purga lo que ya cumplió la retención.

    Idempotente por `id`: dos ventanas que se solapan (p. ej. hours=1 y hours=6) no
    duplican. Un fallo de escritura no puede tumbar el conjunto público: se registra y
    el pedido sigue igual.
    """
    if not flashes:
        return
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=LIGHTNING_KEEP_HOURS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        with db.connect() as conn:
            conn.executemany(
                "INSERT OR IGNORE INTO lightning(id, observed_at, lat, lon, energy_j, source) VALUES (?,?,?,?,?,?)",
                [(f["id"], f["observed_at"], f["lat"], f["lon"], f.get("energy_j"), f["source"]) for f in flashes],
            )
            conn.execute("DELETE FROM lightning WHERE observed_at < ?", (cutoff,))
    except Exception:
        log.warning("No se pudieron guardar los destellos GLM en work.db.", exc_info=True)


@router.get("/lightning.geojson")
async def lightning_geojson(hours: int = Query(1, ge=1, le=6), svc: Services = Depends(services)):
    """Rayos (destellos) del GLM de GOES-19 sobre Chile de las últimas horas (máximo 6).

    Un destello no es un incendio: es luz de tormenta vista desde el satélite. Sobre pasto
    seco puede ser una ignición que todavía no tiene humo, por eso se publica igual.

    El tope de 6 horas por pedido (422 sobre eso) acota el costo: cada hora son ~180
    archivos LCFA de varios MB que se descargan de S3 en cada cache-miss.
    """
    cached = _LIGHTNING_CACHE.get(hours)
    flashes = cached[1] if cached and cached[0] > time.monotonic() else None
    if flashes is None:
        try:
            flashes = await glm.fetch_flashes(svc.client, hours)
        except Exception as exc:  # S3 caído o lento: el conjunto no está disponible, la API sí
            raise HTTPException(
                503, f"Los rayos GLM no están disponibles ahora ({type(exc).__name__}). Intenta de nuevo en unos minutos."
            ) from exc
        _LIGHTNING_CACHE[hours] = (time.monotonic() + _LIGHTNING_CACHE_S, flashes)
        _save_flashes(svc.db, flashes)  # el mismo lote alimenta la marca «rayos cerca del inicio»
    now = datetime.now(timezone.utc)
    features = []
    for flash in flashes[: MAX_FEATURES + 1]:
        observed = datetime.fromisoformat(flash["observed_at"].replace("Z", "+00:00"))
        features.append(
            {
                "type": "Feature",
                "geometry": _point(flash["lon"], flash["lat"]),
                "properties": {
                    "id": flash["id"],
                    "observed_at": flash["observed_at"],
                    "age_s": max(0, int((now - observed).total_seconds())),
                    "energy_j": flash.get("energy_j"),
                    "area_km2": flash.get("area_km2"),
                },
            }
        )
    return _response(
        _collection(features, "NOAA GOES-19 GLM (dominio público)", generated_at=now.strftime("%Y-%m-%dT%H:%M:%SZ"), hours=hours),
        max_age=60,
    )


# Un archivo ADPF pesa ~1 MB y una hora junta ~6: 5 minutos por ventana, como el GLM.
_SMOKE_CACHE_S = 300
_SMOKE_CACHE: dict[int, tuple[float, list[dict[str, Any]]]] = {}


@router.get("/smoke.geojson")
async def smoke_geojson(hours: int = Query(1, ge=1, le=6), svc: Services = Depends(services)):
    """Polígonos de humo que GOES-19 ve sobre Chile en las últimas horas.

    Humo de satélite no es incendio confirmado: es aerosol detectado por el ABI cada
    ~10 minutos, útil para ver hacia dónde se mueve la pluma.
    """
    cached = _SMOKE_CACHE.get(hours)
    polys = cached[1] if cached and cached[0] > time.monotonic() else None
    if polys is None:
        try:
            polys = smoke.polygons(await smoke.fetch_smoke(svc.client, hours))
        except Exception as exc:  # S3 caído o sin archivos recientes: el conjunto no está, la API sí
            raise HTTPException(
                503, f"El humo GOES-19 no está disponible ahora ({type(exc).__name__}). Intenta de nuevo en unos minutos."
            ) from exc
        _SMOKE_CACHE[hours] = (time.monotonic() + _SMOKE_CACHE_S, polys)
    now = datetime.now(timezone.utc)
    features = []
    for poly in polys[: MAX_FEATURES + 1]:
        observed = datetime.fromisoformat(poly["observed_at"].replace("Z", "+00:00"))
        features.append(
            {
                "type": "Feature",
                "geometry": poly["geometry"],
                "properties": {
                    "observed_at": poly["observed_at"],
                    "age_min": max(0, int((now - observed).total_seconds() // 60)),
                    "cells": poly["cells"],
                },
            }
        )
    return _response(
        _collection(features, "NOAA GOES-19 ABI-L2-ADPF (dominio público)", generated_at=now.strftime("%Y-%m-%dT%H:%M:%SZ"), hours=hours),
        max_age=60,
    )


@router.get("/boton-rojo.json")
def boton_rojo_json(
    day: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    days: int = Query(14, ge=1, le=14),
    svc: Services = Depends(services),
):
    """Pronóstico oficial Botón Rojo de CONAF: horas en condición por comuna y día.

    Un FeatureCollection de puntos (centroide de la comuna) servido como `application/json`
    para que se baje y abra como cualquier JSON. Con `day` devuelve un solo día; sin él, los
    `days` días más recientes presentes en la tabla (que guarda hasta 14). Botón Rojo marca
    condiciones favorables para que un incendio se inicie y propague: nunca un incendio
    detectado. Con la tabla vacía responde 200 igual, con `count: 0` y `features: []`.
    """
    sql = "SELECT comuna_code, date, hours, area_ha, proportion, fetched_at FROM boton_rojo "
    params: list[Any] = []
    if day:
        try:
            datetime.fromisoformat(day)
        except ValueError:
            raise HTTPException(422, "La fecha debe tener el formato AAAA-MM-DD.") from None
        sql += "WHERE date = ? ORDER BY comuna_code"
        params.append(day)
    else:
        sql += "WHERE date IN (SELECT DISTINCT date FROM boton_rojo ORDER BY date DESC LIMIT ?) ORDER BY date, comuna_code"
        params.append(days)
    rows = svc.db.query(sql + " LIMIT ?", (*params, MAX_FEATURES))
    t = territory()
    features = []
    for row in rows:
        comuna = t.by_code.get(row["comuna_code"])
        if not comuna:
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": _point(comuna.center[0], comuna.center[1]),
                "properties": {
                    "comuna_code": row["comuna_code"],
                    "comuna": comuna.name,
                    "region": comuna.region,
                    "date": row["date"],
                    "hours": row["hours"],
                    "area_ha": row["area_ha"],
                    "proportion": row["proportion"],
                    "fetched_at": row["fetched_at"],
                },
            }
        )
    extra: dict[str, Any] = {"date": day} if day else {"days": days}
    return _response(
        _collection(
            features,
            conaf.SOURCE,
            source_url=conaf.DASHBOARD_URL,
            **extra,
            generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            count=len(features),
            method=(
                "Horas al día en condición Botón Rojo por comuna, con la superficie "
                "que la cumple y su proporción de la comuna. Información propiedad "
                "de CONAF, republicada citándola."
            ),
        ),
        max_age=600,
        media_type="application/json",
    )


@router.get("/scars.geojson")
def scars_geojson(days: int = Query(90, ge=1, le=180), svc: Services = Depends(services)):
    """Cicatrices de la temporada: una geometría por comuna con la huella unida de sus incidentes.

    La huella es la unión de los píxeles calientes confiables de cada incidente (medio píxel
    de radio por sensor): marca dónde los satélites vieron calor, no el perímetro oficial.
    Incluye las anomalías —detecciones sueltas sin el umbral de «posible»— porque la cicatriz
    mide zona con calor, no superficie quemada con evidencia (SCARS-02). Es la base del riesgo
    de aluvión post-incendio del invierno (docs/ALUVIONES.md).
    """
    scars = season_scars(svc.db, days)
    extra: dict[str, Any] = {}
    if scars["incidents_truncated"]:
        extra["incidents_note"] = f"La ventana tenía más incidentes: se unieron solo los {scars['incidents_limit']} más recientes."
    return _response(
        _collection(
            scars["features"],
            SCARS_SOURCE,
            generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            days=days,
            method=(
                "Unión por comuna de las huellas de detecciones de cada incidente "
                "no descartado ni fijo: cada detección confiable aporta medio píxel "
                "de radio según su sensor. Incluye anomalías (detecciones sueltas sin "
                "el umbral de «posible»): mide zona donde se vio calor, no superficie "
                "quemada con evidencia. No es perímetro oficial ni área quemada medida "
                "(dNBR pendiente); GOES sobreestima la superficie."
            ),
            incidents_examined=scars["incidents_examined"],
            sin_comuna=scars["sin_comuna"],
            **extra,
        ),
        max_age=600,
    )


@router.get("/response.json")
def response_times(season: str | None = Query(None, pattern=r"^\d{4}-\d{4}$"), svc: Services = Depends(services)):
    """Radar de respuesta oficial: medianas de los tiempos entre detección, aviso y despacho de CONAF.

    No es GeoJSON (no hay geometría): es un resumen estadístico de la temporada pedida o de la más
    reciente presente en la tabla. Sin incendios con marcas publicadas responde 200 igual, con
    `count: 0` y una nota: la ausencia de datos también es información.
    """
    if season is None:
        latest = svc.db.one("SELECT MAX(season) AS s FROM official_fires WHERE season IS NOT NULL")
        season = latest["s"] if latest else None
    rows = (
        svc.db.query("SELECT detected_at, alerted_at, dispatched_at, comuna, area_ha FROM official_fires WHERE season = ?", (season,))
        if season
        else []
    )
    body = {
        "type": "response_times",
        "season": season,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": conaf.FIRES_SOURCE,
        "source_url": conaf.FIRES_PAGE_URL,
        "method": (
            "Medianas de las marcas que publica CONAF en su reporte de incendios: detección, "
            "aviso a los equipos y despacho de recursos. No es una medición propia de BRASA "
            "y no incluye la hora de arribo al incendio, porque el CSV no la trae."
        ),
        "count": len(rows),
        "limit": MAX_FEATURES,
        "truncated": len(rows) > MAX_FEATURES,
        **response_mod.aggregate(rows),
    }
    if not rows:
        body["note"] = "Todavía no hay suficientes incendios con horas publicadas."
    return Response(
        content=json.dumps(body, ensure_ascii=False, separators=(",", ":")),
        media_type="application/json",
        headers={"Cache-Control": "public, max-age=600"},
    )

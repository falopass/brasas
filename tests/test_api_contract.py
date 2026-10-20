"""Contrato de la API pública (QA-38): toda respuesta de datos declara su fuente y,
cuando habla de incidentes o de datos de origen oficial, avisa que BRASA no es una
fuente oficial —el texto menciona a SENAPRED o a CONAF—.

La lista es el contrato: un GET público nuevo que no esté en `DATA_GETS` ni en
`EXCLUDED` hace fallar `test_every_public_get_is_covered`, así que nadie puede
agregar un conjunto sin decidir cómo declara su fuente.
"""

from __future__ import annotations

import contextlib
import re
import time
from datetime import datetime, timezone

import pytest

# Claves que declaran la fuente del dato: `source`/`sources`/`fuentes`, `provider`
# (el proveedor de cada corrida de ingesta en /api/status), `sensors` (los sensores
# que vieron un incidente: es su fuente) y cualquier dict auxiliar `*_source`.
SOURCE_KEYS = {"source", "sources", "fuentes", "provider", "sensors"}
NOTICE_KEYS = {"not_official", "official", "explanation", "note", "method"}
OFFICIAL_RE = re.compile(r"SENAPRED|CONAF")
STAMP = "%Y-%m-%dT%H:%M:%SZ"

# GETs públicos cuya respuesta de datos debe declarar su fuente. Con parámetro se
# resuelven con PATH_ARGS; cada conjunto del índice de /api/opendata está incluido.
DATA_GETS = [
    "/api/observations",  # fuente por detección: points[].source
    "/api/incidents",  # fuente por incidente: incidents[].sensors
    "/api/incidents/{incident_id}",  # official_source + evidence[].source
    "/api/official-fires",  # source = reporte CONAF
    "/api/risk",  # *_source por insumo (CONAF, FWI, DMC, lluvia)
    "/api/risk/{code}",  # los mismos por comuna
    "/api/comuna/{code}",  # source por bloque: riesgo, Botón Rojo, censo, incendios
    "/api/panorama",  # source + boton_rojo_source: reporte público de CONAF
    "/api/status",  # runs[].provider: fuentes de ingesta
    "/api/opendata",  # índice: cada conjunto declara `source`
    "/api/opendata/incidents.geojson",
    "/api/opendata/observations.geojson",
    "/api/opendata/risk.geojson",
    "/api/opendata/lightning.geojson",
    "/api/opendata/smoke.geojson",
    "/api/opendata/response.json",  # source = reporte público de CONAF
    "/api/opendata/boton-rojo.json",
    "/api/climate/enso",  # source = NOAA (también en el fallback)
    "/api/climate/fwi/percentile/{code}",  # source = FWI de BRASA (Van Wagner)
]

# De esos, los que hablan de incidentes o de datos oficiales deben llevar además el
# aviso con mención a SENAPRED o CONAF (`not_official`, `official` o la nota de la
# fuente). /api/observations e /api/incidents (lista) no están: su explicación dice
# qué es el dato y el aviso completo vive en el detalle (`official`) y en GeoJSON.
NOTICE_GETS = [
    "/api/incidents/{incident_id}",  # official: «Sigue a SENAPRED y CONAF»
    "/api/official-fires",  # source.note: incendios informados por CONAF
    "/api/risk",  # boton_rojo_source.note: propiedad de CONAF
    "/api/risk/{code}",
    "/api/comuna/{code}",  # notas de fuente: sigue a SENAPRED y CONAF
    "/api/panorama",  # not_official: totales del reporte de CONAF
    "/api/opendata",
    "/api/opendata/incidents.geojson",
    "/api/opendata/observations.geojson",
    "/api/opendata/risk.geojson",
    "/api/opendata/lightning.geojson",
    "/api/opendata/smoke.geojson",
    "/api/opendata/response.json",  # método: marcas que publica CONAF
    "/api/opendata/boton-rojo.json",  # not_official + method: pronóstico de CONAF
]

PATH_ARGS = {"{incident_id}": "0123456789ab", "{code}": "5109"}

# GETs públicos que no sirven un conjunto de datos: quedan fuera con su razón, y la
# guarda de cobertura obliga a justificar cualquier endpoint nuevo de la misma manera.
EXCLUDED = {
    "/api/health": "sonda de vida, no un conjunto de datos",
    "/api/config": "banderas y claves públicas del cliente, no datos",
    "/api/locate": "geocodificador puntual, no publica un conjunto",
    "/api/priority-comunas": "archivo estático del repositorio (web/data)",
    "/api/weather": "sonda puntual a Open-Meteo; su fuente es fija y viaja en `source`",
    "/api/explore": "requiere clave FIRMS; su `sources` lo exige test_api.py",
    "/api/risk/{code}/trend": "comparador de pronósticos propios; sus fuentes son las de /api/risk",
    "/api/cases": "casos históricos: test_api.py ya exige fuente y URL por cifra",
    "/api/cases/{case_id}": "casos históricos: test_api.py ya exige fuente y URL por cifra",
    "/api/cases/{case_id}/polar": "casos históricos: test_api.py ya exige fuente y URL por cifra",
    "/api/cases/{case_id}/weather": "casos históricos: test_api.py ya exige fuente y URL por cifra",
    "/api/reports": "avisos ciudadanos moderados; su publicación la cubre test_api.py",
    "/api/incidents/{incident_id}/reports": "los mismos avisos moderados de /api/reports, filtrados por incidente",
    "/api/quality/feedback": "agregado de opiniones propias; la forma (total/counts/since, sin identificadores) la fija test_quality_feedback.py",
    "/api/reports/mine": "datos personales detrás de token",
    "/api/reports/{report_id}/photo": "foto de un aviso; el acceso lo cubre test_api.py",
    "/api/alerts": "datos personales detrás de token",
    "/api/me": "datos personales detrás de token",
    "/api/me/export": "datos personales detrás de token",
    "/api/places": "datos personales detrás de token",
    "/api/places/{place_id}/history": "datos personales detrás de token",
    "/api/places/{place_id}/summary": "datos personales detrás de token",
    "/api/shared/{token}": "vista compartida de un lugar; el aislamiento lo cubre test_api.py",
    "/api/nearby-services": "datos personales detrás de token",
    "/api/admin/reports": "cola de moderación interna",
}


def _values(node, keys: set[str], suffix: str = ""):
    """Valores no vacíos bajo claves de `keys` (o que terminan en `suffix`), a cualquier profundidad."""
    if isinstance(node, dict):
        for key, value in node.items():
            if value and (key in keys or (suffix and key.endswith(suffix))):
                yield value
            yield from _values(value, keys, suffix)
    elif isinstance(node, list):
        for item in node:
            yield from _values(item, keys, suffix)


def _texts(node) -> list[str]:
    return [v if isinstance(v, str) else str(v) for v in _values(node, NOTICE_KEYS)]


@contextlib.contextmanager
def seeded_client(make_client):
    """Cliente sin red con lo mínimo para que cada conjunto tenga algo que declarar."""
    from backend.routes import opendata

    # Los conjuntos GLM/humo bajan archivos de S3: se precargan sus cachés de módulo
    # con una lista vacía para ejercitar la respuesta real sin tocar la red.
    saved = (dict(opendata._LIGHTNING_CACHE), dict(opendata._SMOKE_CACHE))
    opendata._LIGHTNING_CACHE[1] = (time.monotonic() + 600, [])
    opendata._SMOKE_CACHE[1] = (time.monotonic() + 600, [])
    try:
        with make_client() as client:
            db = client.app.state.services.db
            moment = datetime.now(timezone.utc).strftime(STAMP)
            db.execute(
                "INSERT OR REPLACE INTO observations(id, source, sensor, satellite, resolution_m, lat, lon, "
                "observed_at, frp_mw, brightness_k, confidence, confidence_raw, comuna_code, run_id, ingested_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "obs-1",
                    "VIIRS_NOAA20_NRT",
                    "I4",
                    "NOAA-20",
                    375,
                    -33.05,
                    -71.55,
                    moment,
                    12.0,
                    340.0,
                    "nominal",
                    "n",
                    5109,
                    None,
                    moment,
                ),
            )
            db.execute(
                "INSERT OR REPLACE INTO incidents(id, status, status_changed_at, first_seen_at, last_seen_at, "
                "lat, lon, min_lat, max_lat, min_lon, max_lon, n_obs, n_reliable, sensors, max_frp, comuna_code, "
                "fixed_source, official_ref, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "0123456789ab",
                    "posible",
                    moment,
                    moment,
                    moment,
                    -33.05,
                    -71.55,
                    -33.06,
                    -33.04,
                    -71.56,
                    -71.54,
                    3,
                    2,
                    "GOES19, VIIRS",
                    42.5,
                    5109,
                    0,
                    None,
                    moment,
                ),
            )
            db.execute(
                "INSERT INTO ingest_runs(provider, product, started_at, finished_at, ok, n_records, n_new) VALUES (?,?,?,?,?,?,?)",
                ("NASA FIRMS", "VIIRS_NOAA20_NRT", moment, moment, 1, 1, 1),
            )
            db.execute(
                "INSERT INTO fwi_daily(comuna_code, date, ffmc, dmc, dc, isi, bui, fwi, level, computed_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (5109, moment[:10], 80.0, 20.0, 100.0, 3.0, 50.0, 12.5, "moderado", moment),
            )
            yield client
    finally:
        opendata._LIGHTNING_CACHE.clear()
        opendata._LIGHTNING_CACHE.update(saved[0])
        opendata._SMOKE_CACHE.clear()
        opendata._SMOKE_CACHE.update(saved[1])


def _resolve(path: str) -> str:
    for marker, value in PATH_ARGS.items():
        path = path.replace(marker, value)
    return path


@pytest.mark.parametrize("path", DATA_GETS)
def test_public_dataset_declares_its_source(make_client, path):
    with seeded_client(make_client) as client:
        response = client.get(_resolve(path))
    assert response.status_code == 200, f"{path}: {response.status_code} {response.text[:200]}"
    declarations = list(_values(response.json(), SOURCE_KEYS, suffix="_source"))
    assert declarations, f"{path} no declara su fuente (se busca {sorted(SOURCE_KEYS)} o *_source)"


@pytest.mark.parametrize("path", NOTICE_GETS)
def test_official_related_dataset_warns_not_official(make_client, path):
    with seeded_client(make_client) as client:
        body = client.get(_resolve(path)).json()
    texts = _texts(body)
    assert texts, f"{path} no trae aviso de no oficialidad ({sorted(NOTICE_KEYS)})"
    assert any(OFFICIAL_RE.search(text) for text in texts), f"{path}: el aviso debe mencionar a SENAPRED o a CONAF"


def test_every_public_get_is_covered(make_client):
    """Un GET público nuevo tiene que entrar en DATA_GETS o justificarse en EXCLUDED."""
    with make_client() as client:
        paths = {path for path, ops in client.app.openapi()["paths"].items() if path.startswith("/api") and "get" in ops}
    covered = set(DATA_GETS) | set(EXCLUDED)
    missing = paths - covered
    stale = covered - paths
    assert not missing, f"GET público sin contrato de fuente: {sorted(missing)}"
    assert not stale, f"Entradas del contrato sin endpoint: {sorted(stale)}"

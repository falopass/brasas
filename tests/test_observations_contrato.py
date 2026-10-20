"""QA-82: contrato público de /api/observations.

Fija la forma de cada punto, los límites de `hours`, los filtros `bbox` y
`reliable`, el aviso de recorte y el orden de salida. Todo con base temporal y
las fixtures de `tests/conftest.py`: sin red.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

import backend.routes.public as public

STAMP = "%Y-%m-%dT%H:%M:%SZ"

# DET-20: lo que ve un consumidor del mapa o de datos abiertos, ni una clave más.
CAMPOS_PUBLICOS = {
    "id",
    "source",
    "sensor",
    "satellite",
    "resolution_m",
    "lat",
    "lon",
    "observed_at",
    "frp_mw",
    "confidence",
    "comuna_code",
    "comuna",
    "region",
    "incident_id",
    "incident_status",
    "incident_n",
    "incident_fixed",
}
CAMPOS_INTERNOS = {"run_id", "ingested_at", "alerts_evaluated_at", "confidence_raw", "brightness_k"}


def _momento(**delta: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(**delta)).strftime(STAMP)


def _insertar(
    db,
    oid: str,
    *,
    observed_at: str | None = None,
    lat: float = -33.45,
    lon: float = -70.65,
    confidence: str | None = "alta",
    comuna_code: int | None = 13101,
) -> None:
    """Una detección con todas las columnas internas llenas: si alguna se filtra, se nota."""
    observed_at = observed_at or _momento(minutes=5)
    db.execute(
        "INSERT INTO observations(id, source, sensor, satellite, resolution_m, lat, lon, observed_at, frp_mw, "
        "brightness_k, confidence, confidence_raw, comuna_code, run_id, ingested_at, alerts_evaluated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            oid,
            "VIIRS_NOAA20_NRT",
            "I4",
            "NOAA-20",
            375,
            lat,
            lon,
            observed_at,
            12.0,
            340.0,
            confidence,
            "n",
            comuna_code,
            7,
            observed_at,
            observed_at,
        ),
    )


# 1. Campos exactos ------------------------------------------------------------


def test_cada_punto_trae_exactamente_los_campos_publicos(make_client):
    with make_client() as client:
        _insertar(client.app.state.services.db, "contrato-1")
        body = client.get("/api/observations").json()
    [punto] = body["points"]
    assert set(punto) == CAMPOS_PUBLICOS
    assert CAMPOS_INTERNOS.isdisjoint(punto)
    assert punto["comuna"] == "Santiago" and punto["region"] == "Metropolitana"


# 2. Límites de `hours` --------------------------------------------------------


@pytest.mark.parametrize("hours", [0, 24 * 14 + 1])
def test_hours_fuera_del_rango_es_422(make_client, hours):
    with make_client() as client:
        r = client.get("/api/observations", params={"hours": hours})
    assert r.status_code == 422


@pytest.mark.parametrize("hours", [1, 24 * 14])
def test_hours_en_los_bordes_es_200(make_client, hours):
    with make_client() as client:
        r = client.get("/api/observations", params={"hours": hours})
    assert r.status_code == 200
    assert r.json()["hours"] == hours


# 3. Filtro `bbox` -------------------------------------------------------------


def test_bbox_deja_solo_los_puntos_de_la_caja(make_client):
    with make_client() as client:
        db = client.app.state.services.db
        _insertar(db, "dentro", lat=-33.45, lon=-70.65)
        _insertar(db, "fuera", lat=-35.42, lon=-71.60)
        body = client.get("/api/observations", params={"bbox": "-71,-34,-70,-33"}).json()
    assert [p["id"] for p in body["points"]] == ["dentro"]
    assert body["count"] == 1


@pytest.mark.parametrize("bbox", ["-71,-34,-70", "oeste,sur,este,norte"])
def test_bbox_mal_formado_es_422_con_el_mensaje_del_codigo(make_client, bbox):
    with make_client() as client:
        r = client.get("/api/observations", params={"bbox": bbox})
    assert r.status_code == 422
    assert r.json()["detail"] == "bbox debe ser west,south,east,north"


# 4. Filtro `reliable` ---------------------------------------------------------


def test_reliable_deja_solo_alta_nominal_y_media(make_client):
    with make_client() as client:
        db = client.app.state.services.db
        for i, confidence in enumerate(["alta", "nominal", "media", "baja", "low", None]):
            _insertar(db, f"conf-{i}", confidence=confidence)
        todos = client.get("/api/observations").json()
        confiables = client.get("/api/observations", params={"reliable": "true"}).json()
    assert todos["count"] == 6
    assert {p["id"] for p in confiables["points"]} == {"conf-0", "conf-1", "conf-2"}
    assert {p["confidence"] for p in confiables["points"]} == {"alta", "nominal", "media"}


# 5. Recorte -------------------------------------------------------------------
# El tope real son 20 000 filas; se baja con monkeypatch para probar el borde
# (LIMIT + 1) sin sembrar 20 001 filas.


def test_mas_filas_que_el_limite_avisa_recorte(make_client, monkeypatch):
    monkeypatch.setattr(public, "OBSERVATIONS_LIMIT", 3)
    with make_client() as client:
        db = client.app.state.services.db
        for i in range(4):
            _insertar(db, f"recorte-{i}", observed_at=_momento(minutes=i + 1))
        body = client.get("/api/observations").json()
    assert body["truncated"] is True
    assert body["limit"] == 3
    assert body["count"] == len(body["points"]) == 3


@pytest.mark.parametrize("filas", [2, 3])
def test_sin_pasarse_del_limite_no_avisa_recorte(make_client, monkeypatch, filas):
    monkeypatch.setattr(public, "OBSERVATIONS_LIMIT", 3)
    with make_client() as client:
        db = client.app.state.services.db
        for i in range(filas):
            _insertar(db, f"sin-recorte-{i}", observed_at=_momento(minutes=i + 1))
        body = client.get("/api/observations").json()
    assert body["truncated"] is False
    assert body["count"] == len(body["points"]) == filas


# 6. Orden ---------------------------------------------------------------------


def test_los_puntos_vienen_de_mas_nuevo_a_mas_viejo(make_client):
    with make_client() as client:
        db = client.app.state.services.db
        _insertar(db, "viejo", observed_at=_momento(hours=2))
        _insertar(db, "nuevo", observed_at=_momento(minutes=1))
        _insertar(db, "medio", observed_at=_momento(hours=1))
        body = client.get("/api/observations").json()
    marcas = [p["observed_at"] for p in body["points"]]
    assert marcas == sorted(marcas, reverse=True)
    assert [p["id"] for p in body["points"]] == ["nuevo", "medio", "viejo"]

"""`/api/diagnostico` (AUTO-10 + AUTO-01 + AUTO-14): el producto reporta sus propias fallas.

Fija el contrato: la agregación por ruta plantillada con n/5xx/p50/p95/lentas, los `problemas`
en palabras simples con su `arreglo`, el `advice` como frase de reglas y el veredicto por fuente
que ya calcula `diagnostics` (GOES, FIRMS con cupo, CONAF, Open-Meteo y respaldo). La guarda de
privacidad revisa el payload completo: nunca query string ni el token del dispositivo.
"""

from __future__ import annotations

import json
import time
from datetime import timedelta

import pytest

from backend import diagnostics
from backend.routes import observability
from backend.routes.diagnostico import rutas
from backend.services import stamp, utcnow

TOKEN_VECINO = "token-secreto-de-vecino-0123456789"


@pytest.fixture(autouse=True)
def _ventana_limpia():
    observability.SAMPLES.clear()
    yield
    observability.SAMPLES.clear()


def _rows(body: dict) -> dict[str, dict]:
    return {row["path"]: row for row in body["routes"]}


def seed_run(db, provider: str, product: str, hours_ago: float, ok: bool) -> str:
    started = stamp(utcnow() - timedelta(hours=hours_ago))
    db.execute(
        "INSERT INTO ingest_runs(provider, product, started_at, finished_at, ok, n_records, n_new) VALUES (?,?,?,?,?,?,?)",
        (provider, product, started, started, int(ok), 0, 0),
    )
    return started


def test_agregacion_pura_cuenta_5xx_lentas_y_percentiles() -> None:
    observability.record("/api/x", 200, 10.0)
    observability.record("/api/x", 200, 20.0)
    observability.record("/api/x", 500, 30.0)
    observability.record("/api/x", 200, 2500.0)
    rows = {row["path"]: row for row in rutas()}
    assert rows["/api/x"]["n"] == 4
    assert rows["/api/x"]["p50_ms"] == 20
    assert rows["/api/x"]["p95_ms"] == 2500
    assert rows["/api/x"]["errors_5xx"] == 1
    assert rows["/api/x"]["lentas"] == 1
    assert rows["/api/x"]["ultimo_codigo"] == 500
    assert rows["/api/x"]["ultimo_error_at"]


def test_endpoint_publica_la_ruta_con_sus_claves(make_client) -> None:
    with make_client() as client:
        for _ in range(3):
            assert client.get("/api/incidents").status_code == 200
        body = client.get("/api/diagnostico").json()
    row = _rows(body)["/api/incidents"]
    assert row["n"] >= 3
    for key in ("n", "errors_5xx", "p50_ms", "p95_ms", "lentas", "ultimo_error_at", "ultimo_codigo"):
        assert key in row, f"falta {key} en la fila de ruta"
    assert body["window_min"] == 15
    assert isinstance(body["problemas"], list) and isinstance(body["advice"], str) and body["advice"]
    assert {f["nombre"] for f in body["fuentes"]} == {"GOES", "FIRMS", "CONAF", "Open-Meteo", "Respaldo"}


def test_diagnostico_no_se_cuenta_a_si_mismo(make_client) -> None:
    with make_client() as client:
        client.get("/api/diagnostico")
        body = client.get("/api/diagnostico").json()
    assert "/api/diagnostico" not in _rows(body), "la ruta de diagnóstico apareció en su propia tabla"


def test_payload_sin_query_string_ni_token(make_client) -> None:
    with make_client() as client:
        client.get(
            "/api/observations",
            params={"bbox": "-71.5,-34.5,-70.5,-33.5", "clave_vecino": "vecino-123"},
            headers={"X-Brasa-Token": TOKEN_VECINO},
        )
        body = client.get("/api/diagnostico")
    texto = json.dumps(body.json())
    # Ni la URL real (parámetros y sus valores), ni el token del dispositivo: solo plantillas.
    for filtrado in (TOKEN_VECINO, "bbox", "clave_vecino", "vecino-123", "?", "token"):
        assert filtrado not in texto, f"el payload expone {filtrado!r}"


def test_un_500_sale_en_problemas_y_en_advice(make_client) -> None:
    observability.record("/api/incidents/{incident_id}", 500, 40.0)
    with make_client() as client:
        body = client.get("/api/diagnostico").json()
    row = _rows(body)["/api/incidents/{incident_id}"]
    assert row["errors_5xx"] == 1 and row["ultimo_codigo"] == 500
    assert any(p["clave"] == "errores_5xx" and "/api/incidents/{incident_id}" in p["texto"] for p in body["problemas"])
    assert "errores" in body["advice"]


def test_veredicto_por_fuente_cuatro_casos(make_client) -> None:
    """AUTO-14: bien, tarde (última buena hace más de su ventana), fallando (3 seguidas), sin_dato."""
    with make_client() as client:
        db = client.app.state.services.db
        seed_run(db, "NOAA GOES", "GOES19_FDCF", 0.1, True)      # bien
        seed_run(db, "NASA FIRMS", "VIIRS_NOAA20_NRT", 5.0, True)  # tarde (> 3 h)
        for h in (0.5, 0.4, 0.3):
            seed_run(db, "CONAF · reporte público de incendios (GEPRIF)", "CONAF_INCENDIOS", h, False)
        # Open-Meteo queda sin corridas: sin_dato.
        veredictos = {f["nombre"]: f for f in diagnostics.veredicto_fuentes(db, backup={"enabled": False})}
    assert veredictos["GOES"]["estado"] == "bien"
    assert veredictos["FIRMS"]["estado"] == "tarde"
    assert "firms_quota" in veredictos["FIRMS"]["que_hacer"]
    assert veredictos["CONAF"]["estado"] == "fallando"
    assert veredictos["CONAF"]["fallos_seguidos"] == 3
    assert veredictos["Open-Meteo"]["estado"] == "sin_dato"
    assert veredictos["Respaldo"]["estado"] == "sin_dato"
    for f in veredictos.values():
        bajo = json.dumps(f).lower()
        assert "token" not in bajo.replace("x-admin-token", "") and "bearer" not in bajo


def test_cupo_firms_casi_agotado_marca_tarde(make_client) -> None:
    with make_client() as client:
        db = client.app.state.services.db
        seed_run(db, "NASA FIRMS", "VIIRS_NOAA20_NRT", 0.2, True)
        db.kv_set("firms_quota", json.dumps({"limit": 5000, "used": 4700, "checked_at": stamp()}))
        veredictos = {f["nombre"]: f for f in diagnostics.veredicto_fuentes(db, backup={"enabled": True, "at": stamp()})}
    assert veredictos["FIRMS"]["estado"] == "tarde"
    assert "4700" in veredictos["FIRMS"]["detalle"]
    assert veredictos["Respaldo"]["estado"] == "bien"


def test_ventana_expira_muestras_viejas() -> None:
    observability.SAMPLES.append((time.monotonic() - 20 * 60, "/api/vieja", 200, 5.0))
    observability.record("/api/nueva", 200, 5.0)
    rows = {row["path"] for row in rutas()}
    assert "/api/vieja" not in rows and "/api/nueva" in rows

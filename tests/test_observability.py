"""Observabilidad de las rutas públicas: cuántas veces se pidió cada una, cuánto tardó y qué devolvió.

Fija el contrato de `GET /api/observability/routes`: la ruta plantillada (nunca la URL con el id),
los milisegundos como enteros, la ventana de 60 minutos en UTC y el orden por p95 descendente.
La guarda de privacidad revisa lo que el middleware guardó de verdad, no solo la respuesta: si
guardara la URL cruda, la IP, el query string o el user-agent, la prueba falla.
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime

import pytest

from backend.routes import observability

ISO_UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")


@pytest.fixture(autouse=True)
def _ventana_limpia():
    observability.SAMPLES.clear()
    yield
    observability.SAMPLES.clear()


def _rows(body: dict) -> dict[str, dict]:
    return {row["path"]: row for row in body["routes"]}


def test_cuenta_ruta_plantillada_codigo_y_tiempo(make_client) -> None:
    with make_client() as client:
        for _ in range(3):
            assert client.get("/api/health").status_code == 200
        assert client.get("/api/incidents/no-existe").status_code == 404
        response = client.get("/api/observability/routes")
    assert response.status_code == 200
    body = response.json()
    rows = _rows(body)
    assert rows["/api/health"]["n"] == 3
    assert rows["/api/health"]["errors_4xx"] == 0
    assert rows["/api/health"]["errors_5xx"] == 0
    # La ruta real de la ficha es /api/incidents/{incident_id}; lo que importa es que sea la
    # plantilla y no la URL con el id.
    assert rows["/api/incidents/{incident_id}"]["n"] == 1
    assert rows["/api/incidents/{incident_id}"]["errors_4xx"] == 1
    assert "no-existe" not in json.dumps(body)


def test_respuesta_declara_ventana_y_proceso(make_client) -> None:
    with make_client() as client:
        body = client.get("/api/observability/routes").json()
    assert body["window_min"] == 60
    assert ISO_UTC.fullmatch(body["desde"]), f"desde no es ISO UTC: {body['desde']!r}"
    assert datetime.fromisoformat(body["desde"].replace("Z", "+00:00")).utcoffset().total_seconds() == 0
    aviso = body["aviso"].lower()
    assert "proceso" in aviso and "contenedor" in aviso, "la respuesta debe advertir que es por proceso"
    assert isinstance(body["routes"], list)


def test_la_ventana_expira_los_datos_viejos(make_client) -> None:
    observability.SAMPLES.append((time.monotonic() - 61 * 60, "/api/vieja", 200, 5.0))
    observability.record("/api/nueva", 200, 5.0)
    with make_client() as client:
        rows = _rows(client.get("/api/observability/routes").json())
    assert "/api/vieja" not in rows, "una muestra de hace 61 minutos quedó dentro de la ventana de 60"
    assert rows["/api/nueva"]["n"] == 1


def test_milisegundos_enteros_y_orden_por_p95(make_client) -> None:
    observability.record("/api/lenta", 500, 900.0)
    for ms in (10.0, 20.0, 30.0):
        observability.record("/api/lenta", 200, ms)
    observability.record("/api/rapida", 200, 4.0)
    with make_client() as client:
        body = client.get("/api/observability/routes").json()
    rows = _rows(body)
    lenta = rows["/api/lenta"]
    assert (lenta["n"], lenta["p50_ms"], lenta["p95_ms"], lenta["max_ms"]) == (4, 20, 900, 900)
    assert lenta["errors_5xx"] == 1 and lenta["errors_4xx"] == 0
    for row in body["routes"]:
        for key in ("n", "p50_ms", "p95_ms", "max_ms", "errors_4xx", "errors_5xx"):
            assert isinstance(row[key], int), f"{row['path']}.{key} debe ser un entero"
    p95s = [row["p95_ms"] for row in body["routes"]]
    assert p95s == sorted(p95s, reverse=True), f"las rutas deben ordenarse por p95 descendente: {p95s}"


def test_no_guarda_url_ip_query_ni_user_agent(make_client) -> None:
    with make_client() as client:
        client.get(
            "/api/observations",
            params={"bbox": "-71.5,-34.5,-70.5,-33.5", "secreto": "vecino-123"},
            headers={"X-Brasa-Token": "token-de-vecino-1234567890", "User-Agent": "navegador-de-vecino"},
        )
        client.get("/api/incidents/no-existe")
        client.get("/api/nada-de-nada")
        guardado = json.dumps([[path, code, ms] for _, path, code, ms in observability.SAMPLES])
    for filtrado in (
        "no-existe",
        "nada-de-nada",
        "bbox",
        "secreto",
        "vecino-123",
        "token-de-vecino",
        "navegador-de-vecino",
        "testclient",
        "?",
    ):
        assert filtrado not in guardado, f"el middleware guardó {filtrado!r}, que es un dato de la persona o de la URL"
    assert "/api/sin-ruta" in guardado, "una ruta inexistente se agrupa en /api/sin-ruta, no se descarta en silencio"

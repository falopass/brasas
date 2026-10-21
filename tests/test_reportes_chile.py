"""FUEGO-06: un reporte ciudadano de fuera de Chile no entra a la cola ni se publica.

La caja del formulario (lat -60..-17, lon -110..-66) incluye Mendoza, Bolivia y Perú:
la frontera real la decide `territory()`. Y los reportes ya guardados con comuna nula
tampoco pueden salir al mapa si alguno quedó verificado por descuido.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.routes.common import limiter

STAMP = "%Y-%m-%dT%H:%M:%SZ"
MENDOZA = {"lat": "-32.89", "lon": "-68.83", "kind": "humo", "description": "Humo al oriente"}
TALCA = {"lat": "-35.43", "lon": "-71.66", "kind": "humo", "description": "Columna de humo"}


@pytest.fixture(autouse=True)
def fresh_limits():
    """El limitador es por proceso: sin esto, un test agota el cupo de reportes de los demás."""
    limiter.hits.clear()
    yield
    limiter.hits.clear()


def test_a_report_outside_chile_is_rejected_before_touching_the_db(make_client):
    """Mendoza pasa la caja del Form pero no `territory()`: 422 y la tabla sigue vacía."""
    with make_client() as client:
        response = client.post("/api/reports", data=MENDOZA)
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert detail["code"] == "FUERA_DE_CHILE" and "fuera de Chile" in detail["message"]
        assert client.app.state.services.db.one("SELECT COUNT(*) AS n FROM reports")["n"] == 0


def test_a_report_in_talca_enters_the_queue_with_its_comuna(make_client):
    """El punto válido no se rompió: entra a la cola con su comuna resuelta."""
    with make_client() as client:
        response = client.post("/api/reports", data=TALCA)
        assert response.status_code == 201, response.text
        row = client.app.state.services.db.one("SELECT comuna_code FROM reports WHERE id = ?", (response.json()["id"],))
        assert row["comuna_code"] is not None


def _seed_verified(db, ident: str, comuna: int | None) -> None:
    db.execute(
        "INSERT INTO reports(id, created_at, lat, lon, comuna_code, kind, description, status) VALUES (?,?,?,?,?,?,?,?)",
        (ident, datetime.now(timezone.utc).strftime(STAMP), -32.89, -68.83, comuna, "humo", "Sembrado a mano", "verificado"),
    )


def test_a_verified_report_without_comuna_never_publishes(make_client):
    """Un verificado con comuna nula (anterior al rechazo) no aparece en /api/reports."""
    with make_client() as client:
        _seed_verified(client.app.state.services.db, "fuera-1", None)
        assert client.get("/api/reports").json()["reports"] == []


def test_a_verified_report_with_comuna_still_publishes(make_client):
    """La misma fila con comuna aparece normal: el recorte no esconde avisos chilenos."""
    with make_client() as client:
        _seed_verified(client.app.state.services.db, "dentro-1", 5109)
        reports = client.get("/api/reports").json()["reports"]
        assert [r["id"] for r in reports] == ["dentro-1"] and reports[0]["comuna"] == "Viña del Mar"

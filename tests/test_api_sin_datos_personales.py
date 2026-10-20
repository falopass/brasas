"""Guardas de privacidad de la API pública (Ley 21.719): ninguna respuesta pública lleva
datos de personas y la ubicación de un reporte vecinal sale redondeada (~100 m).

El contrato está implementado a mano en `backend/routes/community.py` (`_public`), endpoint
por endpoint. Esta suite lo convierte en algo verificable: recorre las respuestas públicas,
falla ante una clave que nombre un dato de persona y exige tres decimales en las
coordenadas de los reportes.
"""

from __future__ import annotations

import re

import pytest

LAT, LON = -33.0512345, -71.5512345
ADMIN_TOKEN = "admin-secret-token-999"

# Palabras que nombran a una persona o a su dispositivo. Se comparan contra cada trozo del
# nombre de la clave (`subscriber_id` → subscriber, id), no contra la cadena completa:
# `description` contiene «ip» y es un campo público legítimo.
FORBIDDEN = ("subscriber", "device", "token", "secret", "email", "phone", "telefono", "author", "ip", "session")

# Respuestas públicas que no pueden nombrar a nadie. `/api/reports/near` no existe en este
# router (la lista cercana es `/api/incidents/{id}/reports`, que sale de la misma `_public()`);
# el caso queda listo para cuando se agregue. El conjunto de incidentes es `.geojson`.
PUBLIC_GETS = [
    ("/api/reports", None),
    ("/api/reports/near", {"lat": LAT, "lon": LON}),
    ("/api/status", None),
    ("/api/risk", None),
    ("/api/opendata/incidents.geojson", None),
]


def _forbidden_keys(node, path: str = "$") -> list[str]:
    """Rutas de las claves que nombran datos de personas, a cualquier profundidad."""
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            parts = re.split(r"[^a-z0-9]+", str(key).lower())
            if any(part.startswith(term) for part in parts for term in FORBIDDEN):
                found.append(f"{path}.{key}")
            found.extend(_forbidden_keys(value, f"{path}.{key}"))
    elif isinstance(node, list):
        for index, item in enumerate(node):
            found.extend(_forbidden_keys(item, f"{path}[{index}]"))
    return found


def _with_coords(node):
    """Diccionarios con `lat` y `lon`, a cualquier profundidad."""
    if isinstance(node, dict):
        if "lat" in node and "lon" in node:
            yield node
        for value in node.values():
            yield from _with_coords(value)
    elif isinstance(node, list):
        for item in node:
            yield from _with_coords(item)


def _verified_report(client) -> str:
    """Un reporte real, con dueño (`subscriber_id`), que ya pasó moderación."""
    token = client.post("/api/subscribers").json()["token"]
    created = client.post(
        "/api/reports",
        data={"lat": str(LAT), "lon": str(LON), "kind": "humo", "description": "Columna de humo"},
        headers={"X-Brasa-Token": token},
    )
    assert created.status_code == 201, created.text
    report_id = created.json()["id"]
    decided = client.post(
        f"/api/admin/reports/{report_id}",
        json={"status": "verificado"},
        headers={"X-Admin-Token": ADMIN_TOKEN},
    )
    assert decided.status_code == 200, decided.text
    stored = client.app.state.services.db.one("SELECT subscriber_id FROM reports WHERE id = ?", (report_id,))
    assert stored["subscriber_id"] == token
    return report_id


def test_el_recorrido_detecta_datos_personales():
    """Caso negativo: si el detector no mira, esta prueba falla."""
    sucio = {"reports": [{"id": "r1", "lat": LAT, "lon": LON, "subscriber_id": "abc"}]}
    assert _forbidden_keys(sucio) == ["$.reports[0].subscriber_id"]
    assert _forbidden_keys({"description": "Columna de humo"}) == []


@pytest.mark.parametrize("path,params", PUBLIC_GETS)
def test_las_respuestas_publicas_no_llevan_datos_personales(make_client, path, params):
    with make_client(ADMIN_TOKEN=ADMIN_TOKEN) as client:
        if path not in client.app.openapi()["paths"]:
            pytest.skip(f"{path} no existe en este router")
        _verified_report(client)
        response = client.get(path, params=params)
        assert response.status_code == 200, f"{path}: {response.status_code} {response.text[:200]}"
        leaks = _forbidden_keys(response.json())
        assert not leaks, f"{path} publica datos de personas: {leaks}"


@pytest.mark.parametrize(
    "path,params",
    [
        ("/api/reports", None),
        ("/api/reports/near", {"lat": LAT, "lon": LON}),
    ],
)
def test_las_coordenadas_de_reportes_van_redondeadas(make_client, path, params):
    with make_client(ADMIN_TOKEN=ADMIN_TOKEN) as client:
        if path not in client.app.openapi()["paths"]:
            pytest.skip(f"{path} no existe en este router")
        _verified_report(client)
        body = client.get(path, params=params).json()
        items = list(_with_coords(body))
        assert items, f"{path} no devolvió ningún reporte con lat/lon"
        for item in items:
            for axis, seeded in (("lat", LAT), ("lon", LON)):
                value = item[axis]
                assert len(str(value).split(".")[-1]) <= 3, f"{path}: {axis}={value} tiene más de 3 decimales"
                assert value == round(seeded, 3), f"{path}: {axis}={value} no es el redondeo de {seeded}"
                assert value != seeded, f"{path}: {axis}={value} publica la coordenada exacta"

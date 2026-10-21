"""DEBT-10: lo que no depende del lugar se consulta una vez por pasada de «Mi zona».

La vista pide `/api/places/{id}/summary` por cada lugar guardado, en paralelo. Las consultas
de incendios CONAF recientes (`FROM official_fires`) y de avisos DMC (`FROM dmc_alerts`) son
iguales para todos los lugares: con la marca compartida de 10 s se hacen una vez, no N veces,
y el payload de cada lugar conserva sus claves y el orden de `official` por distancia.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import httpx

from backend.db import Database
from tests.conftest import json_response

PUNTOS = [(-33.02, -71.55), (-33.025, -71.555), (-33.015, -71.545)]


def _open_meteo(web) -> None:
    """`current` (el viento) responde; `hourly` cae → risk_point queda null (caché negativa)."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("hourly"):
            return httpx.Response(503, text="sin pronóstico")
        return json_response(
            {"current": {"wind_speed_10m": 12.0, "wind_direction_10m": 200.0, "time": "2027-01-15T15:00"}, "current_units": {}}
        )

    web.add(lambda r: "open-meteo" in r.url.host, handler)


def _contador(monkeypatch) -> dict[str, int]:
    cuenta = {"official_fires": 0, "dmc_alerts": 0}
    original = Database.query

    def contada(self, sql, params=()):
        for tabla in cuenta:
            if f"FROM {tabla}" in sql:
                cuenta[tabla] += 1
        return original(self, sql, params)

    monkeypatch.setattr(Database, "query", contada)
    return cuenta


def _setup(client, puntos):
    """Un dispositivo con un lugar por cada (lat, lon); devuelve (headers, [place_id])."""
    token = client.post("/api/subscribers").json()["token"]
    headers = {"X-Brasa-Token": token}
    ids = [
        client.post("/api/places", json={"name": f"Lugar {i}", "lat": lat, "lon": lon, "radius_km": 10}, headers=headers).json()["id"]
        for i, (lat, lon) in enumerate(puntos)
    ]
    return headers, ids


def _comuna(db, place_id: str) -> int:
    return db.one("SELECT comuna_code FROM places WHERE id = ?", (place_id,))["comuna_code"]


def _incendio(db, fid: str, lat: float, lon: float) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    db.execute(
        "INSERT INTO official_fires(id, name, status, status_raw, started_at, lat, lon, first_fetched_at, fetched_at) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (fid, f"Incendio {fid}", "confirmado", "En combate", now, lat, lon, now, now),
    )


def _aviso_dmc(db, comunas: list[int]) -> None:
    """Una fila de `dmc_alerts` vigente, como la deja `ingest_dmc` (misma forma que test_alert_dmc)."""
    now = datetime.now(timezone.utc)
    db.execute(
        "INSERT INTO dmc_alerts(id, kind, event, headline, severity, urgency, onset, expires, web, areas, comunas, fetched_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "urn:oid:test:deb10",
            "viento",
            "Viento Normal a Moderado",
            "Viento Normal a Moderado en litoral de la región de Valparaíso",
            "Moderate",
            "Expected",
            (now - timedelta(hours=1)).isoformat(),
            (now + timedelta(hours=6)).isoformat(),
            "https://archivos.meteochile.gob.cl/portaldmc/AAA/doc/evento.html",
            "[]",
            json.dumps(comunas),
            now.isoformat(),
        ),
    )


def test_las_consultas_compartidas_se_hacen_una_vez_por_pasada(make_client, web, monkeypatch):
    """Tres lugares de la misma comuna, tres resúmenes: una consulta por tabla, no tres."""
    _open_meteo(web)
    cuenta = _contador(monkeypatch)
    with make_client(GOES_ENABLED="0") as client:
        headers, ids = _setup(client, PUNTOS)
        db = client.app.state.services.db
        _aviso_dmc(db, [_comuna(db, ids[0])])
        _incendio(db, "F-1", PUNTOS[0][0], PUNTOS[0][1])
        for pid in ids:
            res = client.get(f"/api/places/{pid}/summary", headers=headers)
            assert res.status_code == 200
    assert cuenta == {"official_fires": 1, "dmc_alerts": 1}


def test_el_resumen_conserva_sus_claves_y_el_orden_de_official(make_client, web):
    _open_meteo(web)
    with make_client(GOES_ENABLED="0") as client:
        headers, ids = _setup(client, PUNTOS)
        db = client.app.state.services.db
        _aviso_dmc(db, [_comuna(db, ids[0])])
        # Dos incendios a distancias distintas: `official` sale de más cerca a más lejos.
        _incendio(db, "F-cerca", PUNTOS[0][0] + 0.02, PUNTOS[0][1] + 0.02)
        _incendio(db, "F-lejos", PUNTOS[0][0] + 0.10, PUNTOS[0][1] + 0.10)
        cuerpos = [client.get(f"/api/places/{pid}/summary", headers=headers).json() for pid in ids]
    claves = {
        "place",
        "comuna",
        "status",
        "cause",
        "wind",
        "official",
        "official_source",
        "dmc_alerts",
        "dmc_source",
        "nearby",
        "risk_days",
        "risk_point",
        "data_as_of",
    }
    for body in cuerpos:
        assert set(body) == claves
        assert [f["id"] for f in body["official"]] == ["F-cerca", "F-lejos"]
        assert [f["distance_km"] for f in body["official"]] == sorted(f["distance_km"] for f in body["official"])
        assert body["dmc_alerts"] and body["dmc_alerts"][0]["kind"] == "viento"

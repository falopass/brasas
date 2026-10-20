"""UX-47: el enlace familiar dice si al lugar le llegó un aviso en las últimas 48 h.

`last_alert` resume el aviso más reciente (nivel, tipo, cuándo se creó, si se entregó y su
título) para que la familia sepa si «se enteró». Sigue la regla de `SHARE_FIELDS`: sin ids,
sin token, sin datos del suscriptor: el payload solo cede su título.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from tests.test_api import register

STAMP = "%Y-%m-%dT%H:%M:%SZ"


def _alert(svc, place_id: str, obs: str, level: str, kind: str | None, hours_ago: float, delivered_at: str | None = None) -> None:
    moment = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).strftime(STAMP)
    payload = {"title": f"Aviso {obs}", "place": {"id": place_id, "name": "Casa"}, "distance_km": 3.2}
    if kind:
        payload["kind"] = kind
    svc.db.execute(
        "INSERT INTO alerts(place_id, observation_id, level, distance_km, bearing_deg, upwind, lat, lon, "
        "observed_at, created_at, payload, delivered, delivered_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            place_id,
            obs,
            level,
            3.2,
            90,
            0,
            -33.06,
            -71.54,
            moment,
            moment,
            json.dumps(payload),
            json.dumps(["push"] if delivered_at else []),
            delivered_at,
        ),
    )


def _shared(client, owner: dict, place_id: str):
    token = client.post(f"/api/places/{place_id}/share", headers=owner).json()["token"]
    return client.get(f"/api/shared/{token}")


def _place(client, owner: dict) -> str:
    return client.post("/api/places", json={"name": "Casa de la familia", "lat": -33.05, "lon": -71.55}, headers=owner).json()["id"]


def test_enlace_familiar_incluye_el_aviso_mas_reciente(make_client):
    with make_client() as client:
        svc = client.app.state.services
        owner = register(client)
        pid = _place(client, owner)
        # El endpoint push del dueño es el dato más delicado que NO debe salir por el enlace.
        svc.db.execute(
            "UPDATE subscribers SET push_endpoint = ? WHERE id = ?", ("https://push.ejemplo.invalid/canal-secreto", owner["X-Brasa-Token"])
        )
        _alert(svc, pid, "viejo", "aviso", "foco", hours_ago=30)
        _alert(
            svc,
            pid,
            "reciente",
            "urgente",
            "reporte",
            hours_ago=3,
            delivered_at=(datetime.now(timezone.utc) - timedelta(hours=3)).strftime(STAMP),
        )

        res = _shared(client, owner, pid)
        assert res.status_code == 200
        last = res.json()["last_alert"]
        assert last is not None
        assert set(last) == {"level", "kind", "created_at", "delivered_at", "title"}
        assert last["level"] == "urgente" and last["kind"] == "reporte"  # el más reciente, no el viejo
        assert last["title"] == "Aviso reciente" and last["delivered_at"]

        body = res.text
        for forbidden in ("subscriber_id", "share_token", "push_endpoint", "push.ejemplo.invalid", owner["X-Brasa-Token"], pid):
            assert forbidden not in body, f"el enlace familiar expone {forbidden!r}"


def test_enlace_familiar_sin_avisos_devuelve_null(make_client):
    with make_client() as client:
        owner = register(client)
        pid = _place(client, owner)
        res = _shared(client, owner, pid)
        assert res.status_code == 200 and res.json()["last_alert"] is None


def test_enlace_familiar_ignora_avisos_de_mas_de_48h(make_client):
    with make_client() as client:
        svc = client.app.state.services
        owner = register(client)
        pid = _place(client, owner)
        _alert(svc, pid, "antiguo", "urgente", "foco", hours_ago=60)
        res = _shared(client, owner, pid)
        assert res.status_code == 200 and res.json()["last_alert"] is None


def test_enlace_familiar_asume_foco_cuando_el_payload_no_trae_kind(make_client):
    """Los avisos satelitales (compose()) no guardan «kind» en el payload: por omisión es «foco»."""
    with make_client() as client:
        svc = client.app.state.services
        owner = register(client)
        pid = _place(client, owner)
        _alert(svc, pid, "sin-kind", "aviso", None, hours_ago=2)
        last = _shared(client, owner, pid).json()["last_alert"]
        assert last["kind"] == "foco" and last["level"] == "aviso" and last["delivered_at"] is None

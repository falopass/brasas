"""Contrato de privacidad entre dispositivos (QA-64, SEC-*).

Sin cuentas: la identidad es el token del dispositivo. Esta prueba fija de punta a punta
que el token de un dispositivo no puede leer, cambiar, borrar ni exportar nada de otro:
ni lugares, ni resúmenes, ni historial, ni avisos, ni reportes, ni enlaces compartidos.
Lo ajeno responde 404 (no 403: ni siquiera se filtra que existe) o una lista vacía.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

STAMP = "%Y-%m-%dT%H:%M:%SZ"


def _register(client) -> dict:
    """Dispositivo nuevo: `POST /api/subscribers` y el header que lo identifica."""
    token = client.post("/api/subscribers").json()["token"]
    return {"X-Brasa-Token": token}


def _add_place(client, headers: dict, name: str, lat: float, lon: float) -> str:
    r = client.post("/api/places", json={"name": name, "lat": lat, "lon": lon}, headers=headers)
    assert r.status_code == 201, f"no se pudo crear el lugar «{name}»: {r.text}"
    return r.json()["id"]


def _seed_alert(client, place_id: str) -> int:
    """Un aviso en la bandeja del lugar, como si lo hubiera generado un ciclo de ingesta."""
    svc = client.app.state.services
    moment = datetime.now(timezone.utc).strftime(STAMP)
    payload = {"title": "Foco de calor", "place": {"name": "Casa"}, "distance_km": 3.2, "url": "/#/mapa"}
    svc.db.execute(
        "INSERT INTO alerts(place_id, observation_id, level, distance_km, bearing_deg, upwind, lat, lon, "
        "observed_at, created_at, payload, delivered) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (place_id, "obs-priv-1", "urgente", 3.2, 90, 1, -33.06, -71.54, moment, moment, json.dumps(payload), json.dumps(["push"])),
    )
    return svc.db.one("SELECT id FROM alerts WHERE place_id = ?", (place_id,))["id"]


def _scenario(client):
    """Dos dispositivos: A con dos lugares, un aviso, un reporte y un enlace compartido; B sin nada."""
    a, b = _register(client), _register(client)
    place_a = _add_place(client, a, "Casa del Cerro Alegre", -33.05, -71.55)
    _add_place(client, a, "Parcela de los tíos", -35.43, -71.66)
    alert_a = _seed_alert(client, place_a)
    report = client.post("/api/reports", data={"lat": "-33.05", "lon": "-71.55", "kind": "humo"}, headers=a)
    assert report.status_code == 201, f"A no pudo enviar su reporte: {report.text}"
    share_token = client.post(f"/api/places/{place_a}/share", headers=a).json()["token"]
    return a, b, place_a, alert_a, share_token


def test_b_no_puede_leer_ni_tocar_los_lugares_de_a(make_client):
    """Cada ruta de lugares filtra por subscriber_id: para B, el lugar de A no existe."""
    with make_client() as client:
        a, b, place_a, _, _ = _scenario(client)

        body = client.get("/api/places", headers=b).json()["places"]
        assert body == [], "GET /api/places de B devolvió lugares que no son suyos"

        r = client.patch(f"/api/places/{place_a}", headers=b, json={"name": "Robado", "lat": -33.0, "lon": -71.0})
        assert r.status_code == 404, f"PATCH /api/places/{{id}} de B sobre un lugar de A: {r.status_code}"
        r = client.delete(f"/api/places/{place_a}", headers=b)
        assert r.status_code == 404, f"DELETE /api/places/{{id}} de B sobre un lugar de A: {r.status_code}"

        r = client.get(f"/api/places/{place_a}/summary", headers=b)
        assert r.status_code == 404, f"GET /api/places/{{id}}/summary de B: {r.status_code}"
        r = client.get(f"/api/places/{place_a}/history?days=30", headers=b)
        assert r.status_code == 404, f"GET /api/places/{{id}}/history de B: {r.status_code}"

        r = client.post(f"/api/places/{place_a}/share", headers=b)
        assert r.status_code == 404, f"POST /api/places/{{id}}/share de B: {r.status_code}"
        r = client.delete(f"/api/places/{place_a}/share", headers=b)
        assert r.status_code == 404, f"DELETE /api/places/{{id}}/share de B: {r.status_code}"

        # De verdad no se tocó nada: A sigue viendo sus lugares intactos.
        lugares = client.get("/api/places", headers=a).json()["places"]
        assert [p["name"] for p in lugares] == ["Casa del Cerro Alegre", "Parcela de los tíos"], (
            "los intentos de B modificaron los lugares de A"
        )


def test_b_no_ve_los_avisos_de_a_ni_opina_sobre_ellos(make_client):
    """La bandeja y la opinión de un aviso cruzan por el lugar, que es del dispositivo dueño."""
    with make_client() as client:
        a, b, _, alert_a, _ = _scenario(client)

        bandeja = client.get("/api/alerts", headers=b).json()
        assert bandeja["alerts"] == [] and bandeja["total"] == 0, "GET /api/alerts de B mostró avisos que no son suyos"

        r = client.post(f"/api/alerts/{alert_a}/feedback", headers=b, json={"value": "sirvio"})
        assert r.status_code == 404, f"POST /api/alerts/{{id}}/feedback de B: {r.status_code}"
        r = client.post(f"/api/alerts/{alert_a}/feedback", headers=a, json={"value": "sirvio"})
        assert r.status_code == 200, "A no pudo opinar sobre su propio aviso"


def test_b_no_ve_el_reporte_de_a_en_su_historial(make_client):
    """`/api/reports/mine` es solo del dispositivo que envió el reporte."""
    with make_client() as client:
        _, b, _, _, _ = _scenario(client)

        mio = client.get("/api/reports/mine", headers=b).json()
        assert mio["total"] == 0 and mio["reports"] == [], "GET /api/reports/mine de B mostró el reporte que envió A"


def test_b_no_ve_los_lugares_de_a_en_su_estado_ni_en_su_exportacion(make_client):
    """`/api/me` y `/api/me/export` de B no pueden contener ni el nombre ni el id de un lugar de A."""
    with make_client() as client:
        a, b, place_a, _, _ = _scenario(client)

        estado = client.get("/api/me", headers=b).json()
        assert estado["places"] == 0, "GET /api/me de B contó lugares que no son suyos"

        export = client.get("/api/me/export", headers=b)
        assert export.status_code == 200, "B no pudo exportar sus (cero) datos"
        texto = export.text
        assert "Casa del Cerro Alegre" not in texto and "Parcela de los tíos" not in texto, (
            "el export de B filtró el nombre de un lugar de A"
        )
        assert place_a not in texto, "el export de B filtró el id de un lugar de A"
        assert a["X-Brasa-Token"] not in texto, "el export de B filtró el token de A"


def test_borrar_a_b_no_le_borra_nada_a_a(make_client):
    """`DELETE /api/me` borra en cascada solo lo del dispositivo que pide."""
    with make_client() as client:
        a, b, place_a, alert_a, _ = _scenario(client)
        svc = client.app.state.services

        assert client.delete("/api/me", headers=b).json() == {"ok": True}

        lugares = client.get("/api/places", headers=a).json()["places"]
        assert [p["id"] for p in lugares] == [place_a, lugares[1]["id"]] and len(lugares) == 2, "borrar a B borró lugares de A"
        assert svc.db.one("SELECT COUNT(*) AS n FROM alerts WHERE id = ?", (alert_a,))["n"] == 1, "borrar a B borró avisos de A"
        assert svc.db.one("SELECT COUNT(*) AS n FROM reports WHERE subscriber_id = ?", (a["X-Brasa-Token"],))["n"] == 1, (
            "borrar a B borró el reporte de A"
        )


def test_sin_token_toda_ruta_privada_responde_401(make_client):
    """Nada personal sale sin el header `X-Brasa-Token` válido."""
    with make_client() as client:
        _, _, place_a, alert_a, _ = _scenario(client)
        place_body = {"name": "x", "lat": -33.0, "lon": -71.0}

        casos = [
            ("GET", "/api/me", {}),
            ("GET", "/api/me/export", {}),
            ("DELETE", "/api/me", {}),
            ("GET", "/api/places", {}),
            ("PATCH", f"/api/places/{place_a}", {"json": place_body}),
            ("DELETE", f"/api/places/{place_a}", {}),
            ("GET", f"/api/places/{place_a}/summary", {}),
            ("GET", f"/api/places/{place_a}/history?days=30", {}),
            ("POST", f"/api/places/{place_a}/share", {}),
            ("DELETE", f"/api/places/{place_a}/share", {}),
            ("GET", "/api/alerts", {}),
            ("POST", f"/api/alerts/{alert_a}/feedback", {"json": {"value": "sirvio"}}),
            ("GET", "/api/reports/mine", {}),
        ]
        for metodo, ruta, kwargs in casos:
            r = client.request(metodo, ruta, **kwargs)
            assert r.status_code == 401, f"{metodo} {ruta} sin token respondió {r.status_code}, no 401"


def test_el_enlace_compartido_abre_solo_la_vista_publica(make_client):
    """`/api/shared/{token}` es público a propósito: abre con el token de compartir,
    no con el token del dispositivo, y ese token no sirve como llave de nada privado."""
    with make_client() as client:
        a, _, place_a, _, share_token = _scenario(client)

        r = client.get(f"/api/shared/{share_token}")
        assert r.status_code == 200, "el enlace compartido de A no abrió sin credenciales"
        assert r.json()["place"]["name"] == "Casa del Cerro Alegre"

        r = client.get(f"/api/shared/{a['X-Brasa-Token']}")
        assert r.status_code == 404, "el token del dispositivo abrió la vista compartida"

        # El token de compartir no es una llave maestra: como X-Brasa-Token no identifica a nadie.
        r = client.get("/api/places", headers={"X-Brasa-Token": share_token})
        assert r.status_code == 401, "el token de compartir abrió rutas privadas"
        r = client.get("/api/alerts", headers={"X-Brasa-Token": share_token})
        assert r.status_code == 401, "el token de compartir abrió la bandeja de avisos"
        r = client.delete(f"/api/places/{place_a}", headers={"X-Brasa-Token": share_token})
        assert r.status_code == 401, "el token de compartir pudo borrar el lugar"

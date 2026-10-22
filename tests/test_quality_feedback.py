"""GET /api/quality/feedback: la opinión sobre los avisos como agregado público (ALR-05 → QA-05).

Cada aviso del historial acepta una opinión («sirvio», «no_sirvio», «quema»). Lo que se publica
es solo el conteo global: la página de calidad lo muestra sin identificar dispositivos, lugares
ni avisos, y sin pedir el token del dispositivo.
"""

from __future__ import annotations

from tests.test_features import seed_alerts


def test_agrega_opiniones_sin_identificarlas_y_sin_opiniones_devuelve_ceros(make_client):
    with make_client() as client:
        empty = client.get("/api/quality/feedback")
        assert empty.json() == {"total": 0, "counts": {"sirvio": 0, "no_sirvio": 0, "quema": 0}, "since": None}
        assert "max-age=60" in empty.headers.get("cache-control", "")

        one = seed_alerts(client, 3)
        ids_one = [a["id"] for a in client.get("/api/alerts", headers=one).json()["alerts"]]
        client.post(f"/api/alerts/{ids_one[0]}/feedback", json={"value": "sirvio"}, headers=one)
        client.post(f"/api/alerts/{ids_one[1]}/feedback", json={"value": "quema"}, headers=one)
        # El tercer aviso del primer dispositivo queda sin opinión: no entra al conteo ni a `since`.
        two = seed_alerts(client, 1)
        alert_two = client.get("/api/alerts", headers=two).json()["alerts"][0]["id"]
        client.post(f"/api/alerts/{alert_two}/feedback", json={"value": "no_sirvio"}, headers=two)
        body = client.get("/api/quality/feedback").json()  # público: no pide token
        expected_since = client.app.state.services.db.one("SELECT MIN(created_at) AS t FROM alerts WHERE feedback IS NOT NULL")["t"]
    assert set(body) == {"total", "counts", "since"}
    assert body["total"] == 3
    assert body["counts"] == {"sirvio": 1, "no_sirvio": 1, "quema": 1}
    assert body["since"] == expected_since

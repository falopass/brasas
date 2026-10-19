"""ALR-05: «¿Te sirvió este aviso?» — cada aviso del historial se evalúa con un toque.

La opinión («sirvio», «no_sirvio», «quema») se guarda una sola vez y solo sobre los avisos del
propio dispositivo. `/api/alerts` devuelve además `feedback_counts` para medir la calidad real
y la fatiga de los avisos (QA-05).
"""
from __future__ import annotations

from tests.test_features import seed_alerts


def test_opinar_un_aviso_guarda_la_opinion(make_client):
    with make_client() as client:
        headers = seed_alerts(client, 2)
        alert = client.get("/api/alerts", headers=headers).json()["alerts"][0]
        res = client.post(f"/api/alerts/{alert['id']}/feedback", json={"value": "sirvio"}, headers=headers)
        assert res.status_code == 200 and res.json()["feedback"] == "sirvio"
        saved = client.get("/api/alerts", headers=headers).json()["alerts"][0]
        assert saved["id"] == alert["id"] and saved["feedback"] == "sirvio"


def test_opinar_dos_veces_no_pisa_la_primera_opinion(make_client):
    with make_client() as client:
        headers = seed_alerts(client, 1)
        alert_id = client.get("/api/alerts", headers=headers).json()["alerts"][0]["id"]
        first = client.post(f"/api/alerts/{alert_id}/feedback", json={"value": "no_sirvio"}, headers=headers)
        second = client.post(f"/api/alerts/{alert_id}/feedback", json={"value": "quema"}, headers=headers)
        assert first.json()["feedback"] == "no_sirvio" and second.json()["feedback"] == "no_sirvio"
        row = client.app.state.services.db.one("SELECT feedback FROM alerts WHERE id = ?", (alert_id,))
        assert row["feedback"] == "no_sirvio"


def test_no_se_puede_opinar_un_aviso_de_otro_dispositivo(make_client):
    with make_client() as client:
        mine = seed_alerts(client, 1)
        alert_id = client.get("/api/alerts", headers=mine).json()["alerts"][0]["id"]
        other = {"X-Brasa-Token": client.post("/api/subscribers").json()["token"]}
        res = client.post(f"/api/alerts/{alert_id}/feedback", json={"value": "sirvio"}, headers=other)
        assert res.status_code == 404
        row = client.app.state.services.db.one("SELECT feedback FROM alerts WHERE id = ?", (alert_id,))
        assert row["feedback"] is None


def test_feedback_counts_cuenta_cada_opinion_y_los_sin_opinion(make_client):
    with make_client() as client:
        headers = seed_alerts(client, 4)
        ids = [a["id"] for a in client.get("/api/alerts", headers=headers).json()["alerts"]]
        client.post(f"/api/alerts/{ids[0]}/feedback", json={"value": "sirvio"}, headers=headers)
        client.post(f"/api/alerts/{ids[1]}/feedback", json={"value": "quema"}, headers=headers)
        counts = client.get("/api/alerts", headers=headers).json()["feedback_counts"]
        assert counts == {"sirvio": 1, "no_sirvio": 0, "quema": 1, "sin_opinion": 2}


def test_la_opinion_rechaza_valores_fuera_de_la_lista(make_client):
    with make_client() as client:
        headers = seed_alerts(client, 1)
        alert_id = client.get("/api/alerts", headers=headers).json()["alerts"][0]["id"]
        assert client.post(f"/api/alerts/{alert_id}/feedback",
                           json={"value": "genial"}, headers=headers).status_code == 422
        assert client.post(f"/api/alerts/{alert_id}/feedback",
                           json={"value": ""}, headers=headers).status_code == 422


def test_opinar_un_aviso_que_no_existe_da_404(make_client):
    with make_client() as client:
        headers = seed_alerts(client, 1)
        res = client.post("/api/alerts/99999/feedback", json={"value": "sirvio"}, headers=headers)
        assert res.status_code == 404


def test_opinar_requiere_el_token_del_dispositivo(make_client):
    with make_client() as client:
        assert client.post("/api/alerts/1/feedback", json={"value": "sirvio"}).status_code == 401

import asyncio

import httpx

from backend.providers import conaf
from tests.conftest import json_response

ROWS = [
    {"date": "2027-01-20", "com_id": 5109, "horas": 1, "SUM_br_ha": 1200.4, "proportion": 0.1},
    {"date": "2027-01-20", "com_id": 5109, "horas": 3, "SUM_br_ha": 800.2, "proportion": 0.07},
    {"date": "2027-01-21", "com_id": 5109, "horas": 2, "SUM_br_ha": 500, "proportion": 0.04},
    {"date": "2027-01-20", "com_id": 13101, "horas": 0, "SUM_br_ha": 0, "proportion": 0},
    {"date": "malo", "com_id": "x"},
]


def test_summary_keeps_the_longest_spell_and_adds_the_area():
    days = conaf.summarize(ROWS)
    assert days == [
        {"comuna_code": 5109, "date": "2027-01-20", "hours": 3, "area_ha": 2001, "proportion": 0.17},
        {"comuna_code": 5109, "date": "2027-01-21", "hours": 2, "area_ha": 500, "proportion": 0.04},
    ]


def test_boton_rojo_is_ingested_and_shown_with_its_source(make_client, web):
    pages = []

    def layer(request: httpx.Request) -> httpx.Response:
        pages.append(request.url.params["resultOffset"])
        if request.url.params["resultOffset"] == "0":
            return json_response({"features": [{"attributes": r} for r in ROWS[:2]], "exceededTransferLimit": True})
        return json_response({"features": [{"attributes": r} for r in ROWS[2:]]})

    web.add(lambda r: "arcgis.com" in r.url.host, layer)
    with make_client(GOES_ENABLED="0") as client:
        svc = client.app.state.services
        assert asyncio.run(svc.ingest_boton_rojo()) == 2 and pages == ["0", "2"]
        assert svc.boton_rojo_due() is False
        risk = client.get("/api/risk?day=2027-01-20").json()
        assert risk["boton_rojo"] == {"5109": {"hours": 3, "area_ha": 2001, "proportion": 0.17}}
        assert risk["boton_rojo_source"]["name"] == "CONAF · Botón Rojo" and "No indica un incendio" in risk["boton_rojo_source"]["note"]
        status = client.get("/api/status").json()
        assert any(r["product"] == "BOTON_ROJO" and r["ok"] for r in status["runs"])


def test_a_failed_boton_rojo_fetch_is_recorded_and_does_not_break_the_cycle(make_client, web):
    web.add(lambda r: "arcgis.com" in r.url.host, lambda r: json_response({"error": {"code": 499}}))
    with make_client(GOES_ENABLED="0") as client:
        svc = client.app.state.services
        result = asyncio.run(svc.tick())
        assert "boton_rojo_error" in result and "firms_new" in result
        status = client.get("/api/status").json()
        assert any(r["product"] == "BOTON_ROJO" and not r["ok"] for r in status["runs"])

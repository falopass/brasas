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


CSV_HEAD = ("id,temporada,nombre,estado,num_reg,reg_id,f_inicio,f_control,f_extincion,f_deteccion,f_aviso,f_despacho,f_salida,"
            "f_arribo,f_ataque,sup_total,lat,lon,ambito,comb_inicial,snaspe,comuna,provincia,region,reg_order,nom_order,fmt_inicio,"
            "dia_nom,rango_hora,sha2_ultimo_poligono\n")


def fire_row(fid, name, estado, start_local, lat, lon, area="1,50", extinct=""):
    return (f'{fid},2027,{name},{estado},1,5,{start_local},,{extinct},,,,,,,"{area}",{lat},{lon},CONAF,Pastizal,,Quilpué,'
            f"Marga Marga,Valparaíso,6,05 Valparaíso,{start_local}:00,lunes,15,\n")


def test_fires_csv_is_parsed_in_chile_time_with_comma_decimals():
    fires = conaf.parse_fires(CSV_HEAD + fire_row("1", "EL BELLOTO", "En combate", "2027-01-20 15:30", -33.06, -71.40, "1.234,50")
                              + fire_row("2", "MALO", "Extinguido", "", -33, -71))
    assert fires == [{"id": "1", "name": "EL BELLOTO", "status_raw": "En combate", "status": "confirmado",
                      "started_at": "2027-01-20T18:30:00Z", "controlled_at": None, "extinguished_at": None, "area_ha": 1234.5,
                      "lat": -33.06, "lon": -71.4, "comuna": "Quilpué", "region": "Valparaíso", "ambito": "CONAF", "fuel": "Pastizal"}]


def test_official_fire_confirms_the_incident_and_warns_nearby_places(make_client, web):
    from datetime import datetime, timedelta, timezone
    from zoneinfo import ZoneInfo
    from backend import incidents
    from tests.test_api import register
    from tests.test_incidents import obs
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    local = (now - timedelta(minutes=40)).astimezone(ZoneInfo("America/Santiago")).strftime("%Y-%m-%d %H:%M")
    csv_text = {"body": CSV_HEAD + fire_row("10", "VIEJO", "Extinguido", "2026-01-01 10:00", -20.0, -70.0)}
    web.add(lambda r: "githubusercontent" in r.url.host, lambda r: httpx.Response(200, text=csv_text["body"]))
    with make_client(GOES_ENABLED="0") as client:
        svc = client.app.state.services
        headers = register(client)
        client.post("/api/places", json={"name": "Casa", "kind": "casa", "lat": -33.07, "lon": -71.40, "radius_km": 10}, headers=headers)
        first = asyncio.run(svc.ingest_official_fires())
        assert first["official_fires"] == 1 and first["official_alerts"] == 0
        db = svc.db
        [inc] = incidents.update(db, [obs(db, "sat", -33.061, -71.401, when=now - timedelta(minutes=50))], now)
        csv_text["body"] += fire_row("11", "EL BELLOTO", "En combate", local, -33.06, -71.40)
        second = asyncio.run(svc.ingest_official_fires())
        assert second["official_new"] == 1 and second["official_linked"] == 1 and second["official_alerts"] == 1
        detail = client.get(f"/api/incidents/{inc['id']}").json()
        assert detail["incident"]["status"] == "confirmado" and detail["official_fire"]["name"] == "EL BELLOTO"
        alert = client.get("/api/alerts", headers=headers).json()["alerts"][0]
        assert alert["level"] == "urgente" and "CONAF informa" in alert["title"]
        place_id = client.get("/api/places", headers=headers).json()["places"][0]["id"]
        summary = client.get(f"/api/places/{place_id}/summary", headers=headers).json()
        assert summary["official"][0]["name"] == "EL BELLOTO" and summary["status"] == "urgente"
        assert asyncio.run(svc.ingest_official_fires())["official_alerts"] == 0  # no se repite
        csv_text["body"] = csv_text["body"].replace("EL BELLOTO,En combate", "EL BELLOTO,Controlado")
        asyncio.run(svc.ingest_official_fires())
        assert client.get(f"/api/incidents/{inc['id']}").json()["incident"]["status"] == "controlado"
        listing = client.get("/api/official-fires").json()
        assert [f["name"] for f in listing["fires"]] == ["EL BELLOTO"] and listing["source"]["url"].startswith("https://github.com/")

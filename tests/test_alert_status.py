"""ALR-02: cuando CONAF da por controlado o extinguido un incendio que ya avisó a un lugar,
ese lugar recibe un único aviso de cierre — la familia deja de preocuparse.

El cierre solo va a los lugares que ya recibieron el `conaf:<id>` original: avisar de un
cierre a quien nunca oyó hablar del incendio solo agrega ruido.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx

from backend import alerts
from backend.db import Database
from tests.test_conaf import CSV_HEAD, fire_row

FIRE = {"id": "conaf-1", "name": "EL BELLOTO", "status": "controlado", "status_raw": "Controlado",
        "started_at": "2026-10-17T09:00:00Z", "controlled_at": "2026-10-18T10:00:00Z",
        "extinguished_at": None, "area_ha": 12.0, "lat": -33.06, "lon": -71.40, "comuna": "Quilpué",
        "region": "Valparaíso", "ambito": "CONAF", "fuel": "Pastizal"}


def place(db: Database, pid: str = "p1", sid: str = "s1", lat: float = -33.05, lon: float = -71.40,
          radius_km: float = 10) -> None:
    db.execute("INSERT OR IGNORE INTO subscribers(id, created_at) VALUES (?, '2026-01-01T00:00:00Z')", (sid,))
    db.execute("INSERT INTO places(id, subscriber_id, name, kind, lat, lon, radius_km, created_at) "
               "VALUES (?,?,'Casa','casa',?,?,?,'2026-01-01T00:00:00Z')", (pid, sid, lat, lon, radius_km))


def ingest_csv() -> dict:
    """El CSV de CONAF (mutable entre ingestas). La primera carga no avisa en masa: el incendio
    «11» entra recién en la segunda pasada, cuando la tabla ya conoce al «10»."""
    return {"body": CSV_HEAD + fire_row("10", "VIEJO", "Extinguido", "2026-01-01 10:00", -20.0, -70.0)}


def add_fire(csv: dict, estado: str) -> None:
    local = (datetime.now(timezone.utc) - timedelta(minutes=40)).astimezone(
        ZoneInfo("America/Santiago")).strftime("%Y-%m-%d %H:%M")
    csv["body"] += fire_row("11", "EL BELLOTO", estado, local, -33.06, -71.40)


def test_a_fire_now_controlled_warns_the_places_it_had_alerted(make_client, web):
    csv = ingest_csv()
    web.add(lambda r: "githubusercontent" in r.url.host, lambda r: httpx.Response(200, text=csv["body"]))
    with make_client(GOES_ENABLED="0") as client:
        svc = client.app.state.services
        place(svc.db)
        asyncio.run(svc.ingest_official_fires())              # primera carga: pobla `known`
        add_fire(csv, "En combate")
        second = asyncio.run(svc.ingest_official_fires())
        assert second["official_new"] == 1 and second["official_alerts"] == 1
        csv["body"] = csv["body"].replace("EL BELLOTO,En combate", "EL BELLOTO,Controlado")
        third = asyncio.run(svc.ingest_official_fires())
        assert third["official_new"] == 0 and third["official_alerts"] == 1
        [row] = svc.db.query("SELECT * FROM alerts WHERE observation_id = 'conaf:11:estado'")
        assert row["place_id"] == "p1" and row["level"] == "aviso"  # el cierre nunca es «urgente»
        payload = json.loads(row["payload"])
        assert "quedó controlado según CONAF" in payload["body"]
        assert "dejará de avisar" in payload["body"]
        assert payload["footer"] == alerts.OFFICIAL_FOOTER


def test_a_place_without_the_first_alert_gets_no_closure(make_client, web):
    """El lugar está fuera del radio del incendio: nunca recibió el aviso, así que tampoco
    recibe el cierre (aunque el incendio cambie de estado)."""
    csv = ingest_csv()
    web.add(lambda r: "githubusercontent" in r.url.host, lambda r: httpx.Response(200, text=csv["body"]))
    with make_client(GOES_ENABLED="0") as client:
        svc = client.app.state.services
        place(svc.db, lat=-33.90, lon=-71.40, radius_km=5)   # ~93 km del foco, radio 5 km
        asyncio.run(svc.ingest_official_fires())
        add_fire(csv, "En combate")
        assert asyncio.run(svc.ingest_official_fires())["official_alerts"] == 0
        csv["body"] = csv["body"].replace("EL BELLOTO,En combate", "EL BELLOTO,Extinguido")
        assert asyncio.run(svc.ingest_official_fires())["official_alerts"] == 0
        assert svc.db.one("SELECT COUNT(*) AS n FROM alerts")["n"] == 0


def test_repeating_the_ingestion_does_not_duplicate_the_closure(make_client, web):
    """El UNIQUE(place_id, observation_id) hace idempotente el insert; además, al siguiente
    ciclo el estado ya no cambió, así que ni se intenta."""
    csv = ingest_csv()
    web.add(lambda r: "githubusercontent" in r.url.host, lambda r: httpx.Response(200, text=csv["body"]))
    with make_client(GOES_ENABLED="0") as client:
        svc = client.app.state.services
        place(svc.db)
        asyncio.run(svc.ingest_official_fires())
        add_fire(csv, "En combate")
        asyncio.run(svc.ingest_official_fires())
        csv["body"] = csv["body"].replace("EL BELLOTO,En combate", "EL BELLOTO,Controlado")
        asyncio.run(svc.ingest_official_fires())
        again = asyncio.run(svc.ingest_official_fires())   # mismo CSV «Controlado»
        assert again["official_alerts"] == 0
        assert svc.db.one("SELECT COUNT(*) AS n FROM alerts WHERE observation_id = 'conaf:11:estado'")["n"] == 1


def test_the_closure_names_the_final_state():
    """«Controlado» y «extinguido» se dicen con su nombre; el enlace va a la ficha si existe."""
    payload = alerts.compose_status_change(
        {"id": "p1", "name": "Casa", "lat": -33.05, "lon": -71.40, "radius_km": 10, "older_adult": 0},
        {**FIRE, "status": "extinguido"}, 1.2, 270, incident_id="inc-9")
    assert "quedó extinguido según CONAF" in payload["body"] and payload["url"] == "/#/incendio/inc-9"

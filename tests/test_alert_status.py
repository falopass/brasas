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
        # Repetir la ingesta con el mismo CSV no duplica el cierre (UNIQUE place_id, observation_id).
        assert asyncio.run(svc.ingest_official_fires())["official_alerts"] == 0
        assert svc.db.one("SELECT COUNT(*) AS n FROM alerts WHERE observation_id = 'conaf:11:estado'")["n"] == 1


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


def test_the_closure_names_the_final_state():
    """«Controlado» y «extinguido» se dicen con su nombre; el enlace va a la ficha si existe."""
    payload = alerts.compose_status_change(
        {"id": "p1", "name": "Casa", "lat": -33.05, "lon": -71.40, "radius_km": 10, "older_adult": 0},
        {**FIRE, "status": "extinguido"}, 1.2, 270, incident_id="inc-9")
    assert "quedó extinguido según CONAF" in payload["body"] and payload["url"] == "/#/incendio/inc-9"


def test_the_closure_does_not_hide_new_evidence(tmp_path):
    """El aviso de cierre queda fuera de la deduplicación: dice «deja de avisar», no «no hay
    fuego». Una detección satelital junto al incendio controlado (reactivación) debe avisar."""
    now = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)
    db = Database(tmp_path / "brasa.db")
    place(db)
    db.execute("INSERT INTO alerts(place_id, observation_id, level, distance_km, bearing_deg, upwind, "
               "lat, lon, observed_at, created_at, payload) VALUES ('p1','conaf:11:estado','aviso',1,0,0,"
               "-33.06,-71.40,'2026-10-18T11:00:00Z','2026-10-18T11:30:00Z','{}')")
    # ~2,8 km del cierre (deduplica si el cierre contara) pero ~3,9 km del lugar: nivel «aviso».
    reactivacion = {"id": "sat-1", "source": "firms", "sensor": "VIIRS", "satellite": "N20",
                    "resolution_m": 375, "lat": -33.085, "lon": -71.40, "frp_mw": 20.0,
                    "confidence": "alta", "comuna_code": 13101,
                    "observed_at": now.strftime("%Y-%m-%dT%H:%M:%SZ")}
    created = asyncio.run(alerts.evaluate(db, [reactivacion], now=now))
    assert len(created) == 1

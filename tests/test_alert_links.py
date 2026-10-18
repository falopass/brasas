"""FIX-04: el enlace del aviso lleva a la ficha del incidente, no a un mapa a buscar.

Un aviso decía «Foco de calor a 3 km» y abría el mapa centrado en el punto: había que encontrar el
incendio entre todos los de la zona. Si el aviso sabe de qué incidente habla, va directo a su ficha.
Y si no lo sabe (una detección suelta, un incendio de CONAF sin incidente unido), al mapa.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from backend import alerts
from backend.db import Database
from backend.notify import telegram

NOW = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)
PLACE = {"id": "p1", "name": "Casa", "lat": -33.05, "lon": -71.55, "radius_km": 10, "older_adult": 0}
FIRE = {"id": "conaf-1", "name": "EL BELLOTO", "status": "confirmado", "status_raw": "En combate",
        "started_at": "2026-10-18T09:00:00Z", "area_ha": 12.0, "lat": -33.06, "lon": -71.40, "comuna": "Quilpué"}


def observation(ident: str) -> dict:
    return {"id": ident, "source": "firms", "sensor": "VIIRS", "satellite": "N20", "resolution_m": 375,
            "lat": -33.05, "lon": -71.55, "frp_mw": 20.0, "confidence": "alta", "comuna_code": 13101,
            "observed_at": NOW.strftime("%Y-%m-%dT%H:%M:%SZ")}


def test_the_link_goes_to_the_incident_sheet_when_it_is_known():
    incident = {"id": "inc-42", "status": "posible", "n_obs": 5, "first_seen_at": "2026-10-18T10:00:00Z",
                "last_seen_at": "2026-10-18T11:30:00Z", "sensors": "VIIRS,ABI"}
    payload = alerts.compose(PLACE, observation("o1"), 3.2, 90, upwind=False, level="aviso", wind=None,
                             others=0, incident=incident)
    assert payload["url"] == "/#/incendio/inc-42"
    assert payload["incident"]["id"] == "inc-42"


def test_a_lone_detection_still_points_to_the_map():
    payload = alerts.compose(PLACE, observation("o2"), 3.2, 90, upwind=False, level="aviso", wind=None,
                             others=0, incident=None)
    assert payload["url"].startswith("/#/mapa?lat=-33.0500&lon=-71.5500")


def test_the_official_alert_uses_the_linked_incident():
    linked = alerts.compose_official(PLACE, FIRE, 4.0, 90, "urgente", incident_id="inc-77")
    assert linked["url"] == "/#/incendio/inc-77"
    alone = alerts.compose_official(PLACE, FIRE, 4.0, 90, "urgente")
    assert alone["url"].startswith("/#/mapa?lat=-33.0600&lon=-71.4000")


def test_evaluate_official_finds_the_linked_incident(tmp_path):
    """El vínculo lo deja la ingesta; aquí se comprueba que el aviso lo usa."""
    db = Database(tmp_path / "brasa.db")
    db.execute("INSERT INTO subscribers(id, created_at) VALUES ('s1','2026-10-01T00:00:00Z')")
    db.execute("INSERT INTO places(id, subscriber_id, name, kind, lat, lon, radius_km, created_at) "
               "VALUES ('p1','s1','Casa','casa',-33.05,-71.55,20,'2026-10-01T00:00:00Z')")
    db.execute("INSERT INTO incidents(id, status, status_changed_at, first_seen_at, last_seen_at, lat, lon, min_lat, "
               "max_lat, min_lon, max_lon, n_obs, n_reliable, sensors, comuna_code, official_ref, updated_at) "
               "VALUES ('inc-9','confirmado','2026-10-18T09:00:00Z','2026-10-18T08:00:00Z','2026-10-18T10:00:00Z',"
               "-33.06,-71.40,-33.07,-33.05,-71.41,-71.39,3,3,'VIIRS',13101,'conaf-1','2026-10-18T10:00:00Z')")
    created = asyncio.run(alerts.evaluate_official(db, [FIRE], now=NOW))
    assert len(created) == 1
    assert created[0]["payload"]["url"] == "/#/incendio/inc-9"


def test_the_freshest_incident_wins_when_several_share_the_official_ref(tmp_path):
    """Un rebrote deja dos incidentes con el mismo official_ref: el aviso va a la ficha viva."""
    db = Database(tmp_path / "brasa.db")
    db.execute("INSERT INTO subscribers(id, created_at) VALUES ('s1','2026-10-01T00:00:00Z')")
    db.execute("INSERT INTO places(id, subscriber_id, name, kind, lat, lon, radius_km, created_at) "
               "VALUES ('p1','s1','Casa','casa',-33.05,-71.55,20,'2026-10-01T00:00:00Z')")
    for ident, last_seen in (("inc-viejo", "2026-10-18T09:00:00Z"), ("inc-fresco", "2026-10-18T11:30:00Z")):
        db.execute("INSERT INTO incidents(id, status, status_changed_at, first_seen_at, last_seen_at, lat, lon, "
                   "min_lat, max_lat, min_lon, max_lon, n_obs, n_reliable, sensors, comuna_code, official_ref, "
                   "updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (ident, "confirmado", last_seen, "2026-10-18T08:00:00Z", last_seen, -33.06, -71.40, -33.07,
                    -33.05, -71.41, -71.39, 3, 3, "VIIRS", 13101, "conaf-1", last_seen))
    created = asyncio.run(alerts.evaluate_official(db, [FIRE], now=NOW))
    assert created[0]["payload"]["url"] == "/#/incendio/inc-fresco"


def test_the_telegram_message_names_where_the_link_goes():
    base = "https://brasa.example"
    sheet = telegram.format_alert({"title": "T", "body": "B", "footer": "F", "level": "aviso",
                                   "url": "/#/incendio/inc-1"}, base)
    assert "Ver el incidente: https://brasa.example/#/incendio/inc-1" in sheet
    mapa = telegram.format_alert({"title": "T", "body": "B", "footer": "F", "level": "aviso",
                                  "url": "/#/mapa?lat=-33&lon=-71&z=12"}, base)
    assert "Ver en el mapa: https://brasa.example/#/mapa?lat=-33&lon=-71&z=12" in mapa

"""ALR-43: aviso de acercamiento.

Cuando el foco más cercano de un incidente ya avisado cae a la mitad de la distancia del último
aviso del lugar (o bajo ACERCA_KM si el aviso anterior era a más de ACERCA_KM), el lugar recibe
una única actualización «<incidente>:acerca». La deduplicación de detecciones no la bloquea —
el foco nuevo puede estar a menos de DEDUPE_KM del anterior — y nunca se repite: la fila ya
escrita en `alerts` lo veda.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest

from backend import alerts
from backend.db import Database

NOW = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)


def observation(ident: str, lat: float, lon: float, confidence: str = "alta") -> dict:
    return {"id": ident, "source": "firms", "sensor": "VIIRS", "satellite": "N20", "resolution_m": 375,
            "lat": lat, "lon": lon, "frp_mw": 20.0, "confidence": confidence, "comuna_code": 13101,
            "observed_at": (NOW - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")}


@pytest.fixture
def db(tmp_path):
    d = Database(tmp_path / "brasa.db")
    d.execute("INSERT INTO subscribers(id, created_at) VALUES ('s1','2026-01-01T00:00:00Z')")
    d.execute("INSERT INTO places(id, subscriber_id, name, kind, lat, lon, radius_km, created_at) "
              "VALUES ('casa','s1','Casa','casa',-33.05,-71.55,20,'2026-01-01T00:00:00Z')")
    return d


def incidente(db: Database, ident: str = "inc-1", fixed: int = 0) -> None:
    db.execute("INSERT INTO incidents(id, status, status_changed_at, first_seen_at, last_seen_at, lat, lon, "
               "min_lat, max_lat, min_lon, max_lon, n_obs, n_reliable, sensors, updated_at, fixed_source) "
               "VALUES (?,'posible','2026-10-18T09:00:00Z','2026-10-18T08:00:00Z','2026-10-18T11:50:00Z',"
               "-33.0,-71.55,-33.1,-32.9,-71.6,-71.5,4,4,'VIIRS','2026-10-18T11:50:00Z',?)", (ident, fixed))


def vincula(db: Database, obs_id: str, inc: str = "inc-1") -> None:
    db.execute("INSERT INTO incident_observations(observation_id, incident_id) VALUES (?,?)", (obs_id, inc))


def aviso_previo(db: Database, inc: str = "inc-1", km: float = 12.0, lat: float = -32.94,
                 lon: float = -71.55) -> None:
    """La fila que dejó un aviso anterior del mismo incidente (su payload lleva incident.id)."""
    payload = {"level": "aviso", "place": {"id": "casa"}, "incident": {"id": inc}}
    db.execute("INSERT INTO alerts(place_id, observation_id, level, distance_km, bearing_deg, upwind, "
               "lat, lon, observed_at, created_at, payload) VALUES ('casa',?,'aviso',?,0,0,?,?,"
               "'2026-10-18T10:00:00Z','2026-10-18T10:05:00Z',?)",
               (f"obs-previa-{inc}", km, lat, lon, json.dumps(payload)))


def test_incendio_que_se_acerca_de_12_a_5_km_avisa(db):
    """El caso del encargo: el foco más cercano pasó de 12 a 5 km → el lugar se entera."""
    incidente(db)
    aviso_previo(db, km=12.0, lat=-32.94, lon=-71.55)
    obs = observation("o-nueva", -33.005, -71.55)   # ~5 km al norte del lugar
    vincula(db, "o-nueva")
    created = asyncio.run(alerts.evaluate(db, [obs], now=NOW))
    assert len(created) == 1
    payload = created[0]["payload"]
    d = alerts.haversine_km(-33.05, -71.55, obs["lat"], obs["lon"])
    assert payload["observation"]["id"] == "inc-1:acerca"
    assert f"ahora a {d:.1f} km (antes 12.0 km), al norte" in payload["body"]
    assert payload["level"] == "aviso"


def test_el_acercamiento_no_se_repite(db):
    """Un segundo foco más cercano del mismo incidente no produce otro «:acerca»."""
    incidente(db)
    aviso_previo(db)
    obs1 = observation("o-1", -33.005, -71.55)
    vincula(db, "o-1")
    created = asyncio.run(alerts.evaluate(db, [obs1], now=NOW))
    assert created[0]["payload"]["observation"]["id"] == "inc-1:acerca"
    obs2 = observation("o-2", -33.05, -71.507)   # ~4 km al oriente del lugar: mismo incidente, otro frente
    vincula(db, "o-2")
    created2 = asyncio.run(alerts.evaluate(db, [obs2], now=NOW))
    n = db.one("SELECT COUNT(*) AS n FROM alerts WHERE observation_id = 'inc-1:acerca'")["n"]
    assert n == 1
    # el frente nuevo sigue las reglas normales (no es duplicado del acercamiento: están a >3 km)
    assert created2 and created2[0]["payload"]["observation"]["id"] == "o-2"


def test_incendio_que_se_aleja_no_avisa_acercamiento(db):
    incidente(db)
    aviso_previo(db, km=8.0, lat=-33.128, lon=-71.55)   # último aviso a 8 km al sur
    obs = observation("o-lejos", -32.96, -71.55)         # el foco más cercano queda a ~10 km: se alejó
    vincula(db, "o-lejos")
    asyncio.run(alerts.evaluate(db, [obs], now=NOW))
    assert db.one("SELECT COUNT(*) AS n FROM alerts WHERE observation_id LIKE '%:acerca'")["n"] == 0


def test_fuente_fija_no_genera_acercamiento(db):
    """Volcán o industria: el incidente ni siquiera entra como candidato."""
    incidente(db, fixed=1)
    aviso_previo(db)
    obs = observation("o-fija", -33.005, -71.55)
    vincula(db, "o-fija")
    assert asyncio.run(alerts.evaluate(db, [obs], now=NOW)) == []


def test_deteccion_no_confiable_no_avisa(db):
    incidente(db)
    aviso_previo(db)
    obs = observation("o-debil", -33.005, -71.55, confidence="baja")
    vincula(db, "o-debil")
    assert asyncio.run(alerts.evaluate(db, [obs], now=NOW)) == []


def test_la_deduplicacion_normal_no_bloquea_el_acercamiento(db):
    """El foco nuevo está a <1 km del punto del último aviso: la deduplicación lo marcaría como
    duplicado, pero cruzó la cota de 5 km (venía de 5,4) y el acercamiento sale igual."""
    incidente(db)
    aviso_previo(db, km=5.4, lat=-33.0014, lon=-71.55)
    obs = observation("o-cerca", -33.006, -71.55)   # ~4,9 km del lugar, ~0,5 km del aviso previo
    vincula(db, "o-cerca")
    created = asyncio.run(alerts.evaluate(db, [obs], now=NOW))
    assert len(created) == 1
    assert created[0]["payload"]["observation"]["id"] == "inc-1:acerca"


def test_incendio_sin_aviso_previo_avisa_por_la_via_normal(db):
    """La primera detección alertable del incidente avisa como siempre; el acercamiento necesita
    un aviso anterior contra el que medir."""
    incidente(db)
    obs = observation("o-primera", -33.005, -71.55)
    vincula(db, "o-primera")
    created = asyncio.run(alerts.evaluate(db, [obs], now=NOW))
    assert len(created) == 1
    assert created[0]["payload"]["observation"]["id"] == "o-primera"


def test_el_nivel_lo_decide_classify(db):
    """Un acercamiento a menos de 2 km es «urgente», como cualquier foco a esa distancia."""
    incidente(db)
    aviso_previo(db, km=12.0, lat=-32.94, lon=-71.55)
    obs = observation("o-muy-cerca", -33.033, -71.55)   # ~1,9 km del lugar
    vincula(db, "o-muy-cerca")
    created = asyncio.run(alerts.evaluate(db, [obs], now=NOW))
    assert len(created) == 1
    assert created[0]["level"] == "urgente"
    assert created[0]["payload"]["observation"]["id"] == "inc-1:acerca"

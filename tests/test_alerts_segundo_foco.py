"""ALR-45: un segundo foco distinto dentro del radio del lugar avisa en el mismo ciclo.

`evaluate` ya no corta el recorrido tras el primer aviso del lugar: el ciclo marca como evaluadas
todas las detecciones nuevas y el segundo foco simultáneo quedaba sin aviso para siempre. Lo que
sí se mantiene es que el mismo fuego visto por dos sensores (FIRMS y GOES) no avise dos veces:
mismo incidente, o a menos de DEDUPE_KM de un aviso del ciclo con nivel igual o mayor.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from backend import alerts
from backend.db import Database
from tests.test_alerts_acercamiento import aviso_previo, incidente, observation, vincula

NOW = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)

# Lugar en (-33.05, -71.55), radio 20 km. Un grado de latitud son ~111,2 km.
FOCO_NORTE = (-33.00, -71.55)      # ~5,6 km al norte
FOCO_ORIENTE = (-33.05, -71.43)    # ~11,2 km al oriente; a ~12,5 km del foco norte


@pytest.fixture
def db(tmp_path):
    d = Database(tmp_path / "brasa.db")
    d.execute("INSERT INTO subscribers(id, created_at) VALUES ('s1','2026-01-01T00:00:00Z')")
    d.execute("INSERT INTO places(id, subscriber_id, name, kind, lat, lon, radius_km, created_at) "
              "VALUES ('casa','s1','Casa','casa',-33.05,-71.55,20,'2026-01-01T00:00:00Z')")
    return d


def goes(ident: str, lat: float, lon: float) -> dict:
    return {**observation(ident, lat, lon), "source": "goes", "sensor": "ABI", "satellite": "GOES-19",
            "resolution_m": 2000}


def test_dos_focos_de_incidentes_distintos_avisan_los_dos(db):
    incidente(db, "inc-a")
    incidente(db, "inc-b")
    vincula(db, "o-a", "inc-a")
    vincula(db, "o-b", "inc-b")
    obs = [observation("o-a", *FOCO_NORTE), observation("o-b", *FOCO_ORIENTE)]
    assert alerts.haversine_km(*FOCO_NORTE, *FOCO_ORIENTE) > alerts.DEDUPE_KM
    created = asyncio.run(alerts.evaluate(db, obs, now=NOW))
    assert [c["payload"]["observation"]["id"] for c in created] == ["o-a", "o-b"]
    assert db.one("SELECT COUNT(*) AS n FROM alerts WHERE place_id = 'casa'")["n"] == 2


def test_dos_focos_lejanos_sin_incidente_avisan_los_dos(db):
    obs = [observation("o-a", *FOCO_NORTE), observation("o-b", *FOCO_ORIENTE)]
    created = asyncio.run(alerts.evaluate(db, obs, now=NOW))
    assert {c["payload"]["observation"]["id"] for c in created} == {"o-a", "o-b"}


def test_el_mismo_fuego_en_firms_y_goes_a_menos_de_3_km_avisa_una_vez(db):
    firms = observation("o-firms", *FOCO_NORTE)
    satelite = goes("o-goes", FOCO_NORTE[0] - 0.01, FOCO_NORTE[1])   # ~1,1 km del de FIRMS
    assert alerts.haversine_km(FOCO_NORTE[0], FOCO_NORTE[1], satelite["lat"], satelite["lon"]) <= alerts.DEDUPE_KM
    created = asyncio.run(alerts.evaluate(db, [firms, satelite], now=NOW))
    assert len(created) == 1
    assert db.one("SELECT COUNT(*) AS n FROM alerts WHERE place_id = 'casa'")["n"] == 1


def test_el_mismo_incidente_visto_por_dos_sensores_avisa_una_vez_aunque_haya_mas_de_3_km(db):
    """GOES tiene píxeles de 2 km y su geolocalización puede caer lejos del punto de FIRMS."""
    incidente(db, "inc-1")
    vincula(db, "o-firms", "inc-1")
    vincula(db, "o-goes", "inc-1")
    firms = observation("o-firms", *FOCO_NORTE)
    satelite = goes("o-goes", FOCO_NORTE[0] + 0.04, FOCO_NORTE[1])   # ~4,4 km del de FIRMS
    assert alerts.haversine_km(FOCO_NORTE[0], FOCO_NORTE[1], satelite["lat"], satelite["lon"]) > alerts.DEDUPE_KM
    created = asyncio.run(alerts.evaluate(db, [firms, satelite], now=NOW))
    assert len(created) == 1
    assert created[0]["payload"]["observation"]["id"] == "o-firms"


def test_un_acercamiento_no_silencia_a_otro_incendio_ni_duplica_el_suyo(db):
    """El «:acerca» cuenta como aviso del ciclo para su incidente, pero otro incendio avisa."""
    incidente(db, "inc-1")
    incidente(db, "inc-2")
    aviso_previo(db, "inc-1", km=12.0, lat=-32.94, lon=-71.55)
    vincula(db, "o-cerca", "inc-1")
    vincula(db, "o-lejos-1", "inc-1")   # mismo incidente, otro frente: no vuelve a avisar
    vincula(db, "o-otro", "inc-2")
    obs = [observation("o-cerca", *FOCO_NORTE),
           observation("o-lejos-1", *FOCO_ORIENTE),
           observation("o-otro", FOCO_ORIENTE[0] - 0.02, FOCO_ORIENTE[1])]
    created = asyncio.run(alerts.evaluate(db, obs, now=NOW))
    ids = [c["payload"]["observation"]["id"] for c in created]
    assert ids == ["inc-1:acerca", "o-otro"]
    assert db.one("SELECT COUNT(*) AS n FROM alerts WHERE observation_id = 'o-lejos-1'")["n"] == 0

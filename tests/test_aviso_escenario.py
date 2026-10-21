"""FUEGO-24: el aviso lleva el rumbo del escenario, nunca velocidades ni hora de llegada.

La decisión delegada aprobada es la «frase prudente»: el push y Telegram dicen el rumbo
probable de avance («el viento de ahora lo empujaría hacia el este») y remiten a la ficha,
donde el escenario está con sus supuestos y su nota. Un número de propagación en un aviso
que llega de madrugada se leería como pronóstico oficial: el texto jamás lleva km/h.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from backend import alerts, incidents
from backend.db import Database
from tests.test_incidents import obs

CHILE = ZoneInfo("America/Santiago")

PLACE = {"id": "p1", "name": "Casa", "lat": -33.5, "lon": -70.8, "radius_km": 10, "comuna_code": 13101, "older_adult": 0}

OBS = {
    "id": "sat-1",
    "source": "firms",
    "sensor": "VIIRS",
    "satellite": "N20",
    "resolution_m": 375,
    "lat": -33.56,
    "lon": -70.8,
    "frp_mw": 20.0,
    "confidence": "alta",
    "observed_at": "2026-01-20T17:00:00Z",
}

INC = {
    "id": "inc-1",
    "status": "posible",
    "n_obs": 3,
    "first_seen_at": "2026-01-20T15:00:00Z",
    "last_seen_at": "2026-01-20T17:00:00Z",
    "sensors": "VIIRS",
    "comuna_code": 13101,
}

FIRE = {
    "id": "11",
    "name": "El Belloto",
    "status": "en_combate",
    "status_raw": "En combate",
    "lat": -33.56,
    "lon": -70.8,
    "started_at": "2026-01-20T16:00:00Z",
    "area_ha": 12.5,
}

SPREAD = {
    "kind": "escenario_estimado",
    "ffmc": 88.0,
    "wind_kmh": 25.0,
    "wind_deg": 250.0,
    "slope_deg": None,
    "aspect_deg": None,
    "effective_wind_kmh": 25.0,
    "isi": 4.5,
    "speed_m_min": 20.0,
    "speed_kmh": 1.2,
    "direction_deg": 70.0,
    "fuel": "pasto en pie seco (tipo O-1b del FBP canadiense)",
    "reference": "FCFDG (1992) ST-X-3",
    "assumptions": [],
    "wind_at": "2026-01-20T18:00Z",
    "ffmc_date": "2026-01-20",
    "note": "Escenario estimado con las condiciones de ahora: no es una predicción ni el perímetro del incendio.",
}


def _frase(body: str) -> str | None:
    """La oración del aviso que habla del rumbo probable (o None si no va)."""
    return next((s for s in body.split(". ") if "empujaría" in s), None)


def test_aviso_nombra_el_rumbo_del_escenario_sin_numeros():
    """Con escenario y rumbo conocido el aviso dice «hacia el este» y remite a la ficha."""
    payload = alerts.compose(PLACE, OBS, 4.4, 180, False, "aviso", None, 0, INC, SPREAD)
    frase = _frase(payload["body"])
    assert frase is not None, payload["body"]
    assert "empujaría hacia el este" in frase
    assert "escenario estimado" in frase and "ficha" in frase
    # La frase jamás lleva cifras de avance: sin km/h, sin dígitos.
    assert "km/h" not in frase
    assert not any(ch.isdigit() for ch in frase)


def test_aviso_sin_rumbo_o_sin_escenario_no_lo_menciona():
    """Sin dirección del escenario no se inventa un rumbo; sin escenario no se habla de él."""
    sin_rumbo = alerts.compose(PLACE, OBS, 4.4, 180, False, "aviso", None, 0, INC, {**SPREAD, "direction_deg": None})
    assert "empujaría" not in sin_rumbo["body"]
    sin_escenario = alerts.compose(PLACE, OBS, 4.4, 180, False, "aviso", None, 0, INC, None)
    assert "empujaría" not in sin_escenario["body"]
    assert "escenario estimado" not in sin_escenario["body"]


def test_aviso_oficial_lleva_el_rumbo_sin_atribuirlo_a_satelites():
    """Un incendio de CONAF también lleva el rumbo, pero sin «los satélites lo ven activo»."""
    payload = alerts.compose_official(PLACE, FIRE, 4.4, 180, "aviso", spread=SPREAD)
    frase = _frase(payload["body"])
    assert frase is not None, payload["body"]
    assert "empujaría hacia el este" in frase
    assert "satélites" not in frase


def _semilla_comuna(db: Database, now: datetime) -> None:
    """Deja en `work` el clima que la ingesta guarda para la comuna (FFMC + pronóstico)."""
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    today = now.astimezone(CHILE).date().isoformat()
    db.execute(
        "INSERT INTO fwi_daily(comuna_code, date, ffmc, dmc, dc, isi, bui, fwi, level, computed_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (13101, today, 88.0, 20.0, 100.0, 5.0, 50.0, 15.0, "moderado", stamp),
    )
    # Viento del oeste-suroeste (250° desde): el escenario empuja hacia ~70°, «este».
    db.execute(
        "INSERT INTO risk_hourly(comuna_code, computed_at, payload) VALUES (?,?,?)",
        (13101, stamp, json.dumps([{"time": (now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%MZ"), "wind": 25.0, "dir": 250.0}])),
    )


def test_evaluate_arma_el_escenario_desde_el_clima_de_la_comuna(tmp_path):
    """De punta a punta: el aviso satelital arma el rumbo con fwi_daily + risk_hourly."""
    db = Database(tmp_path / "brasa.db")
    now = datetime.now(timezone.utc).replace(microsecond=0)
    db.execute("INSERT INTO subscribers(id, created_at) VALUES ('s1','2026-01-01T00:00:00Z')")
    db.execute(
        "INSERT INTO places(id, subscriber_id, name, kind, lat, lon, radius_km, created_at) "
        "VALUES ('p1','s1','Casa','casa',-33.5,-70.8,10,'2026-01-01T00:00:00Z')"
    )
    o = obs(db, "fuego-24", -33.55, -70.8, when=now)
    incidents.update(db, [o], now)
    _semilla_comuna(db, now)
    created = asyncio.run(alerts.evaluate(db, [o], now=now))
    assert len(created) == 1
    frase = _frase(created[0]["payload"]["body"])
    assert frase is not None and "empujaría hacia el este" in frase


def test_evaluate_avisa_sin_escenario_cuando_no_hay_clima(tmp_path):
    """Sin datos de la comuna el aviso sale igual, solo sin la frase de escenario."""
    db = Database(tmp_path / "brasa.db")
    now = datetime.now(timezone.utc).replace(microsecond=0)
    db.execute("INSERT INTO subscribers(id, created_at) VALUES ('s1','2026-01-01T00:00:00Z')")
    db.execute(
        "INSERT INTO places(id, subscriber_id, name, kind, lat, lon, radius_km, created_at) "
        "VALUES ('p1','s1','Casa','casa',-33.5,-70.8,10,'2026-01-01T00:00:00Z')"
    )
    o = obs(db, "fuego-24", -33.55, -70.8, when=now)
    incidents.update(db, [o], now)
    created = asyncio.run(alerts.evaluate(db, [o], now=now))
    assert len(created) == 1
    assert "empujaría" not in created[0]["payload"]["body"]

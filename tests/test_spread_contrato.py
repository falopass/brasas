"""Contrato del escenario estimado de propagación en `GET /api/incidents/{id}` (FUEGO-02).

La ficha puede mostrar un número, pero nunca sin decir que es una estimación, con qué datos se
calculó y de qué fuente sale. Estos tests fallan si un refactor de `_incident_spread` pierde el
rótulo, los supuestos o la fuente, o si el escenario aparece sin los datos de la comuna.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from backend import incidents
from tests.test_incidents import obs

COMUNA = 13101
OTRA_COMUNA = 13102


def _spread(
    make_client, *, fwi_comuna: int | None = COMUNA, risk_comuna: int | None = COMUNA, wind_dir: float | None = 250.0
) -> dict | None:
    """Arma un incidente con comuna y siembra el clima guardado como lo hacen los tests de riesgo."""
    with make_client() as client:
        db = client.app.state.services.db
        now = datetime.now(timezone.utc).replace(microsecond=0)
        [incident] = incidents.update(db, [obs(db, "spread-contract", -33.5, -70.8, when=now)], now)
        stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        today = now.astimezone(ZoneInfo("America/Santiago")).date().isoformat()
        if fwi_comuna is not None:
            db.execute(
                "INSERT INTO fwi_daily(comuna_code, date, ffmc, dmc, dc, isi, bui, fwi, level, computed_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (fwi_comuna, today, 88.0, 20.0, 100.0, 5.0, 50.0, 15.0, "moderado", stamp),
            )
        if risk_comuna is not None:
            hour = (now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%MZ")
            payload = [{"time": hour, "wind": 25.0, "dir": wind_dir}]
            db.execute(
                "INSERT INTO risk_hourly(comuna_code, computed_at, payload) VALUES (?,?,?)",
                (risk_comuna, stamp, json.dumps(payload)),
            )
        return client.get(f"/api/incidents/{incident['id']}").json()["spread"]


def test_spread_declares_it_is_an_estimate_with_its_source_and_assumptions(make_client):
    """El número nunca viaja solo: lleva su rótulo de estimación, la fuente del cálculo
    y los supuestos (sin DEM la pendiente queda fuera y eso se declara)."""
    spread = _spread(make_client)
    assert spread is not None
    assert spread["kind"] == "escenario_estimado"
    note = spread.get("note") or ""
    assert "no es una predicción ni el perímetro" in note, note
    assert spread.get("fuel") and spread.get("reference")
    assert "FCFDG" in spread["reference"]
    assumptions = spread.get("assumptions") or []
    assert assumptions
    assert spread["slope_deg"] is None
    assert any("terreno plano" in a.lower() for a in assumptions)
    # FUEGO-27: el supuesto lo tiene que entender un vecino, no solo un técnico.
    assert any("ladera" in a and "subir más rápido" in a for a in assumptions)
    assert any("centro de la comuna" in a for a in assumptions)


def test_spread_numbers_stay_inside_their_declared_ranges(make_client):
    """Con viento del oeste, el rumbo de avance es conocido (no None) y velocidad e ISI son positivos."""
    spread = _spread(make_client)
    assert spread is not None
    direction = spread["direction_deg"]
    assert direction is not None
    assert 0.0 <= direction < 360.0
    assert spread["speed_kmh"] > 0
    assert spread["speed_m_min"] > 0
    assert spread["isi"] > 0


def test_spread_keeps_the_warning_without_wind_direction(make_client):
    """Sin dirección de viento el rumbo es None, pero la advertencia y el supuesto siguen ahí."""
    spread = _spread(make_client, wind_dir=None)
    assert spread is not None
    assert spread["direction_deg"] is None
    assert "no es una predicción" in (spread.get("note") or "")
    assert any("dirección de viento" in a for a in spread["assumptions"])


@pytest.mark.parametrize("fwi_comuna,risk_comuna", [(OTRA_COMUNA, COMUNA), (COMUNA, OTRA_COMUNA)])
def test_spread_is_none_without_fwi_or_wind_for_the_comuna(make_client, fwi_comuna, risk_comuna):
    """Con datos de otra comuna no se inventa el escenario de esta."""
    assert _spread(make_client, fwi_comuna=fwi_comuna, risk_comuna=risk_comuna) is None

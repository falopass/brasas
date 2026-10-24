"""AGUA-07: un aviso DMC de lluvia intensa o tormenta solo avisa en comunas con
cicatriz de la temporada (≥ 10 ha en 90 días, `season_scars`); dedupe por aviso
DMC + lugar, con nivel «aviso» — pasa por los topes y el silencio nocturno ya
existentes en la entrega.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest

from backend import alerts as alerts_mod
from backend.db import Database
from tests.test_scars import seed_incident

NOW = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)
ONSET = (NOW - timedelta(hours=1)).isoformat()
EXPIRES = (NOW + timedelta(hours=6)).isoformat()
TALCA = 7101  # el incidente de `seed_incident` cae en Talca por defecto
VINA = 5109


def _db(tmp_path, comuna: int | None = TALCA) -> Database:
    db = Database(tmp_path / "brasa.db")
    db.execute("INSERT INTO subscribers(id, created_at) VALUES ('s1','2026-10-01T00:00:00Z')")
    db.execute(
        "INSERT INTO places(id, subscriber_id, name, kind, lat, lon, radius_km, comuna_code, older_adult, created_at) "
        "VALUES ('p1','s1','Parcela','parcela',-35.42,-71.60,10,?,0,'2026-10-01T00:00:00Z')",
        (comuna,),
    )
    return db


def _row(kind: str = "lluvia", comunas=(TALCA,), **kw) -> dict:
    """Una fila de `dmc_alerts` como la deja `ingest_dmc` (areas y comunas en JSON)."""
    return {
        "id": "urn:oid:2.49.0.0.152.0.2026.10.18.9", "kind": kind,
        "event": "Precipitaciones", "headline": "Lluvia intensa en la región del Maule",
        "severity": "Moderate", "urgency": "Expected", "onset": ONSET, "expires": EXPIRES,
        "web": "https://archivos.meteochile.gob.cl/portaldmc/AAA/doc/evento.html",
        "areas": "[]", "comunas": json.dumps(list(comunas)), "fetched_at": NOW.isoformat(), **kw,
    }


@pytest.mark.parametrize("kind", ["lluvia", "tormenta"])
def test_aviso_de_lluvia_sobre_cicatriz_avisa_una_sola_vez(tmp_path, kind):
    """Con cicatriz de la temporada en la comuna del lugar: un «aviso» por aviso DMC + lugar."""
    db = _db(tmp_path)
    seed_incident(db, "inc-1", days_ago=10)  # cicatriz reciente en Talca (≥ 10 ha)
    created = asyncio.run(alerts_mod.evaluate_dmc(db, [_row(kind=kind)], now=NOW))
    assert len(created) == 1 and created[0]["level"] == "aviso"
    payload = created[0]["payload"]
    assert "Aviso de lluvia de la DMC sobre una zona quemada: aléjate de quebradas y laderas quemadas" in payload["body"]
    assert "SENAPRED" in payload["body"] and payload["footer"] == alerts_mod.OFFICIAL_FOOTER
    assert payload["dmc"]["kind"] == kind
    # Nivel «aviso»: el silencio nocturno y los topes anti-fatiga aplican como a cualquier otro.
    assert alerts_mod.aplazable(payload)
    row = db.one("SELECT * FROM alerts")
    assert row["observation_id"] == f"dmc:{_row()['id']}" and row["level"] == "aviso"
    # La misma pasada (la tabla DMC se reescribe en cada ingesta) no avisa dos veces.
    assert asyncio.run(alerts_mod.evaluate_dmc(db, [_row(kind=kind)], now=NOW)) == []
    assert db.one("SELECT COUNT(*) AS n FROM alerts")["n"] == 1


def test_aviso_de_lluvia_sin_cicatriz_en_la_comuna_no_avisa(tmp_path):
    """Sin suelo quemado reciente en la comuna del lugar, el aviso de lluvia es ruido."""
    db = _db(tmp_path)
    assert asyncio.run(alerts_mod.evaluate_dmc(db, [_row()], now=NOW)) == []
    assert db.one("SELECT id FROM alerts") is None


def test_cicatriz_en_otra_comuna_o_fuera_de_los_90_dias_no_avisa(tmp_path):
    """La cicatriz que cuenta es la de la comuna del lugar, dentro de la ventana."""
    db = _db(tmp_path)
    seed_incident(db, "inc-otra", comuna_code=VINA, lat=-33.02, lon=-71.52, days_ago=10)
    seed_incident(db, "inc-vieja", days_ago=100)
    assert asyncio.run(alerts_mod.evaluate_dmc(db, [_row()], now=NOW)) == []
    assert db.one("SELECT id FROM alerts") is None


def test_un_aviso_de_viento_no_usa_la_rama_de_la_cicatriz(tmp_path):
    """Viento y calor siguen el camino de siempre: avisan sin necesitar suelo quemado."""
    db = _db(tmp_path)
    created = asyncio.run(alerts_mod.evaluate_dmc(db, [_row(kind="viento", event="Viento Fuerte")], now=NOW))
    assert len(created) == 1 and "zona quemada" not in created[0]["payload"]["body"]

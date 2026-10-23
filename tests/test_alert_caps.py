"""ALR-20: topes anti-fatiga (INV-09) con reloj y bandera inyectados. Los frenados quedan
marcados en la fila («tope:<motivo>») y no se pierden."""
import json
from datetime import datetime, timezone

import pytest

from backend.alerts import caps_exceeded
from backend.db import Database

NOW = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def db(tmp_path):
    # Database(path) deriva work_path = <mismo directorio>/work.db: si el path principal se
    # llamara «work.db», el ATTACH apuntaría al mismo archivo y sqlite diría «database is locked».
    return Database(tmp_path / "brasa.db")


_seq = iter(range(1000))


def _alerta(db, place="casa", level="aviso", inc=None, entregada=None):
    payload = {"level": level, "place": {"id": place}, "incident": {"id": inc} if inc else None}
    return db.insert(
        "INSERT INTO alerts(place_id, observation_id, level, distance_km, bearing_deg, upwind, lat, lon, "
        "observed_at, created_at, payload, delivered, delivered_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (place, f"obs:{next(_seq)}", level, 1.0, 0, 0, -35.0, -71.0, "2026-10-22T11:00:00Z",
         "2026-10-22T11:30:00Z", json.dumps(payload), '["push"]' if entregada else None,
         "2026-10-22T11:35:00Z" if entregada else None))


def _nuevo(place="casa", level="aviso", inc=None, obs="obs:9"):
    return {"id": None, "place_id": place, "level": level, "observation_id": obs, "incident_id": inc}


def test_sin_topes_no_frena(db):
    assert caps_exceeded(db, _nuevo(), NOW) is None


def test_cuarto_push_de_la_semana_no_sale(db):
    for _ in range(3):
        _alerta(db, entregada=True)
    assert caps_exceeded(db, _nuevo(), NOW) == "aviso_7d"


def test_escalada_de_estado_siempre_sale(db):
    for _ in range(3):
        _alerta(db, entregada=True)
    assert caps_exceeded(db, _nuevo(obs="conaf:1:estado"), NOW) is None


def test_urgente_uno_por_incidente_y_por_dia(db):
    _alerta(db, level="urgente", inc="i1", entregada=True)
    assert caps_exceeded(db, _nuevo(level="urgente", inc="i1"), NOW) == "urgente_incidente"
    assert caps_exceeded(db, _nuevo(level="urgente", inc="i2"), NOW) == "urgente_24h"


def test_apagada_por_bandera(db, monkeypatch):
    for _ in range(3):
        _alerta(db, entregada=True)
    monkeypatch.setenv("AVISO_TOPES", "0")
    assert caps_exceeded(db, _nuevo(), NOW) is None


def test_aplazada_no_cuenta_como_entregada(db):
    db.execute("INSERT INTO alerts(place_id, observation_id, level, payload, created_at, delivered, "
               "delivered_at) VALUES ('casa','obs:1','aviso','{}','2026-10-22T04:00:00Z','[\"silencio\"]',NULL)")
    assert caps_exceeded(db, _nuevo(), NOW) is None


def test_tope_no_se_autoalimenta_con_frenadas(db):
    for _ in range(3):
        _alerta(db, entregada=True)
    assert caps_exceeded(db, _nuevo(), NOW) == "aviso_7d"
    # la fila frenada queda marcada «tope:aviso_7d» y no empuja el conteo más arriba
    db.execute("INSERT INTO alerts(place_id, observation_id, level, payload, created_at, delivered, delivered_at) "
               "VALUES ('casa','obs:f1','aviso','{}','2026-10-22T11:40:00Z',?,'2026-10-22T11:40:00Z')", ('["tope:aviso_7d"]',))
    assert caps_exceeded(db, _nuevo(), NOW) == "aviso_7d"  # sigue en tope, no se desborda


def test_urgente_no_lo_frena_aviso_7d(db):
    for _ in range(3):
        _alerta(db, entregada=True)  # 3 avisos entregados en la semana
    assert caps_exceeded(db, _nuevo(level="urgente", inc="i9"), NOW) is None


def test_canal_vacio_no_cuenta_como_entregada(db):
    db.execute("INSERT INTO alerts(place_id, observation_id, level, payload, created_at, delivered, delivered_at) "
               "VALUES ('casa','obs:v1','aviso','{}','2026-10-22T11:40:00Z','[]','2026-10-22T11:40:00Z')")
    for _ in range(3):
        _alerta(db, entregada=True)
    assert caps_exceeded(db, _nuevo(), NOW) == "aviso_7d"
    db.execute("DELETE FROM alerts WHERE delivered = '[]'")
    # quitar la vacía no cambia el veredicto: nunca contó
    assert caps_exceeded(db, _nuevo(), NOW) == "aviso_7d"

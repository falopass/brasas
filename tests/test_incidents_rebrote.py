"""FUEGO-23: un rescoldo que vuelve a dar calor reabre el mismo incidente.

Un incendio declarado «sin calor nuevo» hace menos de REOPEN_HOURS (72 h) es un rebrote del
mismo fuego —la regla de oro es un fuego = una ficha—, no un incendio distinto al lado del
anterior. Pasada esa ventana ya es otro incendio, y el que CONAF cerró no revive por calor
satelital: `official_ref` manda sobre la evidencia.
"""

from datetime import timedelta

from backend import incidents
from backend.db import Database
from tests.test_incidents import T0, obs

OPEN = set(incidents.OPEN_STATES)


def _posible_extinguido(db: Database) -> str:
    """Incidente «posible» que expira a las 25 h: devuelve su id ya en «extinguido»."""
    [inc] = incidents.update(db, [obs(db, "a", -33.5, -70.8)], T0)
    [again] = incidents.update(db, [obs(db, "b", -33.5, -70.8, minutes=40)], T0 + timedelta(minutes=45))
    assert again["id"] == inc["id"] and again["status"] == "posible"
    assert incidents.expire(db, T0 + timedelta(hours=25)) == 1
    assert db.one("SELECT status FROM incidents WHERE id = ?", (inc["id"],))["status"] == "extinguido"
    return inc["id"]


def test_rebrote_dentro_de_72h_reabre_el_mismo_incidente(tmp_path):
    db = Database(tmp_path / "brasa.db")
    inc_id = _posible_extinguido(db)
    when = T0 + timedelta(hours=26)
    [again] = incidents.update(db, [obs(db, "c", -33.5, -70.8, when=when)], when)
    assert again["id"] == inc_id
    assert again["n_obs"] == 3 and again["status"] in OPEN
    assert db.one("SELECT COUNT(*) AS n FROM incidents")["n"] == 1


def test_extinguido_hace_20_dias_es_otro_incendio(tmp_path):
    db = Database(tmp_path / "brasa.db")
    inc_id = _posible_extinguido(db)
    when = T0 + timedelta(days=20)
    [new] = incidents.update(db, [obs(db, "c", -33.5, -70.8, when=when)], when)
    assert new["id"] != inc_id and new["n_obs"] == 1 and new["status"] == "anomalia"
    assert db.one("SELECT COUNT(*) AS n FROM incidents")["n"] == 2


def test_incendio_oficial_extinguido_no_revive_por_calor(tmp_path):
    db = Database(tmp_path / "brasa.db")
    inc_id = _posible_extinguido(db)
    db.execute("UPDATE incidents SET official_ref = 'conaf-2027-0001' WHERE id = ?", (inc_id,))
    when = T0 + timedelta(hours=26)
    [again] = incidents.update(db, [obs(db, "c", -33.5, -70.8, when=when)], when)
    assert again["id"] == inc_id and again["status"] == "extinguido"
    assert db.one("SELECT COUNT(*) AS n FROM incidents")["n"] == 1


def test_expire_no_vuelve_a_cerrar_el_reabierto_en_el_mismo_ciclo(tmp_path):
    db = Database(tmp_path / "brasa.db")
    inc_id = _posible_extinguido(db)
    when = T0 + timedelta(hours=26)
    incidents.update(db, [obs(db, "c", -33.5, -70.8, when=when)], when)
    # El ciclo corre expire justo después de agrupar: el reabierto quedó visto ahora y no expira.
    assert incidents.expire(db, when) == 0
    assert db.one("SELECT status FROM incidents WHERE id = ?", (inc_id,))["status"] in OPEN

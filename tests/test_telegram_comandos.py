"""ALR-21: el bot administra los avisos desde el propio Telegram — /diario, /radio,
/borrar en dos pasos y /riesgo aunque el nivel venga fuera de la tabla. Sin red real:
handle_update devuelve el texto de respuesta."""

from __future__ import annotations

from datetime import datetime

import pytest

from backend.db import Database
from backend.notify import telegram


@pytest.fixture
def db(tmp_path) -> Database:
    d = Database(tmp_path / "brasa.db")
    d.execute("INSERT INTO subscribers(id, created_at, telegram_chat_id) VALUES ('s1','2026-10-01T00:00:00Z','7')")
    return d


def send(db: Database, text: str) -> str:
    reply = telegram.handle_update(db, {"message": {"chat": {"id": 7}, "text": text}})
    assert reply is not None
    return reply


def place(db: Database, pid: str, name: str, daily_brief: int = 0, radius_km: float = 10, comuna_code: int | None = 5109) -> None:
    db.execute(
        "INSERT INTO places(id, subscriber_id, name, kind, lat, lon, radius_km, comuna_code, "
        "daily_brief, created_at) VALUES (?, 's1', ?, 'casa', -33.02, -71.55, ?, ?, ?, '2026-10-01T00:00:00Z')",
        (pid, name, radius_km, comuna_code, daily_brief),
    )


def test_diario_on_y_off_escriben_la_columna_y_responden(db):
    place(db, "p1", "Casa")
    place(db, "p2", "Pega")
    assert "2 de 2" in send(db, "/diario on")
    assert db.one("SELECT COUNT(*) AS n FROM places WHERE daily_brief = 1")["n"] == 2
    assert "0 de 2" in send(db, "/diario off")
    assert db.one("SELECT COUNT(*) AS n FROM places WHERE daily_brief = 1")["n"] == 0


def test_diario_sin_argumento_informa_sin_tocar_la_base(db):
    place(db, "p1", "Casa", daily_brief=1)
    place(db, "p2", "Pega")
    assert "1 de 2" in send(db, "/diario")
    assert db.one("SELECT COUNT(*) AS n FROM places WHERE daily_brief = 1")["n"] == 1


def test_radio_fija_el_radio_en_todos_los_lugares(db):
    place(db, "p1", "Casa")
    place(db, "p2", "Pega")
    assert "25" in send(db, "/radio 25")
    rows = db.query("SELECT radius_km FROM places ORDER BY id")
    assert [r["radius_km"] for r in rows] == [25, 25]
    assert "25" in send(db, "/radio")


@pytest.mark.parametrize("texto", ["/radio abc", "/radio 4", "/radio 400"])
def test_radio_fuera_de_rango_o_sin_numero_no_toca_la_base(db, texto):
    place(db, "p1", "Casa", radius_km=30)
    assert "/radio" in send(db, texto)
    assert db.one("SELECT radius_km FROM places WHERE id = 'p1'")["radius_km"] == 30


def test_borrar_pide_confirmar_y_solo_confirmar_borra(db):
    place(db, "p1", "Casa")
    place(db, "p2", "Pega")
    reply = send(db, "/borrar")
    assert "2" in reply and "confirmar" in reply
    assert db.one("SELECT COUNT(*) AS n FROM places")["n"] == 2
    send(db, "/borrar ya mismo")  # cualquier otro texto cancela
    assert db.one("SELECT COUNT(*) AS n FROM places")["n"] == 2
    send(db, "/borrar confirmar")
    assert db.one("SELECT COUNT(*) AS n FROM places")["n"] == 0


def test_riesgo_con_nivel_fuera_de_tabla_muestra_el_nivel(db):
    place(db, "p1", "Casa", comuna_code=5109)
    today = datetime.now(telegram.CHILE_TZ).date().isoformat()
    db.execute(
        "INSERT INTO risk_daily(comuna_code, date, level, score, hours_3of3, hours_2of3, "
        "tmax, rhmin, windmax, computed_at) "
        "VALUES (5109, ?, 'critico', 9, 5, 4, 34, 12, 45, '2026-10-19T01:00:00Z')",
        (today,),
    )
    reply = send(db, "/riesgo")
    assert "CRITICO" in reply and "⚪" in reply


def test_lugares_marca_cuales_tienen_el_aviso_diario(db):
    place(db, "p1", "Casa", daily_brief=1)
    place(db, "p2", "Pega")
    lines = send(db, "/lugares").splitlines()
    [casa] = [line for line in lines if "Casa" in line]
    [pega] = [line for line in lines if "Pega" in line]
    assert "radio 10 km" in casa and "aviso diario" in casa
    assert "aviso diario" not in pega

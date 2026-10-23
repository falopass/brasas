"""ALR-21: el bot administra los avisos desde el propio Telegram — /diario, /radio,
/borrar en dos pasos y /riesgo aunque el nivel venga fuera de la tabla. Sin red real:
handle_update devuelve el texto de respuesta."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

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


def place(db: Database, pid: str, name: str, daily_brief: int = 0, radius_km: float = 10, comuna_code: int | None = 5109,
          lat: float = -33.02, lon: float = -71.55) -> None:
    db.execute(
        "INSERT INTO places(id, subscriber_id, name, kind, lat, lon, radius_km, comuna_code, "
        "daily_brief, created_at) VALUES (?, 's1', ?, 'casa', ?, ?, ?, ?, ?, '2026-10-01T00:00:00Z')",
        (pid, name, lat, lon, radius_km, comuna_code, daily_brief),
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


# --- ALR-30: /focos lista los incidentes vigentes cerca de tus lugares ---
#
# No son detecciones sueltas: cada línea es un incidente con rumbo, estado en
# palabras (INCIDENT_PHRASE de alerts.py) y antigüedad del dato; un foco visto
# desde dos lugares se cuenta una vez, en el más cercano.


def incident(db: Database, iid: str, lat: float | None = None, lon: float | None = None,
             hours_ago: float = 0.5, span_h: float = 3.0, status: str = "posible", n_obs: int = 6,
             fixed_source: int = 0, fixed_reason: str | None = None) -> None:
    """Incidente sobre el lugar de prueba (por omisión ~4 km al noroeste de «Casa»)."""
    seen = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    first = seen - timedelta(hours=span_h)
    at = seen.strftime("%Y-%m-%dT%H:%M:%SZ")
    if lat is None and lon is None:
        lat, lon = -33.02 + 0.0257, -71.55 - 0.0303  # ~4 km al noroeste del lugar
    # La coordenada omitida cae sobre el lugar: con solo `lat` el incidente queda
    # al norte o al sur de «Casa», en el mismo meridiano.
    lat = -33.02 if lat is None else lat
    lon = -71.55 if lon is None else lon
    db.execute(
        "INSERT INTO incidents(id, status, status_changed_at, first_seen_at, last_seen_at, "
        "lat, lon, min_lat, max_lat, min_lon, max_lon, n_obs, n_reliable, sensors, comuna_code, "
        "fixed_source, fixed_reason, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            iid, status, first.strftime("%Y-%m-%dT%H:%M:%SZ"), first.strftime("%Y-%m-%dT%H:%M:%SZ"), at,
            lat, lon, lat, lat, lon, lon, n_obs, n_obs, "VIIRS", 5109, fixed_source, fixed_reason, at,
        ),
    )


def test_focos_muestra_el_incidente_cercano_con_estado_rumbo_y_antiguedad(db):
    place(db, "p1", "Casa")
    incident(db, "i1", hours_ago=25 / 60, status="posible", n_obs=6, span_h=3)
    reply = send(db, "/focos")
    assert "«Casa»" in reply and "4,0 km" in reply and "noroeste" in reply
    assert "posible incendio" in reply and "6 detecciones" in reply
    assert "hace 25 min" in reply
    assert "24 h" in reply
    assert telegram.FOCOS_FOOTER in reply


def test_focos_no_muestra_el_incidente_fuera_del_radio(db):
    place(db, "p1", "Casa")
    incident(db, "ilejos", lat=-33.02 + 0.45)  # ~50 km al norte
    reply = send(db, "/focos")
    assert "No hay focos de calor vigentes a menos de 10 km" in reply
    assert "posible incendio" not in reply


def test_focos_sin_incidentes_vigentes_lo_dice_en_vez_de_callar(db):
    place(db, "p1", "Casa")
    reply = send(db, "/focos")
    assert "No hay focos de calor vigentes a menos de 10 km" in reply
    assert "Todavía no se ha visto calor" in reply
    assert telegram.FOCOS_FOOTER in reply


def test_focos_ventana_24h_y_la_deteccion_vieja_queda_como_ultima(db):
    place(db, "p1", "Casa")
    incident(db, "iviejo", hours_ago=30)
    reply = send(db, "/focos")
    assert "No hay focos" in reply and "última detección de la zona es de hace 30 h" in reply
    reply = send(db, "/focos 48h")
    assert "posible incendio" in reply and "48 h" in reply


def test_focos_fuente_fija_se_marca_con_su_razon(db):
    place(db, "p1", "Casa")
    incident(db, "ifija", fixed_source=1, fixed_reason="volcán activo conocido (Volcán Villarrica)")
    reply = send(db, "/focos")
    assert "fuente de calor fija" in reply and "Volcán Villarrica" in reply
    assert "posible incendio" not in reply


def test_focos_mismo_incidente_en_dos_lugares_queda_en_el_mas_cercano(db):
    place(db, "p1", "Casa")
    place(db, "p2", "Pega", lat=-33.06)  # ~4,4 km al sur de Casa
    incident(db, "compartido", lat=-33.0)  # ~2,2 km al norte de Casa, ~6,6 de Pega
    reply = send(db, "/focos")
    assert reply.count("«") == 1 and "«Casa»" in reply


def test_focos_tres_por_lugar_y_cinco_en_total(db):
    place(db, "p1", "Casa")
    place(db, "p2", "Pega", lat=-34.0, lon=-71.0)
    for i in range(5):  # más de 3 cerca de Casa: el lugar solo aporta 3
        incident(db, f"c{i}", lat=-33.02 + 0.02 + i * 0.01)
    for i in range(4):  # 4 cerca de Pega: aporta 3
        incident(db, f"p{i}", lat=-34.0 + 0.02 + i * 0.01, lon=-71.0)
    reply = send(db, "/focos")
    assert reply.count("«") == 5
    assert "y 1 foco más" in reply
    assert len(reply) <= 4096


def test_focos_sin_lugares_responde_igual_que_riesgo(db):
    assert send(db, "/focos") == send(db, "/riesgo")


@pytest.mark.parametrize("texto", ["/focos 0h", "/focos 73h", "/focos muchas"])
def test_focos_fuera_de_rango_explica_el_uso(db, texto):
    place(db, "p1", "Casa")
    reply = send(db, texto)
    assert "1 a 72" in reply


def test_focos_si_la_base_falla_lo_dice_y_no_finge_calma(db, monkeypatch):
    place(db, "p1", "Casa")

    def caida(*args, **kwargs):
        raise RuntimeError("base caída")

    monkeypatch.setattr(db, "query", caida)
    reply = send(db, "/focos")
    assert "No pude consultar" in reply
    assert "No hay focos" not in reply


def test_la_ayuda_lista_el_comando_focos():
    assert "/focos" in telegram.HELP

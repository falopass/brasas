"""IDEA-13/14, CAL-02, ALR-23: /calendar/boton-rojo/{code}.ics y /calendar/lugar/{code}.ics
entregan los días peligrosos de una comuna (Botón Rojo de CONAF, avisos DMC vigentes y, en el
del lugar, el riesgo alto/extremo estimado por BRASA) en .ics RFC 5545 para suscribir."""

import json
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from backend.routes import calendar as calendar_mod
from backend.settings import ROOT

CHILE_TZ = ZoneInfo("America/Santiago")
COMUNA = 5109  # Viña del Mar


def _br(db, code, day, hours=4, area_ha=1200.5):
    db.execute(
        "INSERT INTO boton_rojo(comuna_code, date, hours, area_ha, proportion, fetched_at) VALUES (?,?,?,?,?,?)",
        (code, day.isoformat(), hours, area_ha, 0.1, "2026-01-10T00:00:00Z"),
    )


def _risk(db, code, day, level="alto"):
    db.execute(
        "INSERT INTO risk_daily(comuna_code, date, level, score, hours_3of3, hours_2of3, "
        "level_combined, fwi, fwi_level, computed_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (code, day.isoformat(), level, 80, 2, 4, level, 25.5, "alto", datetime.now(timezone.utc).isoformat()),
    )


def _dmc(db, code, alert_id="aviso-1", onset=None, expires=None, headline="Viento moderado en la comuna"):
    """Una fila de `dmc_alerts` vigente por defecto, como la deja `ingest_dmc`."""
    now = datetime.now(timezone.utc)
    db.execute(
        "INSERT INTO dmc_alerts(id, kind, event, headline, severity, urgency, onset, expires, web, areas, comunas, fetched_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            alert_id, "viento", "Viento", headline, "Moderate", "Expected",
            (onset if onset is not None else now - timedelta(hours=1)).isoformat(),
            (expires if expires is not None else now + timedelta(hours=6)).isoformat(),
            "https://archivos.meteochile.gob.cl/portaldmc/AAA/doc/evento.html", "[]", json.dumps([code]), now.isoformat(),
        ),
    )


def _future(days_ahead):
    return datetime.now(CHILE_TZ).date() + timedelta(days=days_ahead)


def _unfold(body):
    """Deshace el plegado RFC 5545 (CRLF + espacio) para buscar texto completo."""
    return body.replace("\r\n ", "")


def test_unknown_comuna_returns_404(make_client):
    with make_client(GOES_ENABLED="0") as client:
        assert client.get("/calendar/boton-rojo/99999.ics").status_code == 404
        assert client.get("/calendar/boton-rojo/no-es-codigo.ics").status_code == 404


def test_each_boton_rojo_day_is_an_all_day_event(make_client):
    with make_client(GOES_ENABLED="0") as client:
        db = client.app.state.services.db
        _br(db, COMUNA, _future(1))
        _br(db, COMUNA, _future(2))
        _br(db, COMUNA, _future(-1))  # un día pasado no entra al calendario
        response = client.get(f"/calendar/boton-rojo/{COMUNA}.ics")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/calendar")
        body = response.text
        assert body.count("BEGIN:VEVENT") == 2 and body.count("DTSTART;VALUE=DATE:") == 2
        d1, d2 = _future(1), _future(2)
        assert f"UID:brasa-botonrojo-{COMUNA}-{d1:%Y%m%d}@brasa-chile" in body
        assert f"DTSTART;VALUE=DATE:{d1:%Y%m%d}" in body and f"DTEND;VALUE=DATE:{d2 + timedelta(days=1):%Y%m%d}" in body
        assert "TRANSP:TRANSPARENT" in body and "DTSTAMP:" in body
        # Cada línea queda dentro de los 75 octetos del RFC 5545 (sin contar el CRLF).
        assert all(len(line.encode("utf-8")) <= 75 for line in body.split("\r\n"))


def test_the_text_names_the_comuna_and_disclaims_official_status(make_client):
    with make_client(GOES_ENABLED="0") as client:
        _br(client.app.state.services.db, COMUNA, _future(1))
        body = client.get(f"/calendar/boton-rojo/{COMUNA}.ics").text
        assert "No es una alerta oficial" in body and "Viña del Mar" in body
        assert "Tablero CONAF: https://www.arcgis.com/" in body


def test_a_comuna_without_days_still_serves_a_valid_empty_calendar(make_client):
    with make_client(GOES_ENABLED="0") as client:
        response = client.get(f"/calendar/boton-rojo/{COMUNA}.ics")
        body = response.text
        assert response.status_code == 200 and "BEGIN:VCALENDAR" in body and "END:VCALENDAR" in body
        assert "VERSION:2.0" in body and "BEGIN:VEVENT" not in body


def test_text_values_are_escaped_and_folded_per_rfc5545():
    """Ninguna comuna del catálogo tiene coma en el nombre: se prueba el escape directo."""
    assert calendar_mod._esc("a,b;c\\d\ne") == "a\\,b\\;c\\\\d\\ne"
    folded = calendar_mod._fold("X" * 80).split("\r\n")
    assert len(folded) == 2 and folded[1].startswith(" ") and all(len(l) <= 75 for l in folded)
    # Un carácter multibyte no se parte al plegar.
    for line in calendar_mod._fold("á" * 40).split("\r\n"):
        assert len(line.encode("utf-8")) <= 75 and line.encode("utf-8").decode("utf-8") == line


def test_la_ruta_bajo_api_tambien_sirve_el_calendario(make_client):
    """FIX-97: el Worker solo manda /api/* al contenedor; el enlace del Botón Rojo usa esa ruta."""
    with make_client(GOES_ENABLED="0") as client:
        _br(client.app.state.services.db, COMUNA, _future(1))
        response = client.get(f"/api/calendar/boton-rojo/{COMUNA}.ics")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/calendar")
        assert "BEGIN:VCALENDAR" in response.text and "BEGIN:VEVENT" in response.text


def test_el_enlace_del_calendario_en_la_tarjeta_pasa_por_api():
    """Guarda estática: el href debe empezar con /api/ o el Worker responde 404 en producción."""
    source = (ROOT / "web/js/views/zona.js").read_text(encoding="utf-8")
    hrefs = re.findall(r'href="(/[^"]*calendar/boton-rojo/[^"]*)"', source)
    assert hrefs, "no se encontró el enlace del calendario en la tarjeta del lugar"
    assert all(href.startswith("/api/") for href in hrefs), hrefs


# ---- CAL-02: avisos oficiales DMC (viento, calor extremo) en el calendario de la comuna ----


def test_el_aviso_dmc_vigente_entra_al_calendario_con_su_enlace(make_client):
    with make_client(GOES_ENABLED="0") as client:
        db = client.app.state.services.db
        onset = datetime.now(timezone.utc) - timedelta(hours=1)
        _dmc(db, COMUNA, "aviso-1", onset=onset)
        body = client.get(f"/calendar/boton-rojo/{COMUNA}.ics").text
        assert body.count("BEGIN:VEVENT") == 1
        unfolded = _unfold(body)
        assert "UID:dmc-aviso-1@brasa" in unfolded
        assert "Aviso de viento en Viña del Mar · DMC" in unfolded
        assert "severidad Moderate" in unfolded and "senapred.cl" in unfolded
        assert "URL:https://archivos.meteochile.gob.cl/portaldmc/AAA/doc/evento.html" in unfolded
        # La hora del aviso se expresa en hora de Chile, con su VTIMEZONE.
        esperado = onset.astimezone(CHILE_TZ).strftime("%Y%m%dT%H%M%S")
        assert f"DTSTART;TZID=America/Santiago:{esperado}" in unfolded and "BEGIN:VTIMEZONE" in body
        assert all(len(line.encode("utf-8")) <= 75 for line in body.split("\r\n"))


def test_el_aviso_dmc_vencido_y_el_de_otra_comuna_quedan_fuera(make_client):
    with make_client(GOES_ENABLED="0") as client:
        db = client.app.state.services.db
        _dmc(db, COMUNA, "vencido", expires=datetime.now(timezone.utc) - timedelta(hours=1))
        _dmc(db, 9999, "otra-comuna")  # toca otra comuna, no la pedida
        body = client.get(f"/calendar/boton-rojo/{COMUNA}.ics").text
        assert "BEGIN:VEVENT" not in body and "dmc-vencido" not in body and "dmc-otra-comuna" not in body


def test_el_texto_del_cap_se_escapa_en_la_descripcion(make_client):
    with make_client(GOES_ENABLED="0") as client:
        _dmc(client.app.state.services.db, COMUNA, "aviso-2", headline="Viento fuerte, ráfagas\nen la costa")
        unfolded = _unfold(client.get(f"/calendar/boton-rojo/{COMUNA}.ics").text)
        assert "Viento fuerte\\, ráfagas\\nen la costa" in unfolded


# ---- ALR-23: /calendar/lugar/{code}.ics desde el enlace compartido ----


def test_lugar_combina_boton_rojo_y_riesgo_en_un_solo_evento(make_client):
    with make_client(GOES_ENABLED="0") as client:
        db = client.app.state.services.db
        day = _future(1)
        _br(db, COMUNA, day)
        _risk(db, COMUNA, day, "alto")
        _risk(db, COMUNA, _future(2), "bajo")  # nivel bajo no entra al calendario
        body = client.get(f"/calendar/lugar/{COMUNA}.ics").text
        assert body.count("BEGIN:VEVENT") == 1
        unfolded = _unfold(body)
        assert f"UID:brasa-lugar-{COMUNA}-{day:%Y%m%d}@brasa-chile" in unfolded
        assert "Botón Rojo" in unfolded and "estimado" in unfolded  # las dos razones, un evento
        assert "senapred.cl" in unfolded


def test_lugar_con_solo_riesgo_alto_avisa_que_es_estimacion(make_client):
    with make_client(GOES_ENABLED="0") as client:
        db = client.app.state.services.db
        day = _future(1)
        _risk(db, COMUNA, day, "alto")
        body = client.get(f"/calendar/lugar/{COMUNA}.ics").text
        assert body.count("BEGIN:VEVENT") == 1
        unfolded = _unfold(body)
        assert "Condiciones peligrosas estimadas en Viña del Mar" in unfolded
        assert "estimado" in unfolded and "no un pronóstico oficial" in unfolded
        assert f"DTSTART;VALUE=DATE:{day:%Y%m%d}" in unfolded
        assert all(len(line.encode("utf-8")) <= 75 for line in body.split("\r\n"))


def test_lugar_sin_dias_sigue_siendo_un_calendario_valido_y_404_sin_comuna(make_client):
    with make_client(GOES_ENABLED="0") as client:
        response = client.get(f"/calendar/lugar/{COMUNA}.ics")
        assert response.status_code == 200 and "BEGIN:VCALENDAR" in response.text and "BEGIN:VEVENT" not in response.text
        assert "max-age=1800" in response.headers["cache-control"]
        assert client.get("/calendar/lugar/99999.ics").status_code == 404
        assert client.get("/api/calendar/lugar/99999.ics").status_code == 404

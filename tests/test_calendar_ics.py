"""IDEA-14: /calendar/boton-rojo/{code}.ics entrega los días de Botón Rojo de una comuna
en formato .ics (RFC 5545), listo para suscribir en cualquier calendario."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from backend.routes import calendar as calendar_mod

CHILE_TZ = ZoneInfo("America/Santiago")
COMUNA = 5109  # Viña del Mar


def _br(db, code, day, hours=4, area_ha=1200.5):
    db.execute(
        "INSERT INTO boton_rojo(comuna_code, date, hours, area_ha, proportion, fetched_at) VALUES (?,?,?,?,?,?)",
        (code, day.isoformat(), hours, area_ha, 0.1, "2026-01-10T00:00:00Z"),
    )


def _future(days_ahead):
    return datetime.now(CHILE_TZ).date() + timedelta(days=days_ahead)


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

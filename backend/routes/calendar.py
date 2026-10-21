"""Días de Botón Rojo al calendario de la familia (IDEA-14): /calendar/boton-rojo/{code}.ics

Sirve un .ics estándar (RFC 5545) con un evento de día completo por cada día en que CONAF
pronostica Botón Rojo para la comuna. Sirve para recordar el día peligroso sin abrir la app:
el enlace de la tarjeta del lugar se suscribe en Google Calendar, Apple Calendario u Outlook.

Solo lee `boton_rojo`, ya poblada por Services.ingest_boton_rojo. Sin filas responde un
VCALENDAR válido sin VEVENT: la suscripción no se rompe y se actualiza sola cuando llegue
el próximo pronóstico.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from backend.geo import territory
from backend.providers import conaf
from backend.routes.common import services
from backend.services import Services

router = APIRouter(include_in_schema=False)
CHILE_TZ = ZoneInfo("America/Santiago")
NO_OFICIAL = "No es una alerta oficial: sigue a SENAPRED (senapred.cl)."


def _esc(text: str) -> str:
    """Escapa los caracteres especiales de un valor TEXT (RFC 5545 §3.3.11)."""
    return (
        text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r\n", "\\n").replace("\n", "\\n").replace("\r", "\\n")
    )


def _fold(line: str) -> str:
    """Pliega la línea a 75 octetos (RFC 5545 §3.1) sin partir un carácter UTF-8."""
    out, current, limit = [], "", 75
    for ch in line:
        n = len(ch.encode("utf-8"))
        if current and len(current.encode("utf-8")) + n > limit:
            out.append(current)
            current, limit = " " + ch, 74  # las continuaciones llevan un espacio inicial
        else:
            current += ch
    out.append(current)
    return "\r\n".join(out)


def _ics(comuna, rows) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//BRASA Chile//Botón Rojo//ES",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_esc(f'Botón Rojo · {comuna.name}')}",
    ]
    for row in rows:
        day = date.fromisoformat(row["date"])
        desc = (
            f"CONAF pronostica {row['hours']} h en condición Botón Rojo en {comuna.name} "
            f"({row['area_ha']:.0f} ha en el pronóstico). {NO_OFICIAL} "
            f"Tablero CONAF: {conaf.DASHBOARD_URL}"
        )
        lines += [
            "BEGIN:VEVENT",
            f"UID:brasa-botonrojo-{comuna.code}-{day:%Y%m%d}@brasa-chile",
            f"DTSTAMP:{stamp}",
            f"DTSTART;VALUE=DATE:{day:%Y%m%d}",
            f"DTEND;VALUE=DATE:{day + timedelta(days=1):%Y%m%d}",
            f"SUMMARY:{_esc(f'Botón Rojo en {comuna.name} (CONAF)')}",
            f"DESCRIPTION:{_esc(desc)}",
            "TRANSP:TRANSPARENT",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"


@router.get("/api/calendar/boton-rojo/{name}")
@router.get("/calendar/boton-rojo/{name}")
def boton_rojo_ics(name: str, svc: Services = Depends(services)):
    if not name.endswith(".ics") or not name[:-4].isdigit():
        raise HTTPException(404, "Comuna no encontrada.")
    comuna = territory().by_code.get(int(name[:-4]))
    if comuna is None:
        raise HTTPException(404, "Comuna no encontrada.")
    today = datetime.now(CHILE_TZ).date().isoformat()
    rows = svc.db.query(
        "SELECT date, hours, area_ha, proportion FROM boton_rojo WHERE comuna_code = ? AND date >= ? ORDER BY date", (comuna.code, today)
    )
    return Response(
        _ics(comuna, rows).encode("utf-8"), media_type="text/calendar; charset=utf-8", headers={"Cache-Control": "public, max-age=1800"}
    )

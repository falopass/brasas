"""Días peligrosos al calendario de la familia (IDEA-13/14, CAL-02, ALR-23).

Sirve .ics estándar (RFC 5545) listos para suscribir en Google Calendar, Apple
Calendario u Outlook: el enlace de la tarjeta del lugar y del enlace compartido
deja el día peligroso en el calendario de la familia sin abrir la app.

- ``/calendar/boton-rojo/{code}.ics``: un evento de día completo por cada día en que
  CONAF pronostica Botón Rojo para la comuna, más un evento por cada aviso oficial
  vigente de la DMC (viento y calor extremo, ya filtrados en ``ingest_dmc``).
- ``/calendar/lugar/{code}.ics``: el mismo conjunto, más los días con riesgo
  ``alto``/``extremo`` estimado por BRASA (30-30-30 + FWI, ``risk_daily``). Si un día
  tiene Botón Rojo y riesgo alto, es un solo VEVENT con las dos razones.

El calendario se pide por código de comuna (dato público): nunca por id de lugar ni
de dispositivo, y no incluye ningún dato personal. Sin filas responde un VCALENDAR
válido sin VEVENT: la suscripción no se rompe y se actualiza sola al próximo ciclo.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from backend.geo import territory
from backend.providers import conaf, dmc
from backend.routes.common import services
from backend.services import Services

router = APIRouter(include_in_schema=False)
CHILE_TZ = ZoneInfo("America/Santiago")
TZ_ID = "America/Santiago"
NO_OFICIAL = "No es una alerta oficial: sigue a SENAPRED (senapred.cl)."
# Regla horaria vigente de Chile continental (horario de verano desde el primer
# domingo de septiembre, horario estándar desde el primero de abril).
VTIMEZONE = [
    "BEGIN:VTIMEZONE",
    f"TZID:{TZ_ID}",
    "BEGIN:STANDARD",
    "DTSTART:19700405T000000",
    "TZOFFSETFROM:-0300",
    "TZOFFSETTO:-0400",
    "TZNAME:-04",
    "RRULE:FREQ=YEARLY;BYMONTH=4;BYDAY=1SU",
    "END:STANDARD",
    "BEGIN:DAYLIGHT",
    "DTSTART:19700906T000000",
    "TZOFFSETFROM:-0400",
    "TZOFFSETTO:-0300",
    "TZNAME:-03",
    "RRULE:FREQ=YEARLY;BYMONTH=9;BYDAY=1SU",
    "END:DAYLIGHT",
    "END:VTIMEZONE",
]


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


def _cap_local(value: Any) -> tuple[str, Any] | None:
    """Fecha u hora de un CAP 1.2 ya en hora de Chile.

    ``("date", date)`` si el CAP solo trae fecha, ``("dt", datetime)`` con zona si
    trae hora (sin zona se asume hora de Chile), ``None`` si no se puede leer.
    """
    if not value:
        return None
    text = str(value).strip()
    try:
        if "T" not in text:
            return ("date", date.fromisoformat(text[:10]))
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=CHILE_TZ)
    return ("dt", parsed.astimezone(CHILE_TZ))


def _vigente(row: dict, now: datetime) -> bool:
    """Vigencia del aviso como en ``common.dmc_by_comuna``: sin marca legible se
    conserva (mejor un aviso de más que un aviso oficial oculto)."""
    onset, expires = _cap_local(row["onset"]), _cap_local(row["expires"])
    if onset and onset[0] == "dt" and onset[1] > now:
        return False
    if expires and expires[0] == "dt" and expires[1] <= now:
        return False
    return True


def _dmc_rows(svc: Services, code: int) -> list[dict]:
    """Filas de ``dmc_alerts`` vigentes que tocan la comuna, sin repetir id."""
    now = datetime.now(timezone.utc)
    out, seen = [], set()
    for row in svc.db.query("SELECT * FROM dmc_alerts ORDER BY onset"):
        if row["id"] in seen or code not in json.loads(row["comunas"] or "[]") or not _vigente(row, now):
            continue
        seen.add(row["id"])
        out.append(row)
    return out


def _br_description(comuna, row: dict) -> str:
    """El porqué del día de Botón Rojo, con su fuente (texto compartido por ambos feeds)."""
    return (
        f"CONAF pronostica {row['hours']} h en condición Botón Rojo en {comuna.name} "
        f"({row['area_ha']:.0f} ha en el pronóstico). Tablero CONAF: {conaf.DASHBOARD_URL}"
    )


def _br_events(comuna, rows: list[dict]) -> list[dict]:
    return [
        {
            "sort": row["date"],
            "uid": f"brasa-botonrojo-{comuna.code}-{date.fromisoformat(row['date']):%Y%m%d}@brasa-chile",
            "summary": f"Botón Rojo en {comuna.name} (CONAF)",
            "desc": f"{_br_description(comuna, row)} {NO_OFICIAL}",
            "start": ("date", date.fromisoformat(row["date"])),
            "end": None,
            "url": None,
        }
        for row in rows
    ]


def _day_events(comuna, br_rows: list[dict], risk_rows: list[dict]) -> list[dict]:
    """Un VEVENT por día peligroso: Botón Rojo, riesgo estimado o ambos (ALR-23)."""
    days: dict[str, dict[str, dict]] = {}
    for row in br_rows:
        days.setdefault(row["date"], {})["br"] = row
    for row in risk_rows:
        days.setdefault(row["date"], {})["risk"] = row
    events = []
    for day_iso in sorted(days):
        day = date.fromisoformat(day_iso)
        br, risk = days[day_iso].get("br"), days[day_iso].get("risk")
        reasons = []
        if br:
            reasons.append(_br_description(comuna, br))
        if risk:
            level = risk["level_combined"] or risk["level"]
            reasons.append(
                "Escenario estimado por BRASA (regla 30-30-30 + índice FWI): "
                f"nivel {level} para el día. Es una estimación, no un pronóstico oficial."
            )
        if br and risk:
            summary = f"Día peligroso en {comuna.name}"
        elif br:
            summary = f"Botón Rojo en {comuna.name} (CONAF)"
        else:
            summary = f"Condiciones peligrosas estimadas en {comuna.name}"
        events.append(
            {
                "sort": day_iso,
                "uid": f"brasa-lugar-{comuna.code}-{day:%Y%m%d}@brasa-chile",
                "summary": summary,
                "desc": f"{' '.join(reasons)} {NO_OFICIAL}",
                "start": ("date", day),
                "end": None,
                "url": None,
            }
        )
    return events


def _dmc_events(comuna, rows: list[dict]) -> list[dict]:
    events = []
    for row in rows:
        start = _cap_local(row["onset"]) or _cap_local(row["expires"])
        if start is None:
            continue  # sin fecha legible no hay dónde ponerlo en el calendario
        end = _cap_local(row["expires"])
        label = dmc.KIND_LABELS.get(row["kind"], row["kind"])
        desc = f"{row['headline'] or row['event']}. "
        desc += f"Aviso oficial de la Dirección Meteorológica de Chile, severidad {row['severity'] or 'no indicada'}. "
        if row["web"]:
            desc += f"Aviso: {row['web']}. "
        desc += NO_OFICIAL
        events.append(
            {
                "sort": start[1].strftime("%Y-%m-%dT%H:%M:%S") if start[0] == "dt" else start[1].isoformat(),
                "uid": f"dmc-{row['id']}@brasa",
                "summary": f"Aviso de {label[:1].lower() + label[1:]} en {comuna.name} · DMC",
                "desc": desc,
                "start": start,
                "end": end,
                "url": row["web"] or None,
            }
        )
    return events


def _ics(comuna, events: list[dict]) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//BRASA Chile//Días peligrosos//ES",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_esc(f'Días peligrosos · {comuna.name}')}",
        *VTIMEZONE,
    ]
    for ev in sorted(events, key=lambda e: e["sort"]):
        lines += ["BEGIN:VEVENT", f"UID:{ev['uid']}", f"DTSTAMP:{stamp}"]
        kind, value = ev["start"]
        if kind == "date":
            lines.append(f"DTSTART;VALUE=DATE:{value:%Y%m%d}")
            end = ev["end"] or ev["start"]
            end_day = end[1].date() if end[0] == "dt" else end[1]
            lines.append(f"DTEND;VALUE=DATE:{end_day + timedelta(days=1):%Y%m%d}")
        else:
            lines.append(f"DTSTART;TZID={TZ_ID}:{value:%Y%m%dT%H%M%S}")
            if ev["end"] and ev["end"][0] == "dt":
                lines.append(f"DTEND;TZID={TZ_ID}:{ev['end'][1]:%Y%m%dT%H%M%S}")
        lines += [f"SUMMARY:{_esc(ev['summary'])}", f"DESCRIPTION:{_esc(ev['desc'])}"]
        if ev["url"]:
            lines.append(f"URL:{ev['url']}")
        lines += ["TRANSP:TRANSPARENT", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"


def _comuna_or_404(name: str):
    if not name.endswith(".ics") or not name[:-4].isdigit():
        raise HTTPException(404, "Comuna no encontrada.")
    comuna = territory().by_code.get(int(name[:-4]))
    if comuna is None:
        raise HTTPException(404, "Comuna no encontrada.")
    return comuna


def _br_rows(svc: Services, code: int, today: str) -> list[dict]:
    return svc.db.query(
        "SELECT date, hours, area_ha, proportion FROM boton_rojo WHERE comuna_code = ? AND date >= ? ORDER BY date", (code, today)
    )


def _respond(comuna, events: list[dict]) -> Response:
    return Response(
        _ics(comuna, events).encode("utf-8"), media_type="text/calendar; charset=utf-8", headers={"Cache-Control": "public, max-age=1800"}
    )


@router.get("/api/calendar/boton-rojo/{name}")
@router.get("/calendar/boton-rojo/{name}")
def boton_rojo_ics(name: str, svc: Services = Depends(services)):
    comuna = _comuna_or_404(name)
    today = datetime.now(CHILE_TZ).date().isoformat()
    events = _br_events(comuna, _br_rows(svc, comuna.code, today)) + _dmc_events(comuna, _dmc_rows(svc, comuna.code))
    return _respond(comuna, events)


@router.get("/api/calendar/lugar/{name}")
@router.get("/calendar/lugar/{name}")
def lugar_ics(name: str, svc: Services = Depends(services)):
    """Calendario del lugar compartido: Botón Rojo + días de riesgo alto/extremo
    estimados por BRASA + avisos DMC vigentes. Solo por código de comuna."""
    comuna = _comuna_or_404(name)
    today = datetime.now(CHILE_TZ).date().isoformat()
    risk_rows = svc.db.query(
        "SELECT date, level, level_combined, score FROM risk_daily "
        "WHERE comuna_code = ? AND date >= ? AND COALESCE(level_combined, level) IN ('alto', 'extremo') ORDER BY date",
        (comuna.code, today),
    )
    events = _day_events(comuna, _br_rows(svc, comuna.code, today), risk_rows) + _dmc_events(comuna, _dmc_rows(svc, comuna.code))
    return _respond(comuna, events)

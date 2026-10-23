"""Panorama de la temporada de incendios: totales y desglose por región y comuna (TEMP-01/02).

Todo lo que aquí se muestra son agregados de `official_fires` (el reporte público de
incendios que publica CONAF en GEPRIF) y de `boton_rojo` (el pronóstico oficial de
condiciones extremas). Solo agregados: no hay lugares, dispositivos ni reportes de
personas en esta respuesta.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query

from backend.geo import territory
from backend.providers import conaf
from backend.routes.common import services
from backend.services import Services

router = APIRouter(prefix="/api")

CHILE_TZ = ZoneInfo("America/Santiago")

# Estado normalizado de `official_fires` → clave del resumen público. «confirmado» es un
# incendio que sigue activo según CONAF (en combate o bajo observación), aún sin controlar.
STATUS_TOTALS = {"confirmado": "en_combate", "controlado": "controlados", "extinguido": "extinguidos"}

NOT_OFFICIAL = (
    "BRASA no es una fuente oficial. Los totales salen del reporte público de incendios de "
    "CONAF; en una emergencia sigue a SENAPRED y llama al 130 (CONAF) o al 132 (Bomberos)."
)


def _season_window(season: str) -> tuple[str, str]:
    """La temporada de CONAF corre del 1 de julio al 30 de junio siguiente.

    «2025-2026» → jul 2025 a jun 2026. Si el reporte trae solo el año del incendio
    («2026»), la temporada empezó en julio del año anterior.
    """
    first = int(season.split("-")[0])
    start = first if "-" in season[4:] else first - 1
    return f"{start}-07-01", f"{start + 1}-06-30"


def _week_days(svc: Services, start: date, end: date) -> dict[str, tuple[int, float]]:
    """Días con incendios informados dentro de `[start, end]`, en calendario de Chile.

    `started_at` está en UTC y el día de Chile no coincide con el de UTC, así que se
    consulta con un día de holgura por lado y cada fila se convierte a `CHILE_TZ` antes
    de decidir a qué día pertenece. Devuelve {día: (incendios, hectáreas)} solo de los
    días que tienen al menos un incendio: los días sin filas cuentan como cero.
    """
    since = datetime.combine(start - timedelta(days=1), time.min, tzinfo=CHILE_TZ).astimezone(timezone.utc)
    until = datetime.combine(end + timedelta(days=1), time.max, tzinfo=CHILE_TZ).astimezone(timezone.utc)
    rows = svc.db.query(
        "SELECT started_at, area_ha FROM official_fires WHERE started_at >= ? AND started_at <= ?",
        (since.strftime("%Y-%m-%dT%H:%M:%SZ"), until.strftime("%Y-%m-%dT%H:%M:%SZ")),
    )
    days: dict[str, tuple[int, float]] = {}
    for row in rows:
        try:
            day = datetime.fromisoformat(row["started_at"].replace("Z", "+00:00")).astimezone(CHILE_TZ).date()
        except (AttributeError, ValueError):
            continue  # fecha ilegible: no se inventa un día
        if not start <= day <= end:
            continue
        n, ha = days.get(day.isoformat(), (0, 0.0))
        days[day.isoformat()] = (n + 1, ha + (row["area_ha"] or 0.0))
    return days


def _week_window(start: date, end: date, days: dict[str, tuple[int, float]]) -> dict:
    return {
        "desde": start.isoformat(),
        "hasta": end.isoformat(),
        "incendios": sum(n for n, _ in days.values()),
        "ha": round(sum(ha for _, ha in days.values()), 1),
        "dias_con_datos": len(days),
    }


def _week_block(svc: Services, today: date) -> dict:
    """«Esta semana» contra la anterior: los últimos 7 días calendario de Chile y los 7 previos.

    Cuenta los incendios por la fecha de detección (`started_at`) que ya usa el resumen,
    sin mirar la temporada pedida: la pregunta es cómo viene la semana, no cómo va una
    temporada pasada. `dias_con_datos` dice cuántos de los 7 días tienen al menos un
    incendio informado; un día sin filas suma cero, no se estima.
    """
    start = today - timedelta(days=6)
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=6)
    return {
        **_week_window(start, today, _week_days(svc, start, today)),
        "anterior": _week_window(prev_start, prev_end, _week_days(svc, prev_start, prev_end)),
    }


def _comuna_detail(svc: Services, terr, comunas: dict, code_for, code: int, season: str | None) -> dict:
    """TEMP-03: el detalle de una comuna en la temporada pedida, aunque no entre al top 12.

    `current`/`previous` agregan las filas cuyo nombre de CONAF se resuelve al código con
    `code_for` (nombre BCN o el punto de un incendio). 422 si el código no existe.
    """
    c = terr.by_code.get(code)
    if c is None:
        raise HTTPException(422, f"No hay una comuna chilena con el código {code}.")
    current = {"n": 0, "ha": 0.0, "en_combate": 0}
    for (nombre, region), agg in comunas.items():
        if nombre and code_for(nombre, region) == code:
            current["n"] += agg["n"]
            current["ha"] += agg["ha"]
            current["en_combate"] += agg["en_combate"]
    br_days, previous = 0, None
    if season:
        start, end = _season_window(season)
        br_days = svc.db.one(
            "SELECT COUNT(DISTINCT date) AS n FROM boton_rojo WHERE comuna_code = ? AND date BETWEEN ? AND ?",
            (code, start, end))["n"]
        prev_season = f"{int(season[:4]) - 1}-{int(season[:4])}"
        previous = {"season": prev_season, "n": 0, "ha": 0.0}
        prev_points = {
            (r["comuna"], r["region"]): (r["lat"], r["lon"])
            for r in svc.db.query(
                "SELECT comuna, region, lat, lon, MIN(rowid) FROM official_fires WHERE season = ? AND comuna IS NOT NULL GROUP BY comuna, region",
                (prev_season,))
        }
        for r in svc.db.query(
            "SELECT comuna, region, COUNT(*) AS n, SUM(COALESCE(area_ha, 0)) AS ha FROM official_fires WHERE season = ? GROUP BY comuna, region",
            (prev_season,)):
            found = terr.comunas_named(r["comuna"])
            hit = found[0].code if len(found) == 1 else None
            if hit is None:
                point = prev_points.get((r["comuna"], r["region"]))
                located = terr.locate(*point) if point else None
                hit = located.code if located else None
            if hit == code:
                previous["n"] += r["n"]
                previous["ha"] += r["ha"]
    return {
        "comuna": {"code": c.code, "name": c.name, "region": c.region},
        "current": {"n": current["n"], "ha": round(current["ha"], 1), "en_combate": current["en_combate"]},
        "boton_rojo_days": br_days,
        "previous": {"season": previous["season"], "n": previous["n"], "ha": round(previous["ha"], 1)} if previous else None,
    }


@router.get("/panorama")
def panorama(season: str | None = Query(None, pattern=r"^\d{4}-\d{4}$"),
             comuna: int | None = Query(None, ge=1), svc: Services = Depends(services)):
    """Agregados de una temporada: incendios informados, hectáreas, estado oficial y días
    con Botón Rojo, más la semana en curso contra la anterior (TEMP-31).

    Sin parámetro usa la temporada más reciente presente en la tabla (igual que
    `/api/opendata/response.json`). Si la temporada pedida no tiene filas responde 200
    igual, con ceros: una temporada sin incendios informados no es una falla del servidor.
    """
    if season is None:
        latest = svc.db.one("SELECT MAX(season) AS s FROM official_fires WHERE season IS NOT NULL")
        season = latest["s"] if latest else None
    rows = (
        svc.db.query(
            "SELECT region, comuna, status, COUNT(*) AS n, SUM(COALESCE(area_ha, 0)) AS ha "
            "FROM official_fires WHERE season = ? GROUP BY region, comuna, status",
            (season,),
        )
        if season
        else []
    )

    totals = {"n": 0, "ha": 0.0, "en_combate": 0, "controlados": 0, "extinguidos": 0}
    regions: dict[str | None, dict] = {}
    comunas: dict[tuple[str | None, str | None], dict] = {}
    for row in rows:
        key = STATUS_TOTALS.get(row["status"])
        totals["n"] += row["n"]
        totals["ha"] += row["ha"]
        if key:
            totals[key] += row["n"]
        reg = regions.setdefault(row["region"], {"region": row["region"], "n": 0, "ha": 0.0, "en_combate": 0})
        reg["n"] += row["n"]
        reg["ha"] += row["ha"]
        com = comunas.setdefault(
            (row["comuna"], row["region"]), {"comuna": row["comuna"], "region": row["region"], "n": 0, "ha": 0.0, "en_combate": 0}
        )
        com["n"] += row["n"]
        com["ha"] += row["ha"]
        if key == "en_combate":
            reg["en_combate"] += row["n"]
            com["en_combate"] += row["n"]

    boton_rojo_days = 0
    if season:
        start, end = _season_window(season)
        boton_rojo_days = svc.db.one("SELECT COUNT(DISTINCT date) AS n FROM boton_rojo WHERE date BETWEEN ? AND ?", (start, end))["n"]

    # Código de la comuna para enlazar a /riesgo: primero por el nombre que declara CONAF;
    # si no calza con el territorio BCN, por el punto de un incendio del grupo.
    terr = territory()
    points = {
        (r["comuna"], r["region"]): (r["lat"], r["lon"])
        for r in (
            svc.db.query(
                "SELECT comuna, region, lat, lon, MIN(rowid) "
                "FROM official_fires WHERE season = ? AND comuna IS NOT NULL "
                "GROUP BY comuna, region",
                (season,),
            )
            if season
            else []
        )
    }

    def code_for(comuna: str, region: str | None) -> int | None:
        found = terr.comunas_named(comuna)
        if len(found) == 1:
            return found[0].code
        point = points.get((comuna, region))
        located = terr.locate(*point) if point else None
        return located.code if located else None

    ranked = sorted(comunas.values(), key=lambda c: (-c["ha"], -c["n"], c["comuna"] or ""))
    by_comuna = [
        {
            "comuna": c["comuna"],
            "region": c["region"],
            "comuna_code": code_for(c["comuna"], c["region"]) if c["comuna"] else None,
            "n": c["n"],
            "ha": round(c["ha"], 1),
            "en_combate": c["en_combate"],
        }
        for c in ranked[:12]
    ]

    seasons = [
        r["season"] for r in svc.db.query("SELECT DISTINCT season FROM official_fires WHERE season IS NOT NULL ORDER BY season DESC")
    ]

    # Estados del reporte que STATUS_MAP no reconoce: al parsear caen en «confirmado» por
    # defecto y este conteo los hace visibles, para detectar a tiempo un cambio de formato
    # de CONAF. No altera los totales: cada incendio sigue contando según su `status`.
    unknown_values = [
        {"raw": r["status_raw"], "n": r["n"]}
        for r in (
            svc.db.query(
                "SELECT status_raw, COUNT(*) AS n FROM official_fires WHERE season = ? AND status_raw IS NOT NULL GROUP BY status_raw",
                (season,),
            )
            if season
            else []
        )
        if r["status_raw"].strip().lower() not in conaf.STATUS_MAP
    ]
    updated = svc.db.one("SELECT MAX(fetched_at) AS t FROM official_fires WHERE season = ?", (season,)) if season else None
    return {
        "type": "panorama",
        "season": season,
        "seasons": seasons,
        "totals": {**totals, "ha": round(totals["ha"], 1)},
        "by_region": sorted(
            ({"region": r["region"], "n": r["n"], "ha": round(r["ha"], 1), "en_combate": r["en_combate"]} for r in regions.values()),
            key=lambda r: (-r["ha"], -r["n"], r["region"] or ""),
        ),
        "by_comuna": by_comuna,
        "by_comuna_total": len(ranked),
        "by_comuna_truncated": len(ranked) > 12,
        "boton_rojo_days": boton_rojo_days,
        "semana": _week_block(svc, datetime.now(CHILE_TZ).date()),
        "unknown_status": {
            "n": sum(v["n"] for v in unknown_values),
            "values": sorted(unknown_values, key=lambda v: (-v["n"], v["raw"]))[:5],
        },
        "comuna_detail": _comuna_detail(svc, terr, comunas, code_for, comuna, season) if comuna is not None else None,
        "source": {
            "name": conaf.FIRES_SOURCE,
            "url": conaf.FIRES_PAGE_URL,
            "note": "Incendios informados por CONAF, con su estado oficial. BRASA los muestra tal como los publica CONAF.",
        },
        "boton_rojo_source": {
            "name": conaf.SOURCE,
            "url": conaf.DASHBOARD_URL,
            "note": (
                "Pronóstico oficial de CONAF de condiciones favorables para incendios; no indica un "
                "incendio. BRASA conserva el pronóstico solo unos días, así que el recuento cubre "
                "lo último guardado, no toda la temporada."
            ),
        },
        "updated_at": updated["t"] if updated else None,
        "not_official": NOT_OFFICIAL,
    }

"""Panorama de la temporada de incendios: totales y desglose por región y comuna (TEMP-01/02).

Todo lo que aquí se muestra son agregados de `official_fires` (el reporte público de
incendios que publica CONAF en GEPRIF) y de `boton_rojo` (el pronóstico oficial de
condiciones extremas). Solo agregados: no hay lugares, dispositivos ni reportes de
personas en esta respuesta.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from backend.geo import territory
from backend.providers import conaf
from backend.routes.common import services
from backend.services import Services

router = APIRouter(prefix="/api")

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


@router.get("/panorama")
def panorama(season: str | None = Query(None, pattern=r"^\d{4}-\d{4}$"), svc: Services = Depends(services)):
    """Agregados de una temporada: incendios informados, hectáreas, estado oficial y días
    con Botón Rojo.

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

    by_comuna = [
        {
            "comuna": c["comuna"],
            "region": c["region"],
            "comuna_code": code_for(c["comuna"], c["region"]) if c["comuna"] else None,
            "n": c["n"],
            "ha": round(c["ha"], 1),
            "en_combate": c["en_combate"],
        }
        for c in sorted(comunas.values(), key=lambda c: (-c["ha"], -c["n"], c["comuna"] or ""))[:12]
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
    updated = svc.db.one("SELECT MAX(fetched_at) AS t FROM official_fires")
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
        "boton_rojo_days": boton_rojo_days,
        "unknown_status": {
            "n": sum(v["n"] for v in unknown_values),
            "values": sorted(unknown_values, key=lambda v: (-v["n"], v["raw"]))[:5],
        },
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

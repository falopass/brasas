"""API pública: configuración, estado de fuentes, observaciones, exploración FIRMS, riesgo, clima
y la opinión agregada sobre los avisos."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import statistics
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from backend import cases as cases_mod
from backend import diagnostics
from backend import freshness
from backend import fwi
from backend import trend as trend_mod
from backend import incidents as incidents_mod
from backend.geo import incident_hull, protected_areas_near, territory
from backend.notify import webpush
from backend.providers import conaf, firms, goes, weather
from backend.risk import LEVEL_LABELS
from backend.version import VERSION
from backend.routes.common import dmc_by_comuna, dmc_for_comuna, dmc_source, limiter, rain_by_comuna, rain_for_comuna, rain_source, services
from backend.services import Services, stamp

router = APIRouter(prefix="/api")
log = logging.getLogger("brasa")
CHILE_TZ = ZoneInfo("America/Santiago")
RECENT_ARCHIVE_DAYS = 60
OBSERVATIONS_LIMIT = 20000  # tope de detecciones por consulta; se pide una de más para saber si hubo recorte
GOES_SWEEPS = 6  # barridos que se muestran en /api/status para poder ver huecos (DET-13)
INCIDENT_ID = re.compile(r"^[0-9a-f]{12}$")
STATUS_ORDER = "CASE status WHEN 'confirmado' THEN 0 WHEN 'reportado' THEN 1 WHEN 'posible' THEN 2 WHEN 'anomalia' THEN 3 ELSE 4 END"


@router.get("/health")
def health():
    return {"status": "ok", "name": "BRASA Chile", "version": VERSION, "time_utc": stamp()}


@router.get("/config")
def config(svc: Services = Depends(services)):
    s = svc.settings
    _, public_key = webpush.ensure_keys(svc.db)
    return {
        "version": VERSION,
        "ion_public_token": s.cesium_ion_token,
        "firms_configured": bool(s.firms_map_key),
        "goes_enabled": s.goes_enabled,
        "telegram": {"enabled": bool(s.telegram_bot_token and s.telegram_bot_username), "username": s.telegram_bot_username or None},
        "push": {"public_key": public_key},
        "moderation_enabled": bool(s.admin_token),
        "turnstile_site_key": s.turnstile_site_key,
        "zones": territory().zones(),
        "risk_levels": LEVEL_LABELS,
    }


FIRMS_QUOTA_TTL_S = 45 * 60  # el cupo de la clave se consulta a FIRMS a lo sumo cada 45 min, no por request


async def _firms_quota_refresh(svc: Services) -> None:
    """Actualiza el cupo guardado en `kv` consultando a FIRMS, fuera del camino de /api/status."""
    try:
        saved = {**await firms.key_status(svc.settings.firms_map_key, client=svc.client), "checked_at": stamp()}
        svc.db.kv_set("firms_quota", json.dumps(saved))
    except Exception as exc:  # el estado ya respondió con lo guardado; el fallo solo se registra
        log.warning("Consulta del cupo FIRMS falló: %s", exc)


async def firms_quota(svc: Services) -> dict[str, Any]:
    """Último consumo conocido de la clave FIRMS en su ventana de 10 min, para ver venir el 429.

    Lee solo lo guardado en `kv`: en Cloudflare el contenedor se suspende entre disparos del
    cron y la memoria se pierde. ROB-01: cuando el dato está vencido la consulta a FIRMS se
    dispara en segundo plano (una a la vez) y la respuesta sale con lo último guardado —
    /api/status nunca la espera y responde 200 igual.
    """
    try:
        saved = json.loads(svc.db.kv_get("firms_quota") or "{}")
    except ValueError:
        saved = {}
    fresh = False
    checked_at = saved.get("checked_at")
    if isinstance(checked_at, str):
        try:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(checked_at.replace("Z", "+00:00"))).total_seconds()
            fresh = age < FIRMS_QUOTA_TTL_S
        except ValueError:
            pass
    if not fresh and svc.settings.firms_map_key:
        task = getattr(svc, "_firms_quota_task", None)
        if task is None or task.done():
            svc._firms_quota_task = asyncio.create_task(_firms_quota_refresh(svc))
            svc.tasks.append(svc._firms_quota_task)  # así se cancela limpio al cerrar la app
    return {"limit": saved.get("limit"), "used": saved.get("used"), "checked_at": saved.get("checked_at"), "error": not fresh}


@router.get("/status")
async def status(history: int = Query(0, ge=0, le=50), coverage: bool = Query(False), svc: Services = Depends(services)):
    """Estado de cada fuente: última ejecución, último éxito y latencia de datos.

    `history=N` agrega las últimas N ejecuciones por producto. Sin él solo viene la última, que no
    alcanza para detectar tres fallos seguidos: eso lo consulta el monitoreo programado.
    `coverage=1` agrega la cobertura de FWI, DMC y lluvia (OPS-19); no va por defecto para no
    engordar la respuesta que se pide desde la calle.
    """
    runs = svc.db.query(
        "SELECT r.provider, r.product, r.started_at, r.finished_at, r.ok, r.n_records, r.n_new, r.message FROM ingest_runs r "
        "JOIN (SELECT product, MAX(id) AS id FROM ingest_runs GROUP BY product) last ON last.id = r.id ORDER BY r.provider"
    )
    last_ok = {
        r["product"]: r["finished_at"]
        for r in svc.db.query("SELECT product, MAX(finished_at) AS finished_at FROM ingest_runs WHERE ok = 1 GROUP BY product")
    }
    newest = {r["source"]: r["t"] for r in svc.db.query("SELECT source, MAX(observed_at) AS t FROM observations GROUP BY source")}
    for r in runs:
        r["last_ok_at"] = last_ok.get(r["product"])
        r["ok"] = bool(r["ok"])
    recent: dict[str, list[dict[str, Any]]] = {}
    if history:
        rows = svc.db.query(
            "SELECT product, ok, started_at FROM (SELECT product, ok, started_at, "
            "ROW_NUMBER() OVER (PARTITION BY product ORDER BY id DESC) AS rn FROM ingest_runs) "
            "WHERE rn <= ? ORDER BY product, rn",
            (history,),
        )
        for row in rows:
            recent.setdefault(row["product"], []).append({"ok": bool(row["ok"]), "started_at": row["started_at"]})
    # DET-13: el hueco se deriva en el servidor (como `freshness`) para que la interfaz no repita
    # la aritmética: GOES-19 entrega un disco completo cada 10 min, así que se esperan
    # GOES_SWEEPS barridos `ok` en la última hora. La ventana se cuenta por la hora del barrido,
    # guardada en `source_ref` (la clave S3), no por `started_at`: el relleno inicial ingiere
    # barridos de hasta 6 horas atrás con la marca de ahora y los contaría como recientes.
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=1)
    goes_ok = sum(
        1
        for row in svc.db.query(
            "SELECT DISTINCT source_ref FROM ingest_runs WHERE provider = 'NOAA GOES' AND ok = 1 AND started_at >= ?", (stamp(since),)
        )
        if (start := goes.key_start(row["source_ref"])) is not None and start >= since
    )
    goes_missing = max(0, GOES_SWEEPS - goes_ok)
    try:
        errors = diagnostics.error_summary(svc.db)
        failures = diagnostics.failures_24h(svc.db)
    except Exception:
        errors = {"error": True}
        failures = {"error": True}
    backup_bytes = svc.db.kv_get("backup_bytes")
    work_bytes = svc.db.kv_get("work_backup_bytes")
    coverage_data = None
    if coverage:
        # OPS-19: cobertura de FWI, DMC y lluvia para que el diagnóstico de producción compare
        # contra las 345 comunas sin abrir la base.
        today_cl = datetime.now(CHILE_TZ).date().isoformat()
        coverage_row = svc.db.one(
            "SELECT "
            "(SELECT COUNT(DISTINCT comuna_code) FROM fwi_daily WHERE date = ?) AS fwi_comunas, "
            "(SELECT COUNT(*) FROM rain_normal) AS rain_normals, "
            "(SELECT COUNT(DISTINCT comuna_code) FROM rain_season WHERE year = (SELECT MAX(year) FROM rain_season)) AS rain_comunas, "
            "(SELECT COUNT(*) FROM dmc_alerts) AS dmc_alerts, "
            "(SELECT GROUP_CONCAT(comunas, '|') FROM dmc_alerts) AS dmc_comunas_json",
            (today_cl,),
        )
        dmc_comunas: set[int] = set()
        for chunk in (coverage_row["dmc_comunas_json"] or "").split("|"):
            try:
                dmc_comunas.update(int(code) for code in json.loads(chunk or "[]"))
            except (TypeError, ValueError):
                continue
        coverage_data = {
            "comunas": len(territory().comunas),
            "fwi_comunas": coverage_row["fwi_comunas"],
            "rain_normals": coverage_row["rain_normals"],
            "rain_comunas": coverage_row["rain_comunas"],
            "dmc_alerts": coverage_row["dmc_alerts"],
            "dmc_comunas": len(dmc_comunas),
        }
    return {
        "time_utc": stamp(),
        "last_ingest_at": svc.db.kv_get("last_ingest_at"),
        # Contrato de frescura: la regla de los 30 minutos vive en el servidor (backend/freshness.py)
        # para que la interfaz no repita la aritmética ni invente otro umbral.
        "freshness": freshness.status(svc.db.kv_get("last_ingest_at")),
        # El resumen se lee de la base: en Cloudflare el contenedor se suspende entre disparos del
        # cron y la copia en memoria se pierde (quedaba en null aunque los ciclos sí corrieran).
        "last_cycle": json.loads(svc.db.kv_get("last_cycle")) if svc.db.kv_get("last_cycle") else svc.last_cycle,
        # OPS-18: tamaño comprimido de los respaldos (lo registra backend/storage.py tras cada subida).
        "backup": {
            "bytes": int(backup_bytes) if backup_bytes else None,
            "updated_at": svc.db.kv_get("backup_at"),
            "work_bytes": int(work_bytes) if work_bytes else None,
            "work_updated_at": svc.db.kv_get("work_backup_at"),
        },
        **({"history": recent} if history else {}),
        "risk_computed_at": svc.db.kv_get("risk_computed_at"),
        **({"coverage": coverage_data} if coverage_data is not None else {}),
        "scheduler_enabled": svc.settings.scheduler_enabled,
        # "interna": tareas en este proceso · "cron": la dispara un programador externo (Cloudflare) · "apagada"
        "ingest_mode": "interna" if svc.settings.scheduler_enabled else "cron" if svc.settings.internal_token else "apagada",
        "firms_configured": bool(svc.settings.firms_map_key),
        "firms_quota": await firms_quota(svc),
        "runs": runs,
        # DET-13: todos los barridos de GOES comparten producto, así que «la última ejecución» esconde
        # un hueco en medio. Se devuelven los últimos para poder ver si falta alguno.
        "goes_sweeps": [
            {"source_ref": row["source_ref"], "ok": bool(row["ok"]), "started_at": row["started_at"]}
            for row in svc.db.query(
                "SELECT source_ref, ok, started_at FROM ingest_runs WHERE provider = 'NOAA GOES' ORDER BY id DESC LIMIT ?", (GOES_SWEEPS,)
            )
        ],
        "errors": errors,
        "failures_24h": failures,
        "goes_missing": goes_missing,
        "goes_gap": goes_missing > 2,
        # RISK-14/REV-20: llamadas y ubicaciones de Open-Meteo. `calls` y `locations` son de este
        # proceso; `scheduled` es el acumulado del día que sobrevive a la suspensión del contenedor.
        "open_meteo": {
            **weather.counts(),
            "daily_cap": weather.DAILY_LOCATIONS_CAP,
            "scheduled": svc.open_meteo_day(),
        },
        "newest_observation": newest,
        "incidents_open": {
            r["status"]: r["n"]
            for r in svc.db.query(
                "SELECT status, COUNT(*) AS n FROM incidents WHERE status NOT IN ('extinguido', 'descartado') AND fixed_source = 0 GROUP BY status"
            )
        },
    }


# DET-20: la lista es el contrato público de cada punto. El resto de `observations` es
# interno (run_id, ingested_at, alerts_evaluated_at, confidence_raw, brightness_k) y no sale.
OBSERVATION_FIELDS = (
    "id",
    "source",
    "sensor",
    "satellite",
    "resolution_m",
    "lat",
    "lon",
    "observed_at",
    "frp_mw",
    "confidence",
    "comuna_code",
)


def _observation_public(row: dict) -> dict:
    comuna = territory().by_code.get(row["comuna_code"])
    out = {k: row[k] for k in OBSERVATION_FIELDS}
    out.update(
        {
            "incident_id": row["incident_id"],
            "incident_status": row["incident_status"],
            "incident_n": row["incident_n"],
            "incident_fixed": row["incident_fixed"],
            "comuna": comuna.name if comuna else None,
            "region": comuna.region if comuna else None,
        }
    )
    return out


@router.get("/observations")
def observations(
    hours: int = Query(48, ge=1, le=24 * 14),
    bbox: str | None = Query(None, description="west,south,east,north"),
    reliable: bool = Query(False, description="Solo confianza nominal/alta (VIIRS/MODIS) o alta/media (GOES)"),
    svc: Services = Depends(services),
):
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    sql = (
        "SELECT " + ", ".join(f"o.{f}" for f in OBSERVATION_FIELDS) + ", i.id AS incident_id, i.status AS incident_status, "
        "i.n_obs AS incident_n, i.fixed_source AS incident_fixed "
        "FROM observations o LEFT JOIN incident_observations io ON io.observation_id = o.id "
        "LEFT JOIN incidents i ON i.id = io.incident_id WHERE o.observed_at >= ?"
    )
    params: list = [since]
    if bbox:
        try:
            west, south, east, north = (float(v) for v in bbox.split(","))
        except ValueError:
            raise HTTPException(422, "bbox debe ser west,south,east,north") from None
        sql += " AND o.lon BETWEEN ? AND ? AND o.lat BETWEEN ? AND ?"
        params += [west, east, south, north]
    if reliable:
        sql += " AND o.confidence IN ('alta','nominal','media')"
    rows = svc.db.query(sql + " ORDER BY o.observed_at DESC LIMIT ?", tuple(params + [OBSERVATIONS_LIMIT + 1]))
    # Con LIMIT+1 se detecta el recorte sin otra consulta: la fila extra solo marca que hay más.
    truncated = len(rows) > OBSERVATIONS_LIMIT
    points = [_observation_public(row) for row in rows[:OBSERVATIONS_LIMIT]]
    return {
        "type": "observations",
        "hours": hours,
        "count": len(points),
        "data_as_of": svc.db.kv_get("last_ingest_at"),
        "explanation": "Detecciones térmicas satelitales: no son incendios confirmados ni perímetros.",
        "truncated": truncated,
        "limit": OBSERVATIONS_LIMIT,
        "points": points,
    }


def _incident_public(row: dict) -> dict:
    comuna = territory().by_code.get(row["comuna_code"])
    out = {
        k: row[k]
        for k in (
            "id",
            "status",
            "status_changed_at",
            "first_seen_at",
            "last_seen_at",
            "lat",
            "lon",
            "n_obs",
            "n_reliable",
            "max_frp",
            "comuna_code",
            "official_ref",
            "fixed_reason",
        )
    }
    out.update(
        {
            "sensors": [s.strip() for s in row["sensors"].split(",") if s.strip()],
            "fixed_source": bool(row["fixed_source"]),
            "bbox": [row["min_lon"], row["min_lat"], row["max_lon"], row["max_lat"]],
            "comuna": comuna.name if comuna else None,
            "region": comuna.region if comuna else None,
        }
    )
    return out


def _incident_hull(svc: Services, row: dict) -> list | None:
    """Huella aproximada del incidente (DET-10), cacheada por su estado: una detección nueva
    cambia `n_obs`/`last_seen_at` y la recalcula sola."""
    key = f"incident-hull:v1:{row['id']}:{row['n_obs']}:{row['last_seen_at']}"
    cached = svc.db.cache_get(key)
    if cached:
        return cached
    hull = incident_hull(incidents_mod.members(svc.db, row["id"]))
    if hull:
        svc.db.cache_set(key, hull, 86400 * 3)
    return hull


@router.get("/incidents")
def incidents(
    hours: int = Query(48, ge=1, le=24 * 14),
    include_fixed: bool = Query(False, description="Incluir fuentes de calor fijas probables (volcanes, industria)"),
    hulls: bool = Query(False, description="Agrega `hull` (huella aproximada) a los incidentes abiertos con ≥3 detecciones"),
    svc: Services = Depends(services),
):
    """Incidentes: detecciones agrupadas en espacio y tiempo, con su estado según la evidencia.

    FUEGO-12: solo sale lo que está en territorio chileno. Un incidente sin comuna
    (`comuna_code` nulo) no es un incendio de Chile y no se publica — sigue en la tabla,
    pero aquí no aparece — salvo que tenga `official_ref`: lo que informa CONAF no
    desaparece aunque su comuna no se haya podido emparejar.
    """
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    sql = "SELECT * FROM incidents WHERE last_seen_at >= ? AND (comuna_code IS NOT NULL OR official_ref IS NOT NULL)" + (
        "" if include_fixed else " AND fixed_source = 0"
    )
    rows = svc.db.query(sql + f" ORDER BY {STATUS_ORDER}, last_seen_at DESC LIMIT 500", (since,))
    items = [_incident_public(r) for r in rows]
    if hulls:
        for item, row in zip(items, rows):
            if row["status"] in incidents_mod.OPEN_STATES and row["n_obs"] >= 3:
                hull = _incident_hull(svc, row)
                if hull:
                    item["hull"] = hull
    return {
        "type": "incidents",
        "hours": hours,
        "count": len(rows),
        "data_as_of": svc.db.kv_get("last_ingest_at"),
        "explanation": incidents_mod.__doc__.split("\n\n")[0].strip(),
        "incidents": items,
    }


OFFICIAL_FIELDS = (
    "id",
    "name",
    "status",
    "status_raw",
    "started_at",
    "controlled_at",
    "extinguished_at",
    "area_ha",
    "lat",
    "lon",
    "comuna",
    "region",
    "ambito",
    "fuel",
    "fetched_at",
)


def official_source(svc: Services) -> dict:
    return {
        "name": conaf.FIRES_SOURCE,
        "url": conaf.FIRES_PAGE_URL,
        "note": "Incendios informados por CONAF, con su estado oficial. BRASA los muestra tal como los publica CONAF.",
    }


def recent_official(svc: Services, hours: int = 48) -> list[dict]:
    """Incendios informados por CONAF aún no extinguidos, o que empezaron o se extinguieron en las últimas `hours`."""
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = svc.db.query(
        "SELECT * FROM official_fires WHERE status != 'extinguido' OR started_at >= ? OR extinguished_at >= ? "
        "ORDER BY started_at DESC LIMIT 500",
        (since, since),
    )
    return [{k: r[k] for k in OFFICIAL_FIELDS} for r in rows]


@router.get("/official-fires")
def official_fires(hours: int = Query(48, ge=1, le=24 * 14), svc: Services = Depends(services)):
    fires = recent_official(svc, hours)
    return {"type": "official_fires", "count": len(fires), "source": official_source(svc), "fires": fires}


def _incident_timeline(inc: dict, members: list[dict], svc: Services) -> dict:
    """Reproducción hora a hora con el mismo motor de los casos históricos (huella, eventos, conteos)."""
    key = f"incident-tl:{inc['id']}:{inc['n_obs']}:{inc['last_seen_at']}:{cases_mod.TIMELINE_VERSION}"
    cached = svc.db.cache_get(key)
    if cached:
        return cached
    first, last = cases_mod.parse_utc(inc["first_seen_at"]), cases_mod.parse_utc(inc["last_seen_at"])
    start = first.replace(minute=0, second=0) - timedelta(hours=1)
    end = last.replace(minute=0, second=0) + timedelta(hours=2)
    pad = 0.05 + 0.2 * max(inc["max_lat"] - inc["min_lat"], inc["max_lon"] - inc["min_lon"])
    pseudo = {
        "start_utc": cases_mod.fmt(start),
        "end_utc": cases_mod.fmt(end),
        "bbox": [inc["min_lon"] - pad, inc["min_lat"] - pad, inc["max_lon"] + pad, inc["max_lat"] + pad],
    }
    timeline = cases_mod.build_timeline(pseudo, members)
    timeline["bbox"] = pseudo["bbox"]
    svc.db.cache_set(key, timeline, 86400 * 3)
    return timeline


def _incident_spread(svc: Services, row: dict) -> dict | None:
    """Escenario estimado de propagación del incidente con el clima guardado de su comuna (FUEGO-02).

    Usa el viento pronosticado que ya calcula `compute_risk` (`risk_hourly`, centro de la comuna)
    en la hora más cercana a ahora, y el FFMC del día (`fwi_daily`). No hace llamadas nuevas ni
    simula nada: sin comuna o sin esos datos devuelve None y la ficha simplemente no lo muestra.
    """
    code = row["comuna_code"]
    if code is None:
        return None
    today = datetime.now(CHILE_TZ).date().isoformat()
    fwi_row = svc.db.one("SELECT ffmc, date FROM fwi_daily WHERE comuna_code = ? ORDER BY date >= ? DESC, date LIMIT 1", (code, today))
    hourly = svc.db.one("SELECT payload FROM risk_hourly WHERE comuna_code = ?", (code,))
    if not fwi_row or not hourly:
        return None
    now = datetime.now(timezone.utc)
    best, gap = None, float("inf")
    for hour in json.loads(hourly["payload"]):
        if hour.get("wind") is None:
            continue
        try:
            t = datetime.fromisoformat(str(hour["time"]).replace("Z", "+00:00"))
        except ValueError:
            continue
        diff = abs((t - now).total_seconds())
        if diff < gap:
            best, gap = hour, diff
    if best is None:
        return None
    scenario = fwi.propagation_scenario(fwi_row["ffmc"], best["wind"], best.get("dir"))
    if scenario is None:
        return None
    return {
        **scenario,
        "wind_at": best["time"],
        "ffmc_date": fwi_row["date"],
        "assumptions": [
            f"Viento y combustible fino (FFMC) del centro de la comuna, no del punto exacto "
            f"del fuego; viento del pronóstico de las {str(best['time'])[11:16]} UTC."
        ]
        + scenario["assumptions"],
        "note": "Escenario estimado con las condiciones de ahora: no es una predicción ni el perímetro del incendio.",
    }


@router.get("/incidents/{incident_id}")
def incident_detail(incident_id: str, svc: Services = Depends(services)):
    if not INCIDENT_ID.match(incident_id):
        raise HTTPException(404, "Incidente no encontrado.")
    row = svc.db.one("SELECT * FROM incidents WHERE id = ?", (incident_id,))
    if row is None:
        # Un enlace viejo de un aviso puede traer un id ya fusionado: se sigue el alias.
        row = incidents_mod.resolve_merge(svc.db, incident_id)
        if row:
            incident_id = row["id"]
    if not row:
        raise HTTPException(404, "Incidente no encontrado (puede haberse unido a otro o ya no tener detecciones guardadas).")
    members = incidents_mod.members(svc.db, incident_id)
    evidence, delays = [], {}
    for m in members:
        delay = (cases_mod.parse_utc(m["ingested_at"]) - cases_mod.parse_utc(m["observed_at"])).total_seconds() / 60
        delay = max(0, round(delay))
        delays.setdefault(m.get("sensor") or "?", []).append(delay)
        evidence.append(
            {
                k: m.get(k)
                for k in (
                    "id",
                    "observed_at",
                    "ingested_at",
                    "source",
                    "sensor",
                    "satellite",
                    "lat",
                    "lon",
                    "frp_mw",
                    "confidence",
                    "resolution_m",
                )
            }
            | {"delay_min": delay}
        )
    latency = {sensor: {"n": len(v), "p50_min": round(statistics.median(v)), "max_min": max(v)} for sensor, v in delays.items()}
    timeline = _incident_timeline(row, members, svc) if members else None
    official = svc.db.one("SELECT * FROM official_fires WHERE id = ?", (row["official_ref"],)) if row["official_ref"] else None
    protected = protected_areas_near(row["lat"], row["lon"])
    # OFI-17: el perímetro oficial llega a `kv` desde la ingesta (tras CONAF_PERIMETRO_ENABLED);
    # aquí solo se lee lo último válido. Sin dato guardado la ficha se muestra igual, sin la huella.
    perimeter = None
    if row["official_ref"]:
        try:
            perimeter = json.loads(svc.db.kv_get(f"perimetro:{row['official_ref']}") or "{}").get("perimeter")
        except ValueError:
            perimeter = None
    return {
        "incident": _incident_public(row),
        "protected_area": protected[0] if protected else None,
        "spread": _incident_spread(svc, row),
        "official_fire": {k: official[k] for k in OFFICIAL_FIELDS} if official else None,
        "official_source": official_source(svc),
        "evidence": evidence[-300:],
        "evidence_total": len(evidence),
        "official_perimeter": perimeter,
        "latency": latency,
        "timeline": timeline,
        "data_as_of": svc.db.kv_get("last_ingest_at"),
        "official": (
            "BRASA no es fuente oficial. Un incidente agrupa detecciones satelitales: puede ser un incendio, "
            "una quema o una industria. Sigue a SENAPRED y CONAF."
        ),
    }


@router.get("/explore")
async def explore(
    request: Request,
    zone: str = "chile",
    mode: Literal["recent", "historical"] = "recent",
    days: int = Query(3, ge=1, le=10),
    start: date | None = None,
    svc: Services = Depends(services),
):
    """Consulta directa a FIRMS por zona y ventana (reciente o histórica).

    Tope diario por IP: cada consulta gasta cuota de la cuenta FIRMS del servidor y una sola
    persona no debe poder agotarla. El aviso llega con su propio código para que la interfaz
    lo explique en vez de mostrar un error genérico.
    """
    limit = svc.settings.explore_daily_limit
    limiter.check(
        request,
        "explore",
        limit,
        86400,
        status_code=422,
        code="EXPLORE_DAILY_LIMIT",
        message=(
            f"Llegaste al tope de {limit} {'consulta diaria' if limit == 1 else 'consultas diarias'} "
            "al archivo satelital. El mapa de incidentes y el de riesgo siguen disponibles; "
            "el cupo se renueva a medianoche."
        ),
    )
    zones = territory().zones()
    if zone not in zones:
        raise HTTPException(422, "Zona no disponible.")
    today = datetime.now(timezone.utc).date()
    if mode == "historical" and not start:
        raise HTTPException(422, "En modo histórico debes indicar la fecha de inicio (AAAA-MM-DD).")
    if mode == "recent" and start:
        raise HTTPException(422, "El modo reciente no admite fecha de inicio.")
    if start and start > today:
        raise HTTPException(422, "La fecha de inicio no puede estar en el futuro.")
    if start and start < date(2000, 11, 1):
        raise HTTPException(422, "No hay archivo satelital FIRMS anterior a noviembre de 2000.")
    key = svc.settings.firms_map_key
    if not key:
        raise HTTPException(503, {"code": "FIRMS_KEY_MISSING", "message": "Este servidor aún no tiene acceso al archivo de NASA FIRMS."})
    notices: list[str] = []
    end = None
    query_start = start
    if mode == "recent":
        sources = svc.settings.firms_sources
        if days > firms.MAX_DAYS_PER_REQUEST:  # la API admite 5 días por solicitud: se consulta por tramos
            query_start, end = today - timedelta(days=days - 1), today
    else:
        end = min(start + timedelta(days=days - 1), today)
        if end < start + timedelta(days=days - 1):
            notices.append(f"La ventana se recortó a hoy ({end.isoformat()}).")
        if (today - start).days <= RECENT_ARCHIVE_DAYS:
            sources = svc.settings.firms_sources
            notices.append("Fecha reciente: se usan productos NRT (el archivo científico SP tarda meses en publicarse).")
        else:
            sources = firms.sources_for(("VIIRS_NOAA20_SP", "VIIRS_SNPP_SP", "MODIS_SP"), start, end)
    bbox = zones[zone]["bbox"]
    cache_key = f"explore:{zone}:{mode}:{days}:{start}:{','.join(sources)}"
    cached = svc.db.cache_get(cache_key)
    if cached:
        return cached
    try:
        points, provider_notices = await firms.fetch_hotspots(
            key, bbox, sources, days=min(days, firms.MAX_DAYS_PER_REQUEST), start=query_start, end=end, client=svc.client
        )
    except firms.UpstreamError as exc:
        raise HTTPException(502, str(exc)) from None
    t = territory()
    for p in points:
        comuna = t.locate(p["lat"], p["lon"], tolerance_deg=firms.COASTAL_TOLERANCE_DEG)
        p["comuna_code"], p["comuna"], p["region"] = (comuna.code, comuna.name, comuna.region) if comuna else (None, None, None)
    in_chile = sum(1 for p in points if p["comuna_code"] is not None)
    payload = {
        "type": "hotspots",
        "mode": mode,
        "zone": zone,
        "days": days,
        "start": start.isoformat() if start else None,
        "end": end.isoformat() if end else None,
        "sources": list(sources),
        "retrieved_at_utc": stamp(),
        "notices": notices + provider_notices,
        "in_chile": in_chile,
        "outside_chile": len(points) - in_chile,
        "explanation": "Detecciones térmicas satelitales, no incendios confirmados ni perímetros.",
        "points": points,
    }
    svc.db.cache_set(cache_key, payload, 900 if mode == "recent" else 86400 * 7)
    return payload


def boton_rojo_source(svc: Services) -> dict:
    return {
        "name": conaf.SOURCE,
        "url": conaf.DASHBOARD_URL,
        "fetched_at": svc.db.kv_get("boton_rojo_at"),
        "note": (
            "Pronóstico oficial de CONAF de condiciones favorables para incendios. No indica un incendio. "
            "Información propiedad de CONAF; BRASA la muestra sin modificarla, resumida por comuna."
        ),
    }


def conaf_condiciones_source(svc: Services) -> dict:
    return {
        "name": conaf.CONDICIONES_SOURCE,
        "url": conaf.CONDICIONES_DASHBOARD_URL,
        "fetched_at": svc.db.kv_get("conaf_cond_at"),
        "note": (
            "Pronóstico oficial de CONAF (probabilidad de ignición, humedad del combustible, viento, "
            "humedad del aire y temperatura), resumido por comuna desde la grilla de ~2 km del "
            "Departamento de Desarrollo e Investigación de GEPRIF. Información propiedad de CONAF: "
            "se muestra con su nombre, separada del cálculo propio de BRASA."
        ),
    }


def fwi_source(svc: Services) -> dict:
    return {
        "name": "BRASA · FWI (sistema canadiense)",
        "url": fwi.SOURCE_URL,
        "fetched_at": svc.db.kv_get("fwi_computed_at"),
        "reference": fwi.SOURCE,
        "note": (
            "Índice de peligro calculado por BRASA con 60 días de temperatura, humedad, viento y lluvia de "
            "Open-Meteo en el centro de cada comuna. Estima qué tan rápido crecería un incendio, no dónde "
            "habrá uno. Se muestra junto al 30-30-30, no en su reemplazo."
        ),
    }


@router.get("/risk")
def risk_map(day: date | None = None, svc: Services = Depends(services)):
    day = day or datetime.now(CHILE_TZ).date()
    rows = svc.db.query("SELECT * FROM risk_daily WHERE date = ?", (day.isoformat(),))
    dates = [
        r["date"]
        for r in svc.db.query(
            "SELECT DISTINCT date FROM risk_daily WHERE date >= ? ORDER BY date LIMIT 8", ((datetime.now(CHILE_TZ).date()).isoformat(),)
        )
    ]
    worst = svc.db.query(
        "SELECT date, SUM(level = 'extremo') AS extremo, SUM(level = 'alto') AS alto, SUM(level = 'moderado') AS moderado "
        "FROM risk_daily WHERE date >= ? GROUP BY date ORDER BY date LIMIT 8",
        (datetime.now(CHILE_TZ).date().isoformat(),),
    )
    br = svc.db.query("SELECT comuna_code, hours, area_ha, proportion FROM boton_rojo WHERE date = ?", (day.isoformat(),))
    fwi_rows = svc.db.query("SELECT * FROM fwi_daily WHERE date = ?", (day.isoformat(),))
    return {
        "date": day.isoformat(),
        "dates": dates,
        "summary": worst,
        "boton_rojo": {str(r["comuna_code"]): {"hours": r["hours"], "area_ha": r["area_ha"], "proportion": r["proportion"]} for r in br},
        "boton_rojo_source": boton_rojo_source(svc),
        "fwi": {
            str(r["comuna_code"]): {
                "fwi": r["fwi"],
                "level": r["level"],
                "ffmc": r["ffmc"],
                "dmc": r["dmc"],
                "dc": r["dc"],
                "isi": r["isi"],
                "bui": r["bui"],
            }
            for r in fwi_rows
        },
        "fwi_source": fwi_source(svc),
        "dmc": dmc_by_comuna(svc),
        "dmc_source": dmc_source(svc),
        "rain": rain_by_comuna(svc),
        "rain_source": rain_source(svc),
        "computed_at": svc.db.kv_get("risk_computed_at"),
        # Frescura de la ingesta satelital: la misma marca que usa el pill de la cabecera.
        "data_as_of": svc.db.kv_get("last_ingest_at"),
        "method": (
            "Regla 30-30-30 evaluada hora a hora: temperatura >30 °C, humedad <30 % y viento >30 km/h "
            "(Open-Meteo, centro de cada comuna). El nivel de condiciones combina el 30-30-30 con el FWI "
            "del mismo día: manda el más alto, y si los dos llegan a «alto» sube un paso. Los dos índices "
            "se muestran por separado, uno no reemplaza al otro."
        ),
        "comunas": {
            str(r["comuna_code"]): {
                "level": r["level"],
                "score": r["score"],
                "h3": r["hours_3of3"],
                "h2": r["hours_2of3"],
                "tmax": r["tmax"],
                "rhmin": r["rhmin"],
                "windmax": r["windmax"],
                "gustmax": r["gustmax"],
                "level_combined": r["level_combined"],
                "fwi": r["fwi"],
                "fwi_level": r["fwi_level"],
                "reasons": json.loads(r["reasons"]) if r["reasons"] else [],
            }
            for r in rows
        },
    }


AIR_TTL_S = 3 * 3600  # CAMS se actualiza dos veces al día; 3 h por comuna basta
AIR_TIMEOUT_S = 8.0  # la ficha no espera más que esto al proveedor de aire


async def air_for_comuna(svc: Services, comuna: Any) -> dict[str, Any] | None:
    """MP2,5 pronosticado (CAMS vía Open-Meteo) para hoy y mañana en la comuna; None si falla.

    Best-effort: el proveedor de aire nunca debe tumbar ni demorar la ficha de riesgo,
    así que cualquier fallo o espera larga devuelve None y la vista simplemente no la pinta.
    """
    key = f"air:{comuna.code}"
    raw = svc.db.kv_get(key)
    if raw:
        try:
            cached = json.loads(raw)
            fetched = datetime.fromisoformat(str(cached["fetched_at"]).replace("Z", "+00:00"))
            if (datetime.now(timezone.utc) - fetched).total_seconds() < AIR_TTL_S:
                return cached
        except (TypeError, ValueError, KeyError):
            pass  # caché ilegible: se pide de nuevo
    lon, lat = comuna.center
    try:
        series = await asyncio.wait_for(weather.air_quality(svc.client, lat, lon), AIR_TIMEOUT_S)
    except Exception:  # best-effort: la ficha no depende del proveedor de aire
        return None
    daily = weather.air_daily_max(series)
    today = datetime.now(CHILE_TZ).date()
    today_max = daily.get(today.isoformat())
    tomorrow_max = daily.get((today + timedelta(days=1)).isoformat())
    if today_max is None and tomorrow_max is None:
        return None
    payload = {
        "pm25_today_max": today_max,
        "pm25_tomorrow_max": tomorrow_max,
        "unit": "µg/m³",
        "source": {"name": "CAMS vía Open-Meteo", "url": "https://open-meteo.com/en/docs/air-quality-api"},
        "guideline": {
            "pm25_24h": 15,
            "name": "Guía OMS 2021",
            "url": "https://www.who.int/es/news-room/fact-sheets/detail/ambient-(outdoor)-air-quality-and-health",
        },
        "fetched_at": stamp(),
    }
    svc.db.kv_set(key, json.dumps(payload, ensure_ascii=False))
    return payload


@router.get("/risk/{code}")
async def risk_comuna(code: int, svc: Services = Depends(services)):
    comuna = territory().by_code.get(code)
    if not comuna:
        raise HTTPException(404, "Comuna no encontrada.")
    today = datetime.now(CHILE_TZ).date().isoformat()
    days = svc.db.query("SELECT * FROM risk_daily WHERE comuna_code = ? AND date >= ? ORDER BY date", (code, today))
    hourly = svc.db.one("SELECT computed_at, payload FROM risk_hourly WHERE comuna_code = ?", (code,))
    br = svc.db.query(
        "SELECT date, hours, area_ha, proportion FROM boton_rojo WHERE comuna_code = ? AND date >= ? ORDER BY date", (code, today)
    )
    fwi_days = svc.db.query("SELECT * FROM fwi_daily WHERE comuna_code = ? AND date >= ? ORDER BY date", (code, today))
    cond = svc.db.query(
        "SELECT date, var, label, cells, cells_total FROM conaf_condiciones WHERE comuna_code = ? AND date >= ? ORDER BY date, var",
        (code, today),
    )
    return {
        "comuna": comuna.as_dict(),
        "days": days,
        "boton_rojo": br,
        "boton_rojo_source": boton_rojo_source(svc),
        "conaf_condiciones": cond,
        "conaf_condiciones_source": conaf_condiciones_source(svc),
        "fwi_days": fwi_days,
        "fwi_source": fwi_source(svc),
        "rain": rain_for_comuna(svc, code),
        "rain_source": rain_source(svc),
        "dmc_alerts": dmc_for_comuna(svc, code),
        "dmc_source": dmc_source(svc),
        "air": await air_for_comuna(svc, comuna),
        "data_as_of": svc.db.kv_get("last_ingest_at"),
        "hours": json.loads(hourly["payload"]) if hourly else [],
        "computed_at": hourly["computed_at"] if hourly else None,
    }


@router.get("/risk/{code}/trend")
def risk_trend(code: int, weeks: int = Query(1, ge=1, le=8), svc: Services = Depends(services)):
    """Comparador: el pronóstico de hoy contra el que se emitió `weeks` semanas antes.

    Para cada día pronosticado se busca la foto del pronóstico emitida exactamente `weeks * 7`
    días antes de ese día. Sin foto previa la fila dice «sin anterior»: no se inventa una
    comparación con un dato que no existe.
    """
    comuna = territory().by_code.get(code)
    if not comuna:
        raise HTTPException(404, "Comuna no encontrada.")
    today = datetime.now(CHILE_TZ).date().isoformat()
    current = {
        r["date"]: {"level": r["level"], "level_combined": r["level_combined"], "score": r["score"]}
        for r in svc.db.query(
            "SELECT date, level, level_combined, score FROM risk_daily WHERE comuna_code = ? AND date >= ?", (code, today)
        )
    }
    previous: dict[str, dict] = {}
    offset_days = weeks * 7
    for r in svc.db.query(
        "SELECT snapshot_date, target_date, level, level_combined, score FROM risk_snapshot "
        "WHERE comuna_code = ? ORDER BY snapshot_date DESC",
        (code,),
    ):
        if (date.fromisoformat(r["target_date"]) - date.fromisoformat(r["snapshot_date"])).days != offset_days:
            continue
        previous.setdefault(
            r["target_date"],
            {"level": r["level"], "level_combined": r["level_combined"], "score": r["score"], "snapshot_date": r["snapshot_date"]},
        )
    rows = [trend_mod.row(target, current.get(target), previous.get(target)) for target in sorted(set(current) | set(previous))]
    return {
        "comuna": comuna.as_dict(),
        "weeks": weeks,
        "rows": rows,
        "summary": trend_mod.summarize(rows),
        "snapshots_from": min((p["snapshot_date"] for p in previous.values()), default=None),
        "method": (
            "Se compara el pronóstico de hoy para cada día con el que se emitió siete días antes "
            "para ese mismo día. Mide cómo cambió la expectativa, no lo que ocurrió."
        ),
    }


@router.get("/weather")
async def current_weather(
    lat: float = Query(..., ge=-90, le=90), lon: float = Query(..., ge=-180, le=180), svc: Services = Depends(services)
):
    """Condiciones actuales MODELADAS (Open-Meteo) en un punto."""
    cache_key = f"weather:{lat:.2f}:{lon:.2f}"
    cached = svc.db.cache_get(cache_key)
    if cached:
        return cached
    try:
        data = await weather.current(svc.client, lat, lon)
    except weather.WeatherError as exc:
        raise HTTPException(502, "El proveedor meteorológico no respondió.") from exc
    payload = {"source": "Open-Meteo", "kind": "modelled_current_weather", "coordinates": [lon, lat], **data}
    svc.db.cache_set(cache_key, payload, 600)
    return payload


@router.get("/locate")
def locate(lat: float = Query(..., ge=-90, le=90), lon: float = Query(..., ge=-180, le=180), svc: Services = Depends(services)):
    comuna = territory().locate(lat, lon)
    if not comuna:
        return {"comuna": None}
    today = datetime.now(CHILE_TZ).date().isoformat()
    risk = svc.db.one("SELECT level, score, tmax, rhmin, windmax FROM risk_daily WHERE comuna_code = ? AND date = ?", (comuna.code, today))
    return {"comuna": comuna.as_dict(), "risk_today": risk}


@router.get("/priority-comunas")
def priority_comunas():
    from backend.settings import ROOT

    return json.loads((ROOT / "web" / "data" / "prioritarias.json").read_text(encoding="utf-8"))


@router.get("/quality/feedback")
def quality_feedback(response: Response, svc: Services = Depends(services)):
    """¿Sirvieron los avisos? La opinión de todas las personas como agregado (ALR-05 → QA-05).

    Solo conteos globales: nada por dispositivo, lugar, comuna ni aviso. `since` es el
    `created_at` del aviso opinado más antiguo (nulo si aún nadie responde).
    """
    response.headers["Cache-Control"] = "public, max-age=60"
    counts = {"sirvio": 0, "no_sirvio": 0, "quema": 0}
    for row in svc.db.query("SELECT feedback AS f, COUNT(*) AS n FROM alerts WHERE feedback IS NOT NULL GROUP BY feedback"):
        if row["f"] in counts:
            counts[row["f"]] = row["n"]
    since = svc.db.one("SELECT MIN(created_at) AS t FROM alerts WHERE feedback IS NOT NULL")["t"]
    return {"total": sum(counts.values()), "counts": counts, "since": since}

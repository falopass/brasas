"""Armado de `/api/status` fuera del bucle de eventos (OPS-813).

La ruta solo orquesta: este módulo reúne todas las lecturas a la base en una función
síncrona que corre con `asyncio.to_thread`, así las consultas no congelan las demás
rutas mientras la tabla de corridas es grande. Cada agregado se calcula una sola vez
y se comparte: `diagnostics.productos` alimenta `runs`, la última corrida buena, la
racha de fallos, el `history` y los `goes_sweeps`; la consulta de `observations`
alimenta `newest_observation` y `desfase`; y `kv` se lee una vez para `last_cycle`,
respaldo y `last_ingest_at`. `firms_quota` vuelve con la ruta: su refresco es asyncio.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from backend import diagnostics, freshness
from backend.geo import territory
from backend.providers import goes, weather
from backend.tiempo import stamp, utcnow

if TYPE_CHECKING:
    from backend.services import Services

CHILE_TZ = ZoneInfo("America/Santiago")
GOES_SWEEPS = 6  # barridos que se muestran en /api/status para poder ver huecos (DET-13)


def build(svc: Services, history: int, coverage: bool) -> dict[str, Any]:
    """Cuerpo de /api/status, menos `firms_quota` (ese refresco corre en la corrutina de la ruta)."""
    db = svc.db
    now = utcnow()
    # Una pasada por producto alimenta runs, la última buena, las recientes (racha de
    # fallos y `history`) y los `goes_sweeps`: `n` cubre el mayor de los tres.
    n = max(GOES_SWEEPS, diagnostics.CORRIDAS_VENTANA, history)
    data = diagnostics.productos(db, n)
    runs = sorted(
        (
            {
                "provider": corrida["provider"],
                "product": corrida["product"],
                "started_at": corrida["started_at"],
                "finished_at": corrida["finished_at"],
                "ok": bool(corrida["ok"]),
                "n_records": corrida["n_records"],
                "n_new": corrida["n_new"],
                "message": corrida["message"],
                "last_ok_at": data[corrida["product"]]["last_ok_at"],
            }
            for corrida in (data[product]["corridas"][0] for product in data)
        ),
        key=lambda row: (row["provider"], row["product"]),
    )
    recent: dict[str, list[dict[str, Any]]] = {}
    if history:
        for product in sorted(data):
            recent[product] = [
                {"ok": bool(r["ok"]), "started_at": r["started_at"]} for r in data[product]["corridas"][:history]
            ]
    # DET-13: el hueco se deriva en el servidor (como `freshness`) para que la interfaz no repita
    # la aritmética: GOES-19 entrega un disco completo cada 10 min, así que se esperan
    # GOES_SWEEPS barridos `ok` en la última hora. La ventana se cuenta por la hora del barrido,
    # guardada en `source_ref` (la clave S3), no por `started_at`: el relleno inicial ingiere
    # barridos de hasta 6 horas atrás con la marca de ahora y los contaría como recientes.
    since = now - timedelta(hours=1)
    goes_ok = sum(
        1
        for row in db.query(
            "SELECT DISTINCT source_ref FROM ingest_runs WHERE provider = 'NOAA GOES' AND product LIKE '%FDCF%' AND ok = 1 "
            "AND started_at >= ?",
            (stamp(since),),
        )
        # `source_ref` puede ser NULL en corridas viejas o de prueba: key_start no acepta None.
        if (start := goes.key_start(row["source_ref"] or "")) is not None and start >= since
    )
    goes_missing = max(0, GOES_SWEEPS - goes_ok)
    # DET-13: todos los barridos de GOES comparten producto, así que «la última ejecución»
    # esconde un hueco en medio. Salen de la misma pasada por producto: FDCF vive en uno o
    # dos productos (GOES<sat>_FDCF y ABI-L2-FDCF) y con `n >= GOES_SWEEPS` corridas por
    # producto la unión conserva el mismo top global.
    goes_sweeps = [
        {"source_ref": r["source_ref"], "ok": bool(r["ok"]), "started_at": r["started_at"]}
        for r in sorted(
            (
                r
                for d in data.values()
                for r in d["corridas"][:GOES_SWEEPS]
                if r["provider"] == "NOAA GOES" and "FDCF" in (r["product"] or "")
            ),
            key=lambda r: r["id"],
            reverse=True,
        )[:GOES_SWEEPS]
    ]
    # Una sola lectura para todas las marcas del kv (antes eran diez `kv_get`, varias repetidas).
    kv = db.kv_many([
        "backup_bytes", "work_backup_bytes", "last_ingest_at", "last_cycle", "backup_at",
        "work_backup_at", "backup_reason", "risk_computed_at",
    ])
    # Una sola pasada por fuente alimenta `newest_observation` y el `desfase` del bloque de errores.
    obs_rows = db.query("SELECT source, MAX(observed_at) AS t FROM observations GROUP BY source ORDER BY source")
    newest = {r["source"]: r["t"] for r in obs_rows}
    try:
        errors, failures = diagnostics.status_blocks(
            db,
            since=stamp(now - timedelta(hours=diagnostics.WINDOW_H)),
            last_cycle=kv["last_cycle"],
            desfase_data=diagnostics.desfase(db, now=now, kv_last_ingest_at=kv["last_ingest_at"], newest=obs_rows),
        )
    except Exception:
        errors = {"error": True}
        failures = {"error": True}
    backup_bytes = kv["backup_bytes"]
    work_bytes = kv["work_backup_bytes"]
    coverage_data = None
    if coverage:
        # OPS-19: cobertura de FWI, DMC y lluvia para que el diagnóstico de producción compare
        # contra las 345 comunas sin abrir la base.
        today_cl = datetime.now(CHILE_TZ).date().isoformat()
        coverage_row = db.one(
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
    # DET-51: una sola lectura entrega los abiertos por estado y las fuentes fijas refrescadas en 24 h.
    incidents_by_status = db.query(
        "SELECT status, fixed_source, COUNT(*) AS n, SUM(CASE WHEN updated_at >= ? THEN 1 ELSE 0 END) AS recent "
        "FROM incidents GROUP BY status, fixed_source",
        (stamp(now - timedelta(hours=24)),),
    )
    # FUEGO-08: frescura por familia (última corrida buena y racha de fallos), para que una
    # fuente caída no siga saliendo como «al día» por la sola marca del ciclo.
    productos = freshness.productos_por_fuente(
        diagnostics._recientes(data), {product: d["last_ok_at"] for product, d in data.items()}
    )
    # El pronóstico (cada 3 h) también prueba contacto con Open-Meteo: el FWI corre una vez al
    # día y la lluvia cada 6 h, así que sin esta marca la familia se declararía vieja en falso.
    if kv["risk_computed_at"]:
        om = productos.setdefault("Open-Meteo", {"last_ok_at": None, "fallos_seguidos": 0})
        if om["last_ok_at"] is None or kv["risk_computed_at"] > om["last_ok_at"]:
            om["last_ok_at"] = kv["risk_computed_at"]
    return {
        "time_utc": stamp(),
        "last_ingest_at": kv["last_ingest_at"],
        # Contrato de frescura: la regla de los 30 minutos vive en el servidor (backend/freshness.py)
        # para que la interfaz no repita la aritmética ni invente otro umbral.
        "freshness": freshness.status(kv["last_ingest_at"], products=productos),
        # El resumen se lee de la base: en Cloudflare el contenedor se suspende entre disparos del
        # cron y la copia en memoria se pierde (quedaba en null aunque los ciclos sí corrieran).
        "last_cycle": json.loads(kv["last_cycle"]) if kv["last_cycle"] else svc.last_cycle,
        # OPS-18: tamaño comprimido de los respaldos (lo registra backend/storage.py tras cada subida).
        "backup": {
            "bytes": int(backup_bytes) if backup_bytes else None,
            "updated_at": kv["backup_at"],
            "work_bytes": int(work_bytes) if work_bytes else None,
            "work_updated_at": kv["work_backup_at"],
            # OPS-44: por qué falló el último respaldo (null si subió o aún no se intentó).
            "reason": kv["backup_reason"] or ("sin_credenciales" if not svc.persistence.enabled else None),
        },
        **({"history": recent} if history else {}),
        "risk_computed_at": kv["risk_computed_at"],
        **({"coverage": coverage_data} if coverage_data is not None else {}),
        "scheduler_enabled": svc.settings.scheduler_enabled,
        # "interna": tareas en este proceso · "cron": la dispara un programador externo (Cloudflare) · "apagada"
        "ingest_mode": "interna" if svc.settings.scheduler_enabled else "cron" if svc.settings.internal_token else "apagada",
        "firms_configured": bool(svc.settings.firms_map_key),
        "runs": runs,
        "goes_sweeps": goes_sweeps,
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
        # DET-51: cuántos incidentes siguen marcados como fuente fija y se refrescaron en 24 h,
        # para auditar que la supresión no tape de más. Sale de la misma consulta que
        # `incidents_open`: /api/status no suma lecturas por este campo.
        "fixed_source_24h": sum(r["recent"] for r in incidents_by_status if r["fixed_source"] == 1),
        "incidents_open": {
            r["status"]: r["n"] for r in incidents_by_status if r["fixed_source"] == 0 and r["status"] not in ("extinguido", "descartado")
        },
        # OPS-813: cuándo arrancó este proceso y cuánto tardó en quedar listo (territorio +
        # restauración del respaldo), para medir el arranque en frío desde la calle.
        "process": {"started_at": svc.process_started_at, "startup_ms": svc.startup_ms},
    }

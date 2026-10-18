"""Servicios compartidos y tareas de ingesta: observaciones → base local → alertas → notificaciones."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from backend import alerts as alerts_mod
from backend import fwi as fwi_mod
from backend import incidents as incidents_mod
from backend import rain as rain_mod
from backend import risk as risk_mod
from backend.db import Database
from backend.geo import territory
from backend.notify import telegram, webpush
from backend.providers import conaf, dmc, firms, goes, weather
from backend.settings import Settings
from backend.storage import Persistence, RemoteStorage
from shapely.geometry import Polygon

log = logging.getLogger("brasa")
CHILE_BBOX = [-81.5, -56.5, -66.0, -17.0]
RETENTION_DAYS = 45
BOTON_ROJO_EVERY_H = 3
DMC_EVERY_H = 1
RAIN_EVERY_H = 6
RAIN_CELL_DEG = 0.5   # las normales se piden por celda de 0,5° (~55 km), no por comuna
RAIN_PAUSE_S = 15     # medido: 194 KB por celda cada 15 s queda bajo el límite por minuto de Open-Meteo


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def stamp(moment: datetime | None = None) -> str:
    return (moment or utcnow()).strftime("%Y-%m-%dT%H:%M:%SZ")


class Services:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.settings = settings
        self.db = Database(settings.db_path)
        self.client = client or httpx.AsyncClient(timeout=40.0, headers={"User-Agent": "BRASA-Chile/0.2 (+prototipo ciudadano)"})
        self.tasks: list[asyncio.Task] = []
        self._lock = asyncio.Lock()
        self._backfilled = False
        self._tick_task: asyncio.Task | None = None
        self.last_cycle: dict[str, Any] | None = None
        self._public_url = settings.public_base_url
        self.storage = RemoteStorage(settings.storage_url, self.client, settings.internal_token) if settings.storage_url else None
        self.persistence = Persistence(self.db, self.storage)
        self.db.on_user_write = self.persistence.mark_dirty

    async def start(self) -> None:
        """Restaura el respaldo (si hay almacenamiento remoto) y lanza las tareas que correspondan."""
        if self.persistence.enabled:
            try:
                await self.persistence.restore()
            except Exception as exc:  # sin respaldo accesible se sigue, pero se registra
                log.error("No se pudo restaurar el respaldo: %s", exc)
            self.persistence.start()
        if self.public_url:
            await self.register_webhook()
        if self.settings.scheduler_enabled:
            self.start_background()

    @property
    def public_url(self) -> str:
        return self._public_url

    async def learn_public_url(self, url: str) -> None:
        """Sin PUBLIC_BASE_URL, se toma de la primera visita por HTTPS (p. ej. *.workers.dev)."""
        if self._public_url or not url.startswith("https://"):
            return
        self._public_url = url.rstrip("/")
        log.info("Dirección pública detectada: %s", self._public_url)
        await self.register_webhook()

    async def register_webhook(self) -> None:
        if not (self.settings.telegram_bot_token and self.settings.telegram_webhook_secret and self._public_url):
            return
        try:
            await telegram.set_webhook(self.client, self.settings.telegram_bot_token,
                                       f"{self._public_url}/api/telegram/webhook", self.settings.telegram_webhook_secret)
        except RuntimeError as exc:
            log.warning("No se pudo registrar el webhook de Telegram: %s", exc)

    async def close(self) -> None:
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        await self.persistence.stop()
        await self.client.aclose()

    async def tick(self) -> dict[str, Any]:
        """Un ciclo completo disparado desde afuera (Cron Trigger de Cloudflare)."""
        result: dict[str, Any] = {}
        if self.persistence.enabled and not self.persistence.ready:
            try:
                result["restored"] = await self.persistence.restore()
            except Exception as exc:
                result["restore_error"] = str(exc)
        if not self._backfilled:
            self._backfilled = True
            try:
                result["backfill"] = await self.backfill_goes()
            except Exception as exc:
                result["backfill_error"] = str(exc)
        result.update(await self.ingest_cycle())
        risk_every = self.settings.risk_interval_min * 60
        # El FWI primero: compute_risk combina su nivel con el 30-30-30 del mismo día.
        if self.due("fwi_computed_at", risk_every):
            try:
                result["fwi_comunas"] = await self.compute_fwi()
            except Exception as exc:
                result["fwi_error"] = str(exc)[:200]
        last = self.db.one("SELECT MAX(computed_at) AS t FROM risk_daily")["t"]
        due = not last or (utcnow() - datetime.fromisoformat(last.replace("Z", "+00:00"))).total_seconds() >= risk_every
        if due:
            try:
                result["risk_comunas"] = await self.compute_risk()
            except Exception as exc:
                result["risk_error"] = str(exc)
        if self.due("dmc_at", DMC_EVERY_H * 3600):
            try:
                result["dmc_alerts"] = await self.ingest_dmc()
            except Exception as exc:
                result["dmc_error"] = str(exc)[:200]
        if self.due("rain_computed_at", RAIN_EVERY_H * 3600):
            try:
                result["rain_comunas"] = await self.compute_rain_anomaly()
            except Exception as exc:
                result["rain_error"] = str(exc)[:200]
        try:
            result.update(await self.ingest_official_fires())
        except Exception as exc:
            result["official_error"] = str(exc)[:200]
        if self.boton_rojo_due():
            try:
                result["boton_rojo"] = await self.ingest_boton_rojo()
            except Exception as exc:
                result["boton_rojo_error"] = str(exc)[:200]
        return result

    # ------------------------------------------------------------------ observaciones
    def store_observations(self, observations: list[dict[str, Any]], run_id: int) -> list[dict[str, Any]]:
        """Inserta observaciones nuevas (idempotente) y les asigna comuna. Devuelve solo las nuevas."""
        t = territory()
        new: list[dict[str, Any]] = []
        now = stamp()
        with self.db.connect() as conn:
            for obs in observations:
                comuna = t.locate(obs["lat"], obs["lon"])
                obs["comuna_code"] = comuna.code if comuna else None
                cursor = conn.execute(
                    "INSERT OR IGNORE INTO observations(id, source, sensor, satellite, resolution_m, lat, lon, observed_at, "
                    "frp_mw, brightness_k, confidence, confidence_raw, comuna_code, run_id, ingested_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (obs["id"], obs["source"], obs.get("sensor"), obs.get("satellite"), obs.get("resolution_m"),
                     obs["lat"], obs["lon"], obs["observed_at"], obs.get("frp_mw"), obs.get("brightness_k"),
                     obs.get("confidence"), obs.get("confidence_raw"), obs["comuna_code"], run_id, now))
                if cursor.rowcount:
                    new.append(obs)
        return new

    def start_run(self, provider: str, product: str, source_ref: str) -> int:
        return self.db.insert("INSERT INTO ingest_runs(provider, product, started_at, source_ref) VALUES (?,?,?,?)",
                               (provider, product, stamp(), source_ref))

    def finish_run(self, run_id: int, ok: bool, n_records: int = 0, n_new: int = 0, message: str = "") -> None:
        self.db.execute("UPDATE ingest_runs SET finished_at = ?, ok = ?, n_records = ?, n_new = ?, message = ? WHERE id = ?",
                        (stamp(), int(ok), n_records, n_new, message[:500], run_id))

    async def ingest_firms(self) -> list[dict[str, Any]]:
        key = self.settings.firms_map_key
        if not key:
            return []
        sources = self.settings.firms_sources
        run_id = self.start_run("NASA FIRMS", ",".join(sources), f"area/csv {','.join(sources)} Chile 1 día")
        try:
            points, notices = await firms.fetch_hotspots(key, CHILE_BBOX, sources, days=1, client=self.client)
        except firms.UpstreamError as exc:
            self.finish_run(run_id, False, message=str(exc))
            return []
        new = self.store_observations(points, run_id)
        self.finish_run(run_id, True, len(points), len(new), " | ".join(notices))
        return new

    async def ingest_goes(self) -> list[dict[str, Any]]:
        if not self.settings.goes_enabled:
            return []
        try:
            found = await goes.latest_scan(self.client)
        except goes.GoesError as exc:
            run_id = self.start_run("NOAA GOES", "ABI-L2-FDCF", "listado S3")
            self.finish_run(run_id, False, message=str(exc))
            return []
        if not found:
            return []
        satellite, key = found
        if self.db.one("SELECT id FROM ingest_runs WHERE source_ref = ? AND ok = 1", (key,)):
            return []  # barrido ya procesado
        run_id = self.start_run("NOAA GOES", f"GOES{satellite[1:]}_FDCF", key)
        try:
            content = await goes.download(self.client, satellite, key)
            points = await asyncio.to_thread(goes.parse_fdc, content, satellite)
        except goes.GoesError as exc:
            self.finish_run(run_id, False, message=str(exc))
            return []
        new = self.store_observations(points, run_id)
        self.finish_run(run_id, True, len(points), len(new))
        return new

    async def backfill_goes(self, hours: int = 6, every_min: int = 30) -> int:
        """Al arrancar, procesa barridos GOES recientes (uno cada `every_min`) para no partir con el mapa vacío."""
        if not self.settings.goes_enabled or hours <= 0:
            return 0
        now = utcnow()
        satellite = goes.satellite_for(now)
        keys: list[str] = []
        for h in range(hours, -1, -1):
            try:
                listed = await goes.list_keys(self.client, satellite, now - timedelta(hours=h))
            except goes.GoesError:
                return 0
            keys += [k for k in listed if (goes.key_start(k) or now).minute % every_min < 10
                     and goes.key_start(k) >= now - timedelta(hours=hours)]
        done = {r["source_ref"] for r in self.db.query("SELECT source_ref FROM ingest_runs WHERE ok = 1 AND provider = 'NOAA GOES'")}
        added = 0
        for key in keys:
            if key in done:
                continue
            run_id = self.start_run("NOAA GOES", f"GOES{satellite[1:]}_FDCF", key)
            try:
                points = await asyncio.to_thread(goes.parse_fdc, await goes.download(self.client, satellite, key), satellite)
            except goes.GoesError as exc:
                self.finish_run(run_id, False, message=str(exc))
                continue
            new = self.store_observations(points, run_id)
            self.finish_run(run_id, True, len(points), len(new), "relleno inicial")
            added += len(new)
        return added

    # ------------------------------------------------------------------ viento y riesgo
    async def wind_at(self, lat: float, lon: float) -> dict[str, Any] | None:
        cache_key = f"wind:{lat:.2f}:{lon:.2f}"
        cached = self.db.cache_get(cache_key)
        if cached is not None:
            return cached or None
        try:
            data = (await weather.current(self.client, lat, lon))["data"]
            wind = {"speed": data.get("wind_speed_10m"), "gust": data.get("wind_gusts_10m"),
                    "direction": data.get("wind_direction_10m"), "time": data.get("time")}
        except weather.WeatherError:
            wind = {}
        self.db.cache_set(cache_key, wind, 1800 if wind else 300)
        return wind or None

    async def compute_risk(self) -> int:
        """Pronóstico horario de 7 días por comuna → 30-30-30 diario, combinado con el FWI.

        El FWI se calcula antes (compute_fwi) y esta pasada solo lo lee: si el FWI falla, el
        30-30-30 se guarda igual y el combinado queda marcado «sin dato» en vez de desaparecer.
        """
        comunas = territory().comunas
        hourly = await weather.forecast_hourly(self.client, [(c.center[1], c.center[0]) for c in comunas])
        now = stamp()
        today = datetime.now(risk_mod.CHILE_TZ).date().isoformat()
        fwi_by_day = {(row["comuna_code"], row["date"]): row
                      for row in self.db.query("SELECT comuna_code, date, fwi, level FROM fwi_daily WHERE date >= ?",
                                               (today,))}
        with self.db.connect() as conn:
            for comuna, data in zip(comunas, hourly):
                result = risk_mod.evaluate(data)
                conn.execute("INSERT INTO risk_hourly(comuna_code, computed_at, payload) VALUES (?,?,?) "
                             "ON CONFLICT(comuna_code) DO UPDATE SET computed_at = excluded.computed_at, payload = excluded.payload",
                             (comuna.code, now, json.dumps(result["hours"], separators=(",", ":"))))
                for day in result["days"]:
                    fwi_row = fwi_by_day.get((comuna.code, day["date"]))
                    combined, reasons = risk_mod.combine(day["level"], fwi_row["level"] if fwi_row else None)
                    conn.execute(
                        "INSERT INTO risk_daily(comuna_code, date, level, score, hours_3of3, hours_2of3, tmax, rhmin, "
                        "windmax, gustmax, level_combined, fwi, fwi_level, reasons, computed_at) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(comuna_code, date) DO UPDATE SET "
                        "level = excluded.level, score = excluded.score, hours_3of3 = excluded.hours_3of3, "
                        "hours_2of3 = excluded.hours_2of3, tmax = excluded.tmax, rhmin = excluded.rhmin, "
                        "windmax = excluded.windmax, gustmax = excluded.gustmax, "
                        "level_combined = excluded.level_combined, fwi = excluded.fwi, fwi_level = excluded.fwi_level, "
                        "reasons = excluded.reasons, computed_at = excluded.computed_at",
                        (comuna.code, day["date"], day["level"], day["score"], day["hours_3of3"], day["hours_2of3"],
                         day["tmax"], day["rhmin"], day["windmax"], day["gustmax"], combined,
                         fwi_row["fwi"] if fwi_row else None, fwi_row["level"] if fwi_row else None,
                         json.dumps(reasons, ensure_ascii=False), now))
        self.db.kv_set("risk_computed_at", now)
        return len(comunas)

    async def compute_fwi(self) -> int:
        """FWI canadiense por comuna: 60 días de archivo para el estado de sequía y el pronóstico.

        Se guardan solo los días de hoy en adelante (el archivo previo es solo memoria del sistema).
        Si una comuna no trae datos, se omite: no se rellena con ceros ni con el promedio nacional.
        """
        comunas = territory().comunas
        pairs = await weather.fwi_inputs(self.client, [(c.center[1], c.center[0]) for c in comunas])
        now = stamp()
        today = datetime.now(risk_mod.CHILE_TZ).date().isoformat()
        stored = 0
        with self.db.connect() as conn:
            for comuna, (archive_hours, forecast_hours) in zip(comunas, pairs):
                rows = fwi_mod.merge_days(fwi_mod.hourly_to_daily(archive_hours),
                                          fwi_mod.hourly_to_daily(forecast_hours))
                if not rows:
                    continue
                for day in fwi_mod.series(rows, lat=comuna.center[1]):
                    if day["missing"] or str(day["date"]) < today:
                        continue
                    conn.execute(
                        "INSERT INTO fwi_daily(comuna_code, date, ffmc, dmc, dc, isi, bui, fwi, level, computed_at) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(comuna_code, date) DO UPDATE SET ffmc = excluded.ffmc, "
                        "dmc = excluded.dmc, dc = excluded.dc, isi = excluded.isi, bui = excluded.bui, fwi = excluded.fwi, "
                        "level = excluded.level, computed_at = excluded.computed_at",
                        (comuna.code, day["date"], day["ffmc"], day["dmc"], day["dc"], day["isi"], day["bui"],
                         round(day["fwi"], 2), day["level"], now))
                    stored += 1
        self.db.kv_set("fwi_computed_at", now)
        return stored

    async def _risk_and_fwi(self) -> int:
        """Recalcula el FWI y después el 30-30-30: comparten fuente y cadencia, y el riesgo lo lee."""
        await self.compute_fwi()
        return await self.compute_risk()

    async def ingest_dmc(self) -> int:
        """Avisos de viento y calor de la DMC, con las comunas que toca cada uno.

        El RSS es la lista vigente completa, así que reemplaza lo anterior: un aviso que ya no está
        en el feed dejó de existir y no debe seguir mostrándose.
        """
        run_id = self.start_run(dmc.SOURCE, "DMC_CAP", dmc.FEED_URL)
        try:
            alerts = await dmc.fetch_alerts(self.client)
        except dmc.DmcError as exc:
            self.finish_run(run_id, False, message=str(exc))
            raise
        t = territory()
        now = stamp()
        rows = []
        for alert in alerts:
            comunas: set[int] = set()
            areas = []
            for area in alert.areas:
                codes: list[int] = []
                if len(area.polygon) >= 3:
                    polygon = Polygon(area.polygon).buffer(0)
                    if not polygon.is_empty:
                        codes = [c.code for c in t.comunas_in(polygon)]
                if not codes:
                    # Sin polígono solo queda el nombre de la zona («Magallanes: Insular Norte»).
                    codes = [c.code for c in t.comunas_named(area.desc)]
                comunas.update(codes)
                areas.append({"desc": area.desc, "comunas": codes})
            rows.append(alert.as_row(areas, sorted(comunas), now))
        with self.db.connect() as conn:
            conn.execute("DELETE FROM dmc_alerts")
            conn.executemany(
                "INSERT OR REPLACE INTO dmc_alerts(id, kind, event, headline, severity, urgency, onset, expires, web, "
                "areas, comunas, fetched_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                [(r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], json.dumps(r[9], ensure_ascii=False),
                  json.dumps(r[10]), r[11]) for r in rows])
        self.db.kv_set("dmc_at", now)
        self.finish_run(run_id, True, n_records=len(rows))
        return len(rows)

    async def build_rain_normals(self, limit: int | None = None) -> int:
        """Normales de lluvia 1991-2020 por comuna (junio a octubre). Trabajo único, reanudable.

        Se piden **una vez por celda de 0,5°** (~55 km) que contiene el centro de una o más comunas, no
        una vez por comuna: 153 celdas en vez de 345, con el mismo ERA5. Una anomalía estacional no
        cambia en 55 km; pedirlo por comuna multiplicaba el peso sin mejorar la respuesta, y la API
        corta por volumen.

        Cada celda se guarda apenas termina: si el proceso se corta, la siguiente corrida continúa
        donde quedó.
        """
        comunas = territory().comunas
        done = {row["comuna_code"] for row in self.db.query("SELECT comuna_code FROM rain_normal")}
        cells: dict[tuple[int, int], list] = {}
        for comuna in comunas:
            if comuna.code in done:
                continue
            key = (round(comuna.center[1] / RAIN_CELL_DEG), round(comuna.center[0] / RAIN_CELL_DEG))
            cells.setdefault(key, []).append(comuna)
        pending = list(cells.items())
        if limit:
            pending = pending[:limit]
        if not pending:
            return 0
        now = stamp()
        stored = 0
        for index, (key, group) in enumerate(pending):
            if index:
                await asyncio.sleep(RAIN_PAUSE_S)
            point = [(key[0] * RAIN_CELL_DEG, key[1] * RAIN_CELL_DEG)]
            series = await weather.daily_rain(client=self.client, points=point,
                                              start_date="1991-06-01", end_date="2020-10-31")
            normal = rain_mod.build_normal(series[0]) if series else {}
            if not normal:
                continue
            rows = [(comuna.code, len(normal), json.dumps(normal, separators=(",", ":")), now)
                    for comuna in group]
            with self.db.connect() as conn:
                conn.executemany("INSERT OR REPLACE INTO rain_normal(comuna_code, days, daily_normals, computed_at) "
                                 "VALUES (?,?,?,?)", rows)
            stored += len(rows)
        self.db.kv_set("rain_normal_at", now)
        return stored

    async def compute_rain_anomaly(self) -> int:
        """Lluvia de la temporada en curso frente a la normal de la misma ventana de días."""
        comunas = territory().comunas
        normals = {row["comuna_code"]: json.loads(row["daily_normals"])
                   for row in self.db.query("SELECT comuna_code, daily_normals FROM rain_normal")}
        if not normals:
            return 0
        today = datetime.now(risk_mod.CHILE_TZ).date()
        start, end = rain_mod.season_window(today)
        if end < start:
            return 0
        points = [(c.center[1], c.center[0]) for c in comunas]
        archive = await weather.daily_rain(self.client, points, start_date=start.isoformat(), end_date=end.isoformat())
        recent = await weather.daily_rain(self.client, points, past_days=7)
        now = stamp()
        rows = []
        for comuna, past, last in zip(comunas, archive, recent):
            normal_days = normals.get(comuna.code)
            if not normal_days:
                continue
            # El archivo manda donde trae dato; el pronóstico cubre los últimos días que aún faltan.
            merged = {**last, **{k: v for k, v in past.items() if v is not None}}
            result = rain_mod.evaluate(rain_mod.window_sum(merged, start, end),
                                       rain_mod.window_normal(normal_days, start, end))
            rows.append((comuna.code, start.year, result["current_mm"], result["normal_mm"], result["ratio"],
                         result["level"], now))
        with self.db.connect() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO rain_season(comuna_code, year, current_mm, normal_mm, ratio, level, computed_at) "
                "VALUES (?,?,?,?,?,?,?)", rows)
        self.db.kv_set("rain_computed_at", now)
        return len(rows)

    async def ingest_boton_rojo(self) -> int:
        """Pronóstico oficial CONAF Botón Rojo (5 días). Reemplaza los días que trae; los pasados se conservan."""
        run_id = self.start_run(conaf.SOURCE, "BOTON_ROJO", conaf.LAYER_URL)
        try:
            days = conaf.summarize(await conaf.fetch_boton_rojo(self.client))
        except conaf.ConafError as exc:
            self.finish_run(run_id, False, message=str(exc))
            raise
        now = stamp()
        with self.db.connect() as conn:
            # Una comuna que sale del Botón Rojo en el nuevo pronóstico no debe quedar marcada con el anterior.
            for day in sorted({d["date"] for d in days}):
                conn.execute("DELETE FROM boton_rojo WHERE date = ?", (day,))
            conn.executemany("INSERT INTO boton_rojo(comuna_code, date, hours, area_ha, proportion, fetched_at) VALUES (?,?,?,?,?,?)",
                             [(d["comuna_code"], d["date"], d["hours"], d["area_ha"], d["proportion"], now) for d in days])
            conn.execute("DELETE FROM boton_rojo WHERE date < ?", (stamp(utcnow() - timedelta(days=14))[:10],))
        self.finish_run(run_id, True, len(days), len(days))
        self.db.kv_set("boton_rojo_at", now)
        return len(days)

    async def ingest_official_fires(self) -> dict[str, Any]:
        """Incendios informados por CONAF: se guardan, se unen a los incidentes y los nuevos cerca de un lugar avisan."""
        run_id = self.start_run(conaf.FIRES_SOURCE, "CONAF_INCENDIOS", conaf.FIRES_CSV_URL)
        try:
            fires = await conaf.fetch_fires(self.client)
        except conaf.ConafError as exc:
            self.finish_run(run_id, False, message=str(exc))
            raise
        now = stamp()
        known = {r["id"]: r for r in self.db.query("SELECT id, status FROM official_fires")}
        with self.db.connect() as conn:
            conn.executemany(
                "INSERT INTO official_fires(id, name, status, status_raw, started_at, controlled_at, extinguished_at, area_ha, lat, lon, "
                "comuna, region, ambito, fuel, first_fetched_at, fetched_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET name = excluded.name, status = excluded.status, status_raw = excluded.status_raw, "
                "controlled_at = excluded.controlled_at, extinguished_at = excluded.extinguished_at, area_ha = excluded.area_ha, "
                "lat = excluded.lat, lon = excluded.lon, fetched_at = excluded.fetched_at",
                [(f["id"], f["name"], f["status"], f["status_raw"], f["started_at"], f["controlled_at"], f["extinguished_at"],
                  f["area_ha"], f["lat"], f["lon"], f["comuna"], f["region"], f["ambito"], f["fuel"], now, now) for f in fires])
        new = [f for f in fires if f["id"] not in known]
        linked = await asyncio.to_thread(incidents_mod.link_official, self.db, fires)
        created = await alerts_mod.evaluate_official(self.db, new) if known else []  # la primera carga no avisa en masa
        await self.deliver(created)
        self.finish_run(run_id, True, len(fires), len(new))
        return {"official_fires": len(fires), "official_new": len(new), "official_linked": linked, "official_alerts": len(created)}

    def due(self, key: str, interval_s: float) -> bool:
        """¿Toca correr una tarea? Se apoya en la marca de tiempo que la tarea deja en `kv`.

        El Cron Trigger puede llamar cada minuto: sin esta guarda, DMC y lluvia se pedirían a su
        API en cada vuelta y el proveedor cortaría por cuota.
        """
        last = self.db.kv_get(key)
        return not last or (utcnow() - datetime.fromisoformat(last.replace("Z", "+00:00"))).total_seconds() >= interval_s

    def boton_rojo_due(self) -> bool:
        return self.due("boton_rojo_at", BOTON_ROJO_EVERY_H * 3600)

    # ------------------------------------------------------------------ alertas
    async def deliver(self, created: list[dict[str, Any]]) -> None:
        token = self.settings.telegram_bot_token
        for alert in created:
            sub = self.db.one("SELECT * FROM subscribers WHERE id = ?", (alert["subscriber_id"],))
            if not sub:
                continue
            channels = []
            if sub.get("push_endpoint") and await asyncio.to_thread(webpush.send, self.db, sub, alert["payload"], self.settings.vapid_contact):
                channels.append("push")
            if token and sub.get("telegram_chat_id"):
                text = telegram.format_alert(alert["payload"], self._public_url)
                if await telegram.send_message(self.client, token, sub["telegram_chat_id"], text):
                    channels.append("telegram")
            self.db.execute("UPDATE alerts SET delivered = ? WHERE id = ?", (json.dumps(channels), alert["id"]))

    async def ingest_cycle(self) -> dict[str, Any]:
        async with self._lock:
            # Una fuente caída no debe bloquear a la otra ni dejar sin registrar la revisión.
            results = await asyncio.gather(self.ingest_firms(), self.ingest_goes(), return_exceptions=True)
            news: dict[str, list[dict[str, Any]]] = {}
            failed: list[str] = []
            for name, res in zip(("firms", "goes"), results):
                if isinstance(res, BaseException):
                    log.warning("Ingesta %s falló: %r", name, res)
                    failed.append(name)
                    news[name] = []
                else:
                    news[name] = res
            fresh = news["firms"] + news["goes"]
            touched: list[dict[str, Any]] = []
            try:  # un error al agrupar no debe impedir los avisos: siguen saliendo, sin datos del incidente
                touched = await asyncio.to_thread(incidents_mod.update, self.db, fresh)
                await asyncio.to_thread(incidents_mod.expire, self.db)
            except Exception:
                log.exception("Agrupación de incidentes falló")
            created = await alerts_mod.evaluate(self.db, fresh, self.wind_at)
            await self.deliver(created)
            cutoff = stamp(utcnow() - timedelta(days=RETENTION_DAYS))
            self.db.execute("DELETE FROM observations WHERE observed_at < ?", (cutoff,))
            incidents_mod.prune(self.db, cutoff)
            self.db.cache_purge()
            if len(failed) < 2:
                self.db.kv_set("last_ingest_at", stamp())
            return {"firms_new": len(news["firms"]), "goes_new": len(news["goes"]), "alerts": len(created),
                    "incidents": len(touched), "failed_sources": failed}

    async def tick_and_backup(self) -> dict[str, Any]:
        """Ciclo completo más respaldo; deja un resumen sin datos sensibles en `last_cycle`."""
        started = stamp()
        try:
            result = await self.tick()
        except Exception as exc:
            log.exception("Ciclo falló")
            result = {"error": type(exc).__name__}
        if self.persistence.enabled:
            try:
                result["backup"] = await self.persistence.flush()
            except Exception as exc:
                result["backup"] = False
                result["backup_error"] = str(exc)
            try:
                result["work_backup"] = await self.persistence.flush_work()
            except Exception as exc:
                result["work_backup"] = False
                result["backup_error"] = (result.get("backup_error", "") + f" work: {exc}").strip()
        self.last_cycle = {"started_at": started, "finished_at": stamp(),
                           **{k: v for k, v in result.items() if k in ("firms_new", "goes_new", "alerts", "incidents", "failed_sources", "backup",
                                                               "work_backup", "error", "risk_comunas", "boton_rojo", "fwi_comunas",
                                                               "dmc_alerts", "rain_comunas",
                                                               "official_fires", "official_new", "official_linked", "official_alerts")},
                           **{k: True for k in ("backfill_error", "risk_error", "boton_rojo_error", "official_error", "fwi_error",
                                                "dmc_error", "rain_error") if k in result},
                           # Los errores del respaldo se muestran recortados: solo hablan de storage.brasa, sin datos sensibles.
                           **{k: str(result[k])[:200] for k in ("restore_error", "backup_error") if k in result}}
        return result

    def start_tick(self) -> bool:
        """Lanza un ciclo en segundo plano (para el Cron Trigger, que tiene ~30 s). False si ya hay uno en curso."""
        if self._tick_task and not self._tick_task.done():
            return False
        self._tick_task = asyncio.create_task(self.tick_and_backup())
        return True

    # ------------------------------------------------------------------ bucles
    def start_background(self) -> None:
        async def first_backfill():
            try:
                log.info("Relleno GOES inicial: %s detecciones", await self.backfill_goes())
            except Exception as exc:
                log.warning("Relleno GOES falló: %s", exc)
        self.tasks.append(asyncio.create_task(first_backfill()))
        self.tasks.append(asyncio.create_task(self._loop("ingesta", self.ingest_cycle, self.settings.ingest_interval_min * 60)))
        self.tasks.append(asyncio.create_task(self._loop("riesgo", self._risk_and_fwi, self.settings.risk_interval_min * 60)))
        self.tasks.append(asyncio.create_task(self._loop("boton-rojo", self.ingest_boton_rojo, BOTON_ROJO_EVERY_H * 3600)))
        self.tasks.append(asyncio.create_task(self._loop("dmc", self.ingest_dmc, DMC_EVERY_H * 3600)))
        self.tasks.append(asyncio.create_task(self._loop("lluvia", self.compute_rain_anomaly, RAIN_EVERY_H * 3600)))
        self.tasks.append(asyncio.create_task(self._loop("conaf-incendios", self.ingest_official_fires, self.settings.ingest_interval_min * 60)))
        if self.settings.telegram_bot_token and not self.settings.telegram_webhook_secret:
            self.tasks.append(asyncio.create_task(self._telegram_loop()))

    async def _loop(self, name: str, job, interval: float) -> None:
        while True:
            try:
                result = await job()
                log.info("Tarea %s completada: %s", name, result)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # una falla de proveedor no debe detener el servicio
                log.warning("Tarea %s falló: %s", name, exc)
            await asyncio.sleep(interval)

    async def _telegram_loop(self) -> None:
        while True:
            try:
                await telegram.poll_once(self.db, self.client, self.settings.telegram_bot_token)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("Telegram: %s", exc)
                await asyncio.sleep(15)

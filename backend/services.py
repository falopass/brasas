"""Servicios compartidos y tareas de ingesta: observaciones → base local → alertas → notificaciones."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from backend import alerts as alerts_mod
from backend import incidents as incidents_mod
from backend import risk as risk_mod
from backend.db import Database
from backend.geo import territory
from backend.notify import telegram, webpush
from backend.providers import firms, goes, weather
from backend.settings import Settings
from backend.storage import Persistence, RemoteStorage

log = logging.getLogger("brasa")
CHILE_BBOX = [-81.5, -56.5, -66.0, -17.0]
RETENTION_DAYS = 45


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
        last = self.db.one("SELECT MAX(computed_at) AS t FROM risk_daily")["t"]
        due = not last or (utcnow() - datetime.fromisoformat(last.replace("Z", "+00:00"))).total_seconds() >= self.settings.risk_interval_min * 60
        if due:
            try:
                result["risk_comunas"] = await self.compute_risk()
            except Exception as exc:
                result["risk_error"] = str(exc)
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
        """Pronóstico horario de 7 días en el centro de cada comuna → índice diario."""
        comunas = territory().comunas
        hourly = await weather.forecast_hourly(self.client, [(c.center[1], c.center[0]) for c in comunas])
        now = stamp()
        with self.db.connect() as conn:
            for comuna, data in zip(comunas, hourly):
                result = risk_mod.evaluate(data)
                conn.execute("INSERT INTO risk_hourly(comuna_code, computed_at, payload) VALUES (?,?,?) "
                             "ON CONFLICT(comuna_code) DO UPDATE SET computed_at = excluded.computed_at, payload = excluded.payload",
                             (comuna.code, now, json.dumps(result["hours"], separators=(",", ":"))))
                for day in result["days"]:
                    conn.execute(
                        "INSERT INTO risk_daily(comuna_code, date, level, score, hours_3of3, hours_2of3, tmax, rhmin, windmax, gustmax, computed_at) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(comuna_code, date) DO UPDATE SET level = excluded.level, "
                        "score = excluded.score, hours_3of3 = excluded.hours_3of3, hours_2of3 = excluded.hours_2of3, tmax = excluded.tmax, "
                        "rhmin = excluded.rhmin, windmax = excluded.windmax, gustmax = excluded.gustmax, computed_at = excluded.computed_at",
                        (comuna.code, day["date"], day["level"], day["score"], day["hours_3of3"], day["hours_2of3"],
                         day["tmax"], day["rhmin"], day["windmax"], day["gustmax"], now))
        self.db.kv_set("risk_computed_at", now)
        return len(comunas)

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
                                                               "work_backup", "error", "risk_comunas")},
                           **{k: True for k in ("backfill_error", "risk_error") if k in result},
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
        self.tasks.append(asyncio.create_task(self._loop("riesgo", self.compute_risk, self.settings.risk_interval_min * 60)))
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

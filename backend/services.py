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
from backend.settings import ROOT, Settings
from backend.storage import Persistence, RemoteStorage
from shapely.geometry import Polygon

log = logging.getLogger("brasa")
CHILE_BBOX = [-81.5, -56.5, -66.0, -17.0]
RETENTION_DAYS = 45
ALERTS_RETENTION_DAYS = 365      # FIX-21: el historial de avisos de un dispositivo dura máximo 12 meses
REPORTS_STALE_DAYS = 90          # reportes sin verificar o descartados
REPORTS_VERIFIED_DAYS = 730      # reportes verificados: 2 años
BOTON_ROJO_EVERY_H = 3
CONAF_COND_EVERY_H = 3            # las capas de condiciones se publican una vez al día
CONAF_COND_LAYERS_PER_RUN = 8     # 25 capas en total: una actualización tarda ~4 tandas
CONAF_COND_BATCH_PAUSE_S = 60     # entre tandas pendientes, para que el próximo ciclo continúe pronto
CONAF_COND_LOOP_S = 1800          # el lazo interno revisa cada 30 min; la cadencia la manda conaf_cond_due
DMC_EVERY_H = 1
RAIN_EVERY_H = 6
RAIN_CELL_DEG = 0.5   # las normales se piden por celda de 0,5° (~55 km), no por comuna
RAIN_PAUSE_S = 15     # medido: 194 KB por celda cada 15 s queda bajo el límite por minuto de Open-Meteo
RISK_SNAPSHOT_EVERY_H = 1   # la foto es diaria; esta guarda evita consultar la base en cada tick
RISK_SNAPSHOT_DAYS = 120    # fotos guardadas: cuatro meses alcanzan para comparar todo el verano
GOES_WINDOW_MIN = 40  # barridos pendientes a cubrir: cuatro ciclos de 10 min, tolera un atraso
GOES_MAX_SCANS = 4    # tope por ciclo para no comerse el tiempo del cron
RAIN_NORMALS_FILE = ROOT / "web" / "data" / "rain_normals.json"  # FIX-25: semilla versionada si se pierde work.db


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
        self._deliver_lock = asyncio.Lock()
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
        # La foto del pronóstico se toma una vez al día, después de recalcular el riesgo.
        if self.due("risk_snapshot_at", RISK_SNAPSHOT_EVERY_H * 3600):
            try:
                result["risk_snapshots"] = await self.capture_risk_snapshot()
            except Exception as exc:
                result["snapshot_error"] = str(exc)[:200]
        if self.due("dmc_at", DMC_EVERY_H * 3600):
            try:
                result["dmc_alerts"] = await self.ingest_dmc()
            except Exception as exc:
                result["dmc_error"] = str(exc)[:200]
        if self.due("rain_computed_at", RAIN_EVERY_H * 3600):
            try:
                result.update(await self.rain_cycle())
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
        try:
            result["conaf_condiciones"] = await self.ingest_conaf_condiciones()
        except Exception as exc:
            result["conaf_cond_error"] = str(exc)[:200]
        # ALR-04: la pasada preventiva va al final del ciclo, cuando el riesgo y el Botón Rojo
        # del día ya están lo más frescos posible.
        try:
            result["daily_brief"] = await self.daily_brief()
        except Exception as exc:
            result["daily_brief_error"] = str(exc)[:200]
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

    def pending_alert_observations(self, hours: int = alerts_mod.MAX_AGE_H) -> list[dict[str, Any]]:
        """Detecciones recientes que todavía no se miraron para ver si generan aviso.

        Guardar la detección, marcarla como procesada y avisar son pasos separados: si el proceso
        muere entre ellos (reinicio, suspensión del contenedor), esa detección no despertaba a
        nadie nunca, porque el reintento la encuentra ya registrada con ok=1. Aquí se recuperan
        para el ciclo siguiente.

        El estado se lleva en `alerts_evaluated_at`, no en la existencia de una fila en `alerts`:
        la mayoría de las detecciones no tiene ningún lugar cerca y nunca crearía alerta, así que
        deducir «evaluada» de esa tabla las dejaba pendientes seis horas, reconsultadas y
        reevaluadas cada diez minutos.

        La excepción es la que ya tiene su aviso escrito: la fila en `alerts` prueba que pasó por
        la evaluación (una base migrada antes de que existiera la marca, o un corte entre crear
        la alerta y marcarla), y traerla otra vez podría ganarle el puesto de «detección más
        cercana» a un foco nuevo que sí necesita aviso.
        """
        since = stamp(utcnow() - timedelta(hours=hours))
        return self.db.query(
            "SELECT o.* FROM observations o WHERE o.observed_at >= ? AND o.alerts_evaluated_at IS NULL "
            "AND NOT EXISTS (SELECT 1 FROM alerts a WHERE a.observation_id = o.id) "
            "ORDER BY o.observed_at", (since,))

    def mark_alerts_evaluated(self, observations: list[dict[str, Any]], moment: datetime | None = None) -> int:
        """Marca como evaluadas las detecciones de este ciclo, hayan avisado o no."""
        ids = [obs["id"] for obs in observations if obs.get("id")]
        if not ids:
            return 0
        now = stamp(moment or utcnow())
        marked = 0
        with self.db.connect() as conn:
            for start in range(0, len(ids), 500):   # SQLite limita los parámetros por consulta
                chunk = ids[start:start + 500]
                marked += conn.execute(
                    f"UPDATE observations SET alerts_evaluated_at = ? WHERE id IN ({','.join('?' * len(chunk))})",
                    (now, *chunk)).rowcount
        return marked

    def start_run(self, provider: str, product: str, source_ref: str) -> int:
        return self.db.insert("INSERT INTO ingest_runs(provider, product, started_at, source_ref) VALUES (?,?,?,?)",
                               (provider, product, stamp(), source_ref))

    def finish_run(self, run_id: int, ok: bool, n_records: int = 0, n_new: int = 0, message: str = "") -> None:
        self.db.execute("UPDATE ingest_runs SET finished_at = ?, ok = ?, n_records = ?, n_new = ?, message = ? WHERE id = ?",
                        (stamp(), int(ok), n_records, n_new, message[:500], run_id))

    async def ingest_firms(self) -> list[dict[str, Any]]:
        """Punto de entrada público: toma el lock para no pisarse con otra llamada (cron, arranque)."""
        async with self._lock:
            return await self._ingest_firms()

    async def ingest_goes(self) -> list[dict[str, Any]]:
        """Punto de entrada público: mismo lock que la ingesta de FIRMS y que el ciclo."""
        async with self._lock:
            return await self._ingest_goes()

    async def _ingest_firms(self) -> list[dict[str, Any]]:
        """Detecciones de las últimas 48 h. Se piden dos días porque la latencia NRT es de 1 a 3 h:
        con `days=1` FIRMS devuelve solo el día UTC en curso, y una pasada adquirida a las 22:30 que
        se publica a la 01:30 del día siguiente no aparecía en ninguna consulta. `INSERT OR IGNORE`
        ya deduplica por `id`, así que volver a pedir el día anterior no duplica nada."""
        key = self.settings.firms_map_key
        if not key:
            return []
        sources = self.settings.firms_sources
        run_id = self.start_run("NASA FIRMS", ",".join(sources), f"area/csv {','.join(sources)} Chile 2 días")
        try:
            points, notices = await firms.fetch_hotspots(key, CHILE_BBOX, sources, days=2, client=self.client)
        except firms.UpstreamError as exc:
            self.finish_run(run_id, False, message=str(exc))
            return []
        new = self.store_observations(points, run_id)
        self.finish_run(run_id, True, len(points), len(new), " | ".join(notices))
        return new

    async def _ingest_goes(self) -> list[dict[str, Any]]:
        """Procesa los barridos de los últimos 40 minutos, no solo el más reciente.

        GOES-19 entrega un barrido cada 10 minutos y el cron también corre cada 10: si un ciclo se
        atrasa, falla o el contenedor se reinicia, mirar solo el último (`latest_scan`) dejaba los
        intermedios perdidos para siempre, y el relleno únicamente corre al arrancar. Se listan la
        hora actual y la anterior (un barrido de las 23:55 aparece en la hora nueva), se descartan
        los ya procesados y se atienden en orden, con un tope por ciclo para no comerse el tiempo
        del cron. Un barrido que falla no bloquea a los demás.
        """
        if not self.settings.goes_enabled:
            return []
        now = utcnow()
        satellite = goes.satellite_for(now)
        since = now - timedelta(minutes=GOES_WINDOW_MIN)
        # La hora anterior solo hace falta si la ventana de 40 minutos la cruza: un barrido de las
        # 23:55 vive en la hora nueva, pero uno de las 23:20 está en la anterior.
        crossed = (since.hour, since.date()) != (now.hour, now.date())
        keys: list[str] = []
        errors: list[str] = []
        for hour in ([now, now - timedelta(hours=1)] if crossed else [now]):
            try:
                keys += await goes.list_keys(self.client, satellite, hour)
            except goes.GoesError as exc:
                errors.append(f"{hour:%Y-%m-%dT%H}Z {exc}")  # un listado caído no invalida el otro
        if errors:
            # La hora caída queda en la corrida aunque la otra haya devuelto claves: si no, el
            # fallo no aparece en el estado y sus barridos envejecen fuera de la ventana sin
            # registro de por qué no entraron.
            run_id = self.start_run("NOAA GOES", "ABI-L2-FDCF", "listado S3")
            self.finish_run(run_id, False, message=" | ".join(errors))
            if not keys:
                return []
        done = {row["source_ref"] for row in self.db.query(
            "SELECT source_ref FROM ingest_runs WHERE ok = 1 AND provider = 'NOAA GOES'")}
        pending: list[str] = []
        for key in sorted(set(keys)):
            start = goes.key_start(key)
            if start is None or start < since or key in done:
                continue
            pending.append(key)
        news: list[dict[str, Any]] = []
        for key in pending[:GOES_MAX_SCANS]:
            run_id = self.start_run("NOAA GOES", f"GOES{satellite[1:]}_FDCF", key)
            try:
                content = await goes.download(self.client, satellite, key)
                points = await asyncio.to_thread(goes.parse_fdc, content, satellite)
                new = self.store_observations(points, run_id)
            except Exception as exc:  # un HDF5 con un campo inesperado no puede tirar los barridos anteriores
                self.finish_run(run_id, False, message=f"No se pudo leer el barrido ({type(exc).__name__}: {exc})"[:500])
                continue
            self.finish_run(run_id, True, len(points), len(new))
            news.extend(new)
        return news

    async def backfill_goes(self, hours: int = 6, every_min: int = 30) -> int:
        """Al arrancar, procesa barridos GOES recientes (uno cada `every_min`) para no partir con el mapa vacío.

        Dos cuidados, porque corre en paralelo con la ingesta periódica:
        - Toma el mismo lock que `ingest_cycle`: si no, el relleno podía insertar un barrido entre el
          listado y el guardado del ciclo, `store_observations` devolvía cero filas nuevas y ese
          barrido —reciente— se quedaba sin aviso.
        - Deja fuera los últimos GOES_WINDOW_MIN minutos: esos son del ciclo normal, que sí evalúa
          avisos. El relleno es para la historia del mapa, no para despertar a nadie.
        """
        if not self.settings.goes_enabled or hours <= 0:
            return 0
        async with self._lock:
            now = utcnow()
            satellite = goes.satellite_for(now)
            fresh_after = now - timedelta(minutes=GOES_WINDOW_MIN)
            keys: list[str] = []
            for h in range(hours, -1, -1):
                try:
                    listed = await goes.list_keys(self.client, satellite, now - timedelta(hours=h))
                except goes.GoesError:
                    return 0
                keys += [k for k in listed if (goes.key_start(k) or now).minute % every_min < 10
                         and (goes.key_start(k) or now) >= now - timedelta(hours=hours)
                         and (goes.key_start(k) or now) < fresh_after]
            done = {r["source_ref"] for r in self.db.query("SELECT source_ref FROM ingest_runs WHERE ok = 1 AND provider = 'NOAA GOES'")}
            added = 0
            for key in sorted(set(keys)):
                if key in done:
                    continue
                run_id = self.start_run("NOAA GOES", f"GOES{satellite[1:]}_FDCF", key)
                try:
                    points = await asyncio.to_thread(goes.parse_fdc, await goes.download(self.client, satellite, key), satellite)
                except Exception as exc:  # igual que en la ingesta: un barrido roto no tira los demás
                    self.finish_run(run_id, False, message=f"No se pudo leer el barrido ({type(exc).__name__})"[:500])
                    continue
                new = self.store_observations(points, run_id)
                self.finish_run(run_id, True, len(points), len(new), "relleno inicial")
                # El relleno llena el mapa, no despierta a nadie: se marca como evaluado para que no
                # entre en la recuperación de avisos del ciclo siguiente.
                self.mark_alerts_evaluated(new)
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

        RISK-04: cada comuna se evalúa en varios puntos (`risk.evaluation_points`: el centro y,
        si su caja es extensa, hasta cuatro puntos interiores que caigan dentro de su polígono)
        y queda con el peor nivel del día. Todos los puntos van en el mismo lote multi-ubicación
        de Open-Meteo, así que el número de peticiones no crece por comuna.

        El FWI se calcula antes (compute_fwi) y esta pasada solo lo lee: si el FWI falla, el
        30-30-30 se guarda igual y el combinado queda marcado «sin dato» en vez de desaparecer.
        El FWI se mantiene en el centro de la comuna: extenderlo a varios puntos multiplicaría
        por cinco el archivo ERA5, la fuente que ya más carga el cupo de Open-Meteo; se evalúa
        en su propio ítem.
        """
        terr = territory()
        comunas = terr.comunas

        def inside(code: int):
            def check(lat: float, lon: float) -> bool:
                found = terr.locate(lat, lon)
                return found is not None and found.code == code
            return check

        per_comuna = [risk_mod.evaluation_points(c, inside(c.code)) for c in comunas]
        points = [point for pts in per_comuna for point in pts]
        hourly = await weather.forecast_hourly(self.client, points)
        now = stamp()
        today = datetime.now(risk_mod.CHILE_TZ).date().isoformat()
        fwi_by_day = {(row["comuna_code"], row["date"]): row
                      for row in self.db.query("SELECT comuna_code, date, fwi, level FROM fwi_daily WHERE date >= ?",
                                               (today,))}
        with self.db.connect() as conn:
            offset = 0
            for comuna, pts in zip(comunas, per_comuna):
                result = risk_mod.evaluate_comuna(pts, hourly[offset:offset + len(pts)])
                offset += len(pts)
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
        """FWI canadiense por comuna: archivo desde el inicio de la temporada (junio) para el estado de sequía y el pronóstico.

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

    async def _risk_and_fwi(self) -> dict[str, Any]:
        """FWI y después 30-30-30, sin que uno arrastre al otro.

        El archivo de Open-Meteo que alimenta el FWI se agota por volumen (429); si eso pasara y
        esta función abortara, el mapa se quedaría sin nivel 30-30-30 aunque su fuente (el
        pronóstico) esté sana. Cada mitad se guarda por separado y el combinado cae al 30-30-30.
        """
        fwi: int | None = None
        error = ""
        try:
            fwi = await self.compute_fwi()
        except Exception as exc:  # se registra y se sigue: el 30-30-30 no depende del archivo
            error = str(exc)[:200]
            log.warning("FWI falló: %s", error)
        comunas = await self.compute_risk()
        snapshots = await self.capture_risk_snapshot()
        return {"fwi_comunas": fwi, "risk_comunas": comunas, "risk_snapshots": snapshots,
                **({"fwi_error": error} if error else {})}

    async def capture_risk_snapshot(self) -> int:
        """Guarda el pronóstico de hoy como la foto del día (una sola vez por día de Chile).

        Es lo que hace posible comparar semana a semana: cuando el cron recalcule, esta foto
        conserva lo que se pronosticaba hoy para los próximos días. Se poda sola a los cuatro meses.
        """
        today = datetime.now(risk_mod.CHILE_TZ).date()
        day = today.isoformat()
        done = self.db.one("SELECT COUNT(*) AS n FROM risk_snapshot WHERE snapshot_date = ?", (day,))["n"]
        if done:
            return 0
        rows = self.db.query("SELECT comuna_code, date, level, level_combined, score FROM risk_daily "
                             "WHERE date >= ? ORDER BY date", (day,))
        if not rows:
            return 0
        cutoff = (today - timedelta(days=RISK_SNAPSHOT_DAYS)).isoformat()
        with self.db.connect() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO risk_snapshot(snapshot_date, comuna_code, target_date, level, level_combined, score) "
                "VALUES (?,?,?,?,?,?)",
                [(day, r["comuna_code"], r["date"], r["level"], r["level_combined"], r["score"]) for r in rows])
            conn.execute("DELETE FROM risk_snapshot WHERE snapshot_date < ?", (cutoff,))
        self.db.kv_set("risk_snapshot_at", stamp())
        return len(rows)

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
        # ALR-14: cada aviso vigente que toca la comuna de un lugar avisa una vez;
        # el UNIQUE(place_id, observation_id) con «dmc:<id CAP>» deduplica las pasadas siguientes.
        created = await alerts_mod.evaluate_dmc(self.db, self.db.query("SELECT * FROM dmc_alerts"), utcnow())
        await self.deliver(created)
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

    def _seed_rain_normals(self) -> int:
        """Repone `rain_normal` desde el JSON versionado cuando la tabla está vacía (FIX-25).

        Las normales 1991-2020 no cambian: si se pierde `work.db`, cargarlas desde
        `web/data/rain_normals.json` evita pedir otra vez 30 años de archivo por celda. Las
        comunas que el archivo no traiga las completa después `build_rain_normals`.
        """
        if self.db.one("SELECT comuna_code FROM rain_normal LIMIT 1"):
            return 0
        pack = rain_mod.load_normals_file(RAIN_NORMALS_FILE)
        if not pack:
            return 0
        computed_at = pack["generated_at"] or stamp()
        rows = [(code, len(daily), json.dumps(daily, separators=(",", ":")), computed_at)
                for code, daily in pack["cells"].items()]
        with self.db.connect() as conn:
            conn.executemany("INSERT OR REPLACE INTO rain_normal(comuna_code, days, daily_normals, computed_at) "
                             "VALUES (?,?,?,?)", rows)
        self.db.kv_set("rain_normal_at", computed_at)
        log.info("Normales de lluvia repuestas desde %s: %d comunas", RAIN_NORMALS_FILE, len(rows))
        return len(rows)

    async def rain_cycle(self) -> dict[str, Any]:
        """Completa las normales que falten y recalcula la anomalía de la temporada.

        Si la tabla está vacía y existe el JSON versionado, primero se repone desde ahí (FIX-25)
        y las celdas solo se piden para las comunas que el archivo no traiga. Las normales son
        153 celdas de 30 años de archivo: se avanzan de a `rain_normals_per_run` por vuelta
        (cada 6 h) para no agotar el cupo de Open-Meteo, que el FWI también usa. Si el archivo
        responde 429 se conserva lo avanzado y la anomalía se calcula igual con las comunas
        que ya tengan normal: el resultado parcial es correcto, solo cubre menos comunas.
        """
        self._seed_rain_normals()
        built = 0
        per_run = self.settings.rain_normals_per_run
        if per_run > 0:
            try:
                built = await self.build_rain_normals(limit=per_run)
            except weather.WeatherRateLimited:
                log.warning("Normales de lluvia: cupo de Open-Meteo agotado; se retoma en la próxima vuelta")
        return {"rain_normals": built, "rain_comunas": await self.compute_rain_anomaly()}

    async def compute_rain_anomaly(self) -> int:
        """Lluvia de la temporada en curso frente a la normal de la misma ventana de días."""
        comunas = territory().comunas
        self._seed_rain_normals()
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
        # FIX-11: el intento se marca antes de descargar para que el reintento espere
        # tras un fallo en vez de volver a probar en cada ciclo de ingesta.
        self.db.kv_set("boton_rojo_try_at", stamp())
        try:
            days = conaf.summarize(await conaf.fetch_boton_rojo(self.client))
        except conaf.ConafError as exc:
            self.db.kv_set("boton_rojo_fails", str(int(self.db.kv_get("boton_rojo_fails") or 0) + 1))
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
        self.db.kv_set("boton_rojo_fails", "0")
        return len(days)

    async def ingest_conaf_condiciones(self, per_run: int = CONAF_COND_LAYERS_PER_RUN) -> int:
        """Condiciones oficiales de CONAF (PI/HC/VV/HR/TP) resumidas por comuna y día.

        Los cinco servicios tienen cada uno 5 capas diarias con la grilla de ~2 km disuelta por
        clase: unas 130.000 filas por actualización, demasiadas para un solo ciclo del cron.
        Primero se lee la firma barata de las capas (los nombres llevan la fecha): si no cambió
        y la tabla tiene filas, no se baja nada. Cuando cambia, la cola de capas pendientes se
        guarda en `kv` y se procesan `per_run` por llamada —la última versión completa queda en
        la tabla mientras tanto— y un corte a mitad se retoma en el ciclo siguiente.
        """
        if not self.conaf_cond_due():
            return 0
        run_id = self.start_run(conaf.CONDICIONES_SOURCE, "CONAF_CONDICIONES", conaf.CONDICIONES_CATALOG_URL)
        # Igual que FIX-11 en Botón Rojo: el intento se marca antes de descargar para que el
        # reintento tras un fallo espere en vez de volver a probar en cada ciclo.
        self.db.kv_set("conaf_cond_try_at", stamp())
        try:
            layers = await conaf.list_condicion_layers(self.client)
        except conaf.ConafError as exc:
            self.db.kv_set("conaf_cond_fails", str(int(self.db.kv_get("conaf_cond_fails") or 0) + 1))
            self.finish_run(run_id, False, message=str(exc))
            raise
        signature = conaf.condiciones_signature(layers)
        saved = self.db.kv_get("conaf_cond_pending")
        pending = json.loads(saved) if saved else None
        queue = pending["layers"] if pending and pending.get("sig") == signature else None
        if queue is None:
            if signature == self.db.kv_get("conaf_cond_sig") and self.db.one("SELECT 1 AS x FROM conaf_condiciones LIMIT 1"):
                self.finish_run(run_id, True, 0, 0, "capas sin cambios")
                self.db.kv_set("conaf_cond_at", stamp())
                self.db.kv_set("conaf_cond_fails", "0")
                return 0
            queue = [[var, layer_id] for var, items in layers.items() for layer_id, _ in items]
            self.db.kv_set("conaf_cond_pending",
                           json.dumps({"sig": signature, "layers": queue}, separators=(",", ":")))
        written = 0
        try:
            for _ in range(per_run):
                if not queue:
                    break
                var, layer_id = queue.pop(0)
                features = await conaf.fetch_condicion_layer(self.client, var, layer_id)
                rows = await asyncio.to_thread(conaf.summarize_condiciones, features)
                now = stamp()
                with self.db.connect() as conn:
                    # Una capa reemplaza solo sus propios (var, fecha): el resto sigue vigente.
                    for day in {r["date"] for r in rows}:
                        conn.execute("DELETE FROM conaf_condiciones WHERE var = ? AND date = ?", (var, day))
                    conn.executemany(
                        "INSERT INTO conaf_condiciones(comuna_code, date, var, label, cells, cells_total, fetched_at) "
                        "VALUES (?,?,?,?,?,?,?)",
                        [(r["comuna_code"], r["date"], r["var"], r["label"], r["cells"], r["cells_total"], now)
                         for r in rows])
                written += len(rows)
                self.db.kv_set("conaf_cond_pending",
                               json.dumps({"sig": signature, "layers": queue}, separators=(",", ":")))
        except conaf.ConafError as exc:
            self.db.kv_set("conaf_cond_fails", str(int(self.db.kv_get("conaf_cond_fails") or 0) + 1))
            self.finish_run(run_id, False, written, written, str(exc))
            raise
        if queue:
            # Quedan capas por procesar: el progreso es bueno (sin castigo de reintento) y la
            # tanda sigue en el próximo ciclo.
            self.db.kv_set("conaf_cond_fails", "0")
            self.finish_run(run_id, True, written, written, f"tanda: quedan {len(queue)} capas")
            return written
        self.db.execute("DELETE FROM conaf_condiciones WHERE date < ?", (stamp(utcnow() - timedelta(days=14))[:10],))
        self.db.kv_set("conaf_cond_pending", "")
        self.db.kv_set("conaf_cond_sig", signature)
        self.db.kv_set("conaf_cond_at", stamp())
        self.db.kv_set("conaf_cond_fails", "0")
        self.finish_run(run_id, True, written, written)
        return written

    async def ingest_official_fires(self) -> dict[str, Any]:
        """Incendios informados por CONAF: se guardan, se unen a los incidentes y los nuevos cerca de un lugar avisan.

        La descarga es condicional: se guarda el `ETag` del CSV en `kv` y se manda como
        `If-None-Match`. Si CONAF responde 304 no cambió nada y no hay nada que parsear ni escribir.
        """
        run_id = self.start_run(conaf.FIRES_SOURCE, "CONAF_INCENDIOS", conaf.FIRES_CSV_URL)
        try:
            # El ETag vive en main y las filas en work.db: con la tabla vacía (work.db restaurado)
            # la etiqueta ya no corresponde a las filas y un 304 dejaría la tabla vacía para siempre.
            known = {r["id"]: r for r in self.db.query("SELECT id, status FROM official_fires")}
            result = await conaf.fetch_fires(self.client, etag=self.db.kv_get("conaf_etag") if known else None)
        except conaf.ConafError as exc:
            self.finish_run(run_id, False, message=str(exc))
            raise
        if result["not_modified"]:
            self.finish_run(run_id, True, 0, 0, "sin cambios en el reporte (304)")
            return {"official_fires": 0, "official_new": 0, "official_linked": 0, "official_alerts": 0,
                    "official_not_modified": True}
        fires = result["fires"]
        now = stamp()
        try:
            with self.db.connect() as conn:
                conn.executemany(
                    "INSERT INTO official_fires(id, name, status, status_raw, started_at, controlled_at, extinguished_at, area_ha, lat, lon, "
                    "comuna, region, ambito, fuel, detected_at, alerted_at, dispatched_at, season, first_fetched_at, fetched_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
                    "ON CONFLICT(id) DO UPDATE SET name = excluded.name, status = excluded.status, status_raw = excluded.status_raw, "
                    "controlled_at = excluded.controlled_at, extinguished_at = excluded.extinguished_at, area_ha = excluded.area_ha, "
                    "lat = excluded.lat, lon = excluded.lon, detected_at = excluded.detected_at, alerted_at = excluded.alerted_at, "
                    "dispatched_at = excluded.dispatched_at, season = excluded.season, fetched_at = excluded.fetched_at",
                    [(f["id"], f["name"], f["status"], f["status_raw"], f["started_at"], f["controlled_at"], f["extinguished_at"],
                      f["area_ha"], f["lat"], f["lon"], f["comuna"], f["region"], f["ambito"], f["fuel"], f.get("detected_at"),
                      f.get("alerted_at"), f.get("dispatched_at"), f.get("season"), now, now) for f in fires])
        except Exception as exc:
            # Sin filas escritas no se toca el ETag: una etiqueta nueva con datos viejos haría que el
            # siguiente 304 se saltara el arreglo para siempre.
            self.finish_run(run_id, False, message=f"No se pudieron guardar los incendios ({type(exc).__name__})"[:500])
            raise
        # El ETag se guarda recién cuando las filas están escritas: si el guardado falla, se vuelve a
        # pedir el archivo completo en el ciclo siguiente.
        if result["etag"]:
            self.db.kv_set("conaf_etag", result["etag"])
        new = [f for f in fires if f["id"] not in known]
        # Un incendio ya conocido que CONAF da por controlado o extinguido merece un último
        # aviso a los lugares que ya fueron alertados (ALR-02): la familia deja de preocuparse.
        closed = [f for f in fires if f["id"] in known and f["status"] in ("controlado", "extinguido")
                  and known[f["id"]]["status"] != f["status"]]
        linked = await asyncio.to_thread(incidents_mod.link_official, self.db, fires)
        # FIX-10: con la tabla vacía (work.db restaurado) la primera carga sigue sin avisar en
        # masa, pero un incendio de las últimas 2 h sí avisa: ese se perdió por el vacío, no por viejo.
        cutoff = utcnow() - timedelta(hours=2)
        fresh = [f for f in new if f["status"] != "extinguido"
                 and datetime.fromisoformat(f["started_at"].replace("Z", "+00:00")) >= cutoff]
        created = await alerts_mod.evaluate_official(self.db, new if known else fresh)
        created += await alerts_mod.evaluate_status_change(self.db, closed)
        await self.deliver(created)
        # Una superficie imposible delata un formato decimal leído al revés: se deja dicho en la corrida.
        huge = [f for f in fires if (f.get("area_ha") or 0) > 500_000]
        notice = f"{len(huge)} filas con superficie sobre 500.000 ha: revisa el formato decimal" if huge else ""
        self.finish_run(run_id, True, len(fires), len(new), notice)
        return {"official_fires": len(fires), "official_new": len(new), "official_linked": linked,
                "official_alerts": len(created), "official_area_suspicious": len(huge)}

    def due(self, key: str, interval_s: float) -> bool:
        """¿Toca correr una tarea? Se apoya en la marca de tiempo que la tarea deja en `kv`.

        El Cron Trigger puede llamar cada minuto: sin esta guarda, DMC y lluvia se pedirían a su
        API en cada vuelta y el proveedor cortaría por cuota.
        """
        last = self.db.kv_get(key)
        return not last or (utcnow() - datetime.fromisoformat(last.replace("Z", "+00:00"))).total_seconds() >= interval_s

    def boton_rojo_due(self) -> bool:
        # FIX-11: tras un fallo el reintento espera 15 min × 2^fallos desde el último
        # intento (tope 3 h); con la última corrida buena manda la cadencia normal.
        fails = int(self.db.kv_get("boton_rojo_fails") or 0)
        if fails:
            return self.due("boton_rojo_try_at", min(3 * 3600, 900 * 2 ** fails))
        return self.due("boton_rojo_at", BOTON_ROJO_EVERY_H * 3600)

    def conaf_cond_due(self) -> bool:
        # Misma regla que Botón Rojo: tras un fallo, 15 min × 2^fallos (tope 3 h). Con una
        # tanda a medias se reanuda pronto; sin nada pendiente, la firma se revisa cada 3 h.
        fails = int(self.db.kv_get("conaf_cond_fails") or 0)
        if fails:
            return self.due("conaf_cond_try_at", min(3 * 3600, 900 * 2 ** fails))
        if self.db.kv_get("conaf_cond_pending"):
            return self.due("conaf_cond_try_at", CONAF_COND_BATCH_PAUSE_S)
        return self.due("conaf_cond_at", CONAF_COND_EVERY_H * 3600)

    # ------------------------------------------------------------------ alertas
    async def daily_brief(self, now: datetime | None = None) -> int:
        """Aviso preventivo diario (ALR-04): una pasada al día, en cuanto son las 08:00 en Chile.

        `daily_brief_at` guarda el día local ya atendido: el cron corre cada ~10 minutos y sin
        la marca las pasadas siguientes repetirían el barrido. Se escribe después de crear y
        entregar: si la corrida falla, el siguiente ciclo reintenta, y el `observation_id`
        `daily:<fecha>` impide duplicados aunque el corte haya dejado avisos a medias.
        """
        now = now or utcnow()
        local = now.astimezone(alerts_mod.CHILE_TZ)
        today = local.date().isoformat()
        if local.hour < 8 or self.db.kv_get("daily_brief_at") == today:
            return 0
        created = await alerts_mod.evaluate_daily(self.db, now)
        await self.deliver(created)
        self.db.kv_set("daily_brief_at", today)
        return len(created)

    async def deliver(self, created: list[dict[str, Any]]) -> None:
        token = self.settings.telegram_bot_token
        async with self._deliver_lock:
            # La alerta se escribe antes de mandarla: si el proceso se corta en medio, la fila
            # queda sin intento registrado (delivered_at nulo) y la próxima entrega la reintenta
            # desde la base — su detección ya está marcada como evaluada y no volvería a crearla.
            # El lock cubre consulta, envío y marca: dos tareas que entregaran a la vez
            # seleccionarían la misma pendiente y la mandarían dos veces.
            # Solo las todavía recientes: tras una caída de días nadie quiere un «foco cerca»
            # viejo. La ventana se mide sobre `created_at` (cuándo se generó el aviso), no
            # `observed_at` (cuándo empezó el fenómeno): un aviso `dmc:` nace con el onset del
            # CAP, que ya puede estar fuera de la cota al ingestarlo, y si el primer intento
            # quedaba a medias el pendiente nunca se recuperaba (REV-18). Cada tipo conserva
            # su ventana: CONAF 24 h; el resto usa la cota satelital de 6 h.
            sat_since = stamp(utcnow() - timedelta(hours=alerts_mod.MAX_AGE_H))
            conaf_since = stamp(utcnow() - timedelta(hours=alerts_mod.OFFICIAL_HOURS))
            created_ids = {a["id"] for a in created}   # las recién creadas también son pendientes
            pending = [row for row in self.db.query(
                "SELECT a.id, p.subscriber_id, a.payload FROM alerts a JOIN places p ON p.id = a.place_id "
                "WHERE a.delivered_at IS NULL AND a.created_at >= "
                "(CASE WHEN a.observation_id LIKE 'conaf:%' THEN ? ELSE ? END) ORDER BY a.id",
                (conaf_since, sat_since))
                if row["id"] not in created_ids]
            for alert in (*pending, *created):
                sub = self.db.one("SELECT * FROM subscribers WHERE id = ?", (alert["subscriber_id"],))
                if not sub:
                    self.db.execute("UPDATE alerts SET delivered_at = ? WHERE id = ?", (stamp(), alert["id"]))
                    continue
                payload = alert["payload"]
                if isinstance(payload, str):
                    payload = json.loads(payload)
                channels = []
                if sub.get("push_endpoint") and await asyncio.to_thread(webpush.send, self.db, sub, payload, self.settings.vapid_contact):
                    channels.append("push")
                if token and sub.get("telegram_chat_id"):
                    text = telegram.format_alert(payload, self._public_url)
                    if await telegram.send_message(self.client, token, sub["telegram_chat_id"], text):
                        channels.append("telegram")
                self.db.execute("UPDATE alerts SET delivered = ?, delivered_at = ? WHERE id = ?",
                                (json.dumps(channels), stamp(), alert["id"]))
            # ALR-10: un urgente ya entregado que sigue siendo el último aviso del lugar
            # se reenvía una sola vez; `reminded_at` garantiza que nunca haya un tercer envío.
            now = utcnow()
            for alert in self.db.query(
                    "SELECT a.id, a.place_id, a.level, a.created_at, a.delivered_at, a.reminded_at, "
                    "p.subscriber_id, a.payload FROM alerts a JOIN places p ON p.id = a.place_id "
                    "WHERE a.level = 'urgente' AND a.delivered_at IS NOT NULL AND a.reminded_at IS NULL "
                    "AND a.created_at <= ?", (stamp(now - timedelta(minutes=alerts_mod.ESCALATE_AFTER_MIN)),)):
                has_newer = self.db.one("SELECT 1 AS x FROM alerts WHERE place_id = ? AND id > ? LIMIT 1",
                                        (alert["place_id"], alert["id"])) is not None
                if not alerts_mod.escalation_due(alert, has_newer, now):
                    continue
                sub = self.db.one("SELECT * FROM subscribers WHERE id = ?", (alert["subscriber_id"],))
                if sub:
                    payload = alert["payload"]
                    if isinstance(payload, str):
                        payload = json.loads(payload)
                    payload = {**payload, "title": f"Recordatorio · {payload.get('title') or 'Aviso de BRASA'}"}
                    if sub.get("push_endpoint"):
                        await asyncio.to_thread(webpush.send, self.db, sub, payload, self.settings.vapid_contact)
                    if token and sub.get("telegram_chat_id"):
                        text = telegram.format_alert(payload, self._public_url)
                        await telegram.send_message(self.client, token, sub["telegram_chat_id"], text)
                self.db.execute("UPDATE alerts SET reminded_at = ? WHERE id = ?", (stamp(now), alert["id"]))


    async def ingest_cycle(self) -> dict[str, Any]:
        async with self._lock:
            # Una fuente caída no debe bloquear a la otra ni dejar sin registrar la revisión.
            # Se llaman las versiones internas: el ciclo ya tiene el lock y volver a tomarlo bloquearía.
            results = await asyncio.gather(self._ingest_firms(), self._ingest_goes(), return_exceptions=True)
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
            # Recuperable: si el proceso murió entre guardar la detección y avisar, el aviso sale
            # en este ciclo. Las ya avisadas quedan fuera por la propia consulta.
            recovered = await asyncio.to_thread(self.pending_alert_observations)
            if recovered:
                fresh = list({obs["id"]: obs for obs in fresh + recovered}.values())
            touched: list[dict[str, Any]] = []
            try:  # un error al agrupar no debe impedir los avisos: siguen saliendo, sin datos del incidente
                touched = await asyncio.to_thread(incidents_mod.update, self.db, fresh)
                await asyncio.to_thread(incidents_mod.expire, self.db)
            except Exception:
                log.exception("Agrupación de incidentes falló")
            created = await alerts_mod.evaluate(self.db, fresh, self.wind_at)
            # Se marca lo evaluado (avisara o no) para no reconsultarlo ni re-evaluarlo cada ciclo.
            if fresh:
                await asyncio.to_thread(self.mark_alerts_evaluated, fresh)
            await self.deliver(created)
            cutoff = stamp(utcnow() - timedelta(days=RETENTION_DAYS))
            self.db.execute("DELETE FROM observations WHERE observed_at < ?", (cutoff,))
            incidents_mod.prune(self.db, cutoff)
            self.db.cache_purge()
            try:  # la retención no debe impedir el ciclo: un fallo se registra y se reintenta a la próxima
                await self.purge_user_data()
            except Exception:
                log.exception("Retención de datos de personas falló")
            if len(failed) < 2:
                self.db.kv_set("last_ingest_at", stamp())
            return {"firms_new": len(news["firms"]), "goes_new": len(news["goes"]), "alerts": len(created),
                    "incidents": len(touched), "failed_sources": failed}

    async def purge_user_data(self) -> dict[str, int]:
        """Retención de datos de personas (FIX-21, Ley 21.719): lo que cumplió su plazo se borra.

        - Avisos de más de 12 meses (el historial ya no sirve para actuar).
        - Reportes sin verificar o descartados de más de 90 días: no se muestran y guardan
          coordenadas y una foto que ya no hacen falta.
        - Reportes verificados de más de 2 años.
        Las fotos se borran del disco; en R2 no hay DELETE, así que el objeto se sobrescribe
        con cero bytes (el Worker solo admite GET/PUT). Si el borrado de una foto falla, su
        reporte se conserva y el próximo ciclo lo reintenta: nunca queda una foto huérfana.
        La foto puede quedar vacía antes que su reporte: el dato se destruye lo antes posible
        y un reporte pendiente de borrado no necesita recuperarla.
        """
        stale = stamp(utcnow() - timedelta(days=REPORTS_STALE_DAYS))
        verified = stamp(utcnow() - timedelta(days=REPORTS_VERIFIED_DAYS))
        rows = self.db.query(
            "SELECT id, photo FROM reports WHERE (status = 'verificado' AND created_at < ?) "
            "OR (status != 'verificado' AND created_at < ?)", (verified, stale))
        photos = []
        pending = set()  # reportes cuya foto no se pudo borrar: se conservan para reintentar
        for row in rows:
            name = row["photo"]
            if not name:
                continue
            ok = True
            try:
                (self.settings.data_dir / "uploads" / name).unlink(missing_ok=True)
            except OSError as exc:
                log.warning("No se pudo borrar la foto %s: %s", name, exc)
                ok = False
            if self.storage:
                try:
                    await self.storage.put(f"photos/{name}", b"", "image/jpeg")
                except Exception as exc:
                    log.warning("No se pudo vaciar la foto remota %s: %s", name, exc)
                    ok = False
            if ok:
                photos.append(name)
            else:
                pending.add(row["id"])
        reports = self.db.execute(
            "DELETE FROM reports WHERE ((status = 'verificado' AND created_at < ?) OR (status != 'verificado' AND created_at < ?))"
            + (f" AND id NOT IN ({','.join('?' * len(pending))})" if pending else ""),
            (verified, stale, *pending))
        alerts = self.db.execute("DELETE FROM alerts WHERE created_at < ?",
                                 (stamp(utcnow() - timedelta(days=ALERTS_RETENTION_DAYS)),))
        # Testigos de reportes que ya no existen: el dispositivo que corroboró no puede quedar
        # guardado más allá del plazo del propio reporte.
        self.db.execute("DELETE FROM report_corroborations WHERE report_id NOT IN (SELECT id FROM reports)")
        if reports or alerts:
            log.info("Retención: %s reportes y %s avisos antiguos borrados (%s fotos)", reports, alerts, len(photos))
        return {"reports": reports, "alerts": alerts, "photos": len(photos)}

    async def tick_and_backup(self) -> dict[str, Any]:
        """Ciclo completo más respaldo; deja un resumen sin datos sensibles en `last_cycle`.

        El resumen se guarda también en `kv`: en Cloudflare el contenedor se suspende entre
        disparos del cron, así que la copia en memoria se pierde y `/api/status` no podría decir
        si el ciclo anterior terminó. Con esto, el estado se lee de la base y sobrevive.
        """
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
                                                               "dmc_alerts", "rain_comunas", "rain_normals", "risk_snapshots",
                                                               "official_fires", "official_new", "official_linked", "official_alerts",
                                                               "conaf_condiciones", "daily_brief")},
                           **{k: True for k in ("backfill_error", "risk_error", "boton_rojo_error", "official_error", "fwi_error",
                                                "dmc_error", "rain_error", "snapshot_error", "daily_brief_error",
                                                "conaf_cond_error") if k in result},
                           # Los errores del respaldo se muestran recortados: solo hablan de storage.brasa, sin datos sensibles.
                           **{k: str(result[k])[:200] for k in ("restore_error", "backup_error") if k in result}}
        self.db.kv_set("last_cycle", json.dumps(self.last_cycle, ensure_ascii=False))
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
        self.tasks.append(asyncio.create_task(
            self._loop("conaf-condiciones", self.ingest_conaf_condiciones, CONAF_COND_LOOP_S)))
        self.tasks.append(asyncio.create_task(self._loop("dmc", self.ingest_dmc, DMC_EVERY_H * 3600)))
        self.tasks.append(asyncio.create_task(self._loop("lluvia", self.rain_cycle, RAIN_EVERY_H * 3600)))
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

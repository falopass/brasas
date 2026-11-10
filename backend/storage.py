"""Respaldo remoto de los datos de las personas (brasa.db), de las fotos de reportes y, cada hora, de work.db.

work.db (observaciones e incidentes) se puede reconstruir, pero los incidentes llevan su historia: sin respaldo,
un reinicio del contenedor los partiría de cero. Se sube comprimida y su restauración es de mejor esfuerzo.

Se activa con BRASA_STORAGE_URL. En Cloudflare apunta a <URL pública>/_internal/storage: el Worker valida
el INTERNAL_TOKEN y guarda en R2, así que el contenedor no necesita credenciales de R2.
Cualquier servidor que acepte GET/PUT por ruta sirve igual (por ejemplo, para pruebas).
"""

from __future__ import annotations

import asyncio
import gzip
import logging
import time
from datetime import datetime, timezone

import httpx

from backend.db import Database
from backend.providers import _retry

log = logging.getLogger("brasa.storage")
DB_KEY = "db/brasa.db"
WORK_KEY = "db/work.db.gz"
WORK_EVERY_S = 3600
# El respaldo corre de fondo: tolera más espera que un barrido, sin martillar R2.
STORAGE_DELAYS = (1.0, 2.0, 4.0)  # 4 intentos, ~7 s de espera máxima por pedido


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def backup_reason(exc: BaseException) -> str:
    """Motivo público de un respaldo fallido, tipado y sin URLs ni credenciales.

    `sin_credenciales`: falta BRASA_STORAGE_URL o el almacenamiento responde 401/403.
    `red`: no hubo respuesta (timeout, DNS, conexión). `tamaño`: el archivo no cabe (413/507).
    """
    cause = getattr(exc, "cause", None) or exc  # _retry.Failure envuelve el error de httpx
    if isinstance(cause, httpx.HTTPStatusError):
        status = cause.response.status_code
        if status in (401, 403):
            return "sin_credenciales"
        if status in (413, 507):
            return "tamaño"
        return f"excepcion:HTTP{status}"
    if isinstance(cause, httpx.RequestError):
        return "red"
    return f"excepcion:{type(cause).__name__}"


class RemoteStorage:
    def __init__(self, base_url: str, client: httpx.AsyncClient, token: str = ""):
        self.base = base_url.rstrip("/")
        self.client = client
        self.headers = {"X-Internal-Token": token} if token else {}

    async def get(self, key: str) -> bytes | None:
        try:
            response = await _retry.request(
                self.client, "GET", f"{self.base}/{key}", delays=STORAGE_DELAYS, headers=self.headers, timeout=60
            )
        except _retry.Failure as exc:
            if isinstance(exc.cause, httpx.HTTPStatusError) and exc.cause.response.status_code == 404:
                return None
            raise
        return response.content

    async def put(self, key: str, content: bytes, content_type: str = "application/octet-stream") -> None:
        await _retry.request(
            self.client,
            "PUT",
            f"{self.base}/{key}",
            delays=STORAGE_DELAYS,
            content=content,
            headers={**self.headers, "Content-Type": content_type},
            timeout=60,
        )


class Persistence:
    """Restaura brasa.db al arrancar y la sube tras cada cambio (con unos segundos de espera para agrupar)."""

    def __init__(self, db: Database, storage: RemoteStorage | None, debounce_s: float = 3.0):
        self.db = db
        self.storage = storage
        self.debounce_s = debounce_s
        self._dirty = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        # Hasta confirmar el estado del respaldo no se sube nada: evita pisar un respaldo bueno con una base vacía.
        self.ready = storage is None
        # OPS-818: tiempos de la última restauración, para el desglose del arranque en /api/status.
        self.restore_work_ms: int | None = None
        self.restore_db_ms: int | None = None
        self.restore_work_parts: dict[str, int | None] = {}
        self.work_db_bytes: int | None = None

    @property
    def enabled(self) -> bool:
        return self.storage is not None

    async def restore(self) -> bool:
        if not self.storage:
            return False
        await self.restore_work()
        started = time.perf_counter()
        try:
            content = await self.storage.get(DB_KEY)
            if content is None:
                log.info("No hay respaldo previo: se parte con una base vacía.")
                self.ready = True
                return False
            try:
                await asyncio.to_thread(self.db.restore, content)
            except ValueError as exc:
                # El respaldo remoto quedó confirmado inservible: se sigue con la base local y
                # el próximo flush lo reemplaza. Si no, ningún dato nuevo volvería a respaldarse.
                log.warning("El respaldo remoto no sirve (%s); se conserva la base local.", exc)
                self.ready = True
                return False
            self.ready = True
            log.info("Datos restaurados desde el respaldo (%s KB).", len(content) // 1024)
            return True
        finally:
            self.restore_db_ms = round((time.perf_counter() - started) * 1000)

    async def flush(self) -> str | None:
        """Sube brasa.db. Devuelve None si subió, o el motivo tipado del fallo (OPS-44)."""
        if not self.storage:
            return "sin_credenciales"
        if not self.ready:
            raise RuntimeError("El respaldo aún no se ha restaurado; no se sobrescribe.")
        async with self._lock:
            # Se limpia antes del snapshot: una escritura que llegue durante la copia vuelve a
            # marcar el pendiente y se reintenta, aunque el respaldo ya la haya incluido.
            self._dirty.clear()
            try:
                content = await asyncio.to_thread(self.db.snapshot)
            except Exception as exc:
                # La copia falló (base bloqueada, disco lleno): el cambio sigue pendiente.
                self._dirty.set()
                log.warning("No se pudo respaldar la base: %s", exc)
                return self._record_reason(exc)
            try:
                await self.storage.put(DB_KEY, content, "application/vnd.sqlite3")
            except Exception as exc:
                # La subida falló: el cambio sigue pendiente para el próximo intento (bucle o stop).
                self._dirty.set()
                log.warning("No se pudo respaldar la base: %s", exc)
                return self._record_reason(exc)
            # OPS-18: tamaño del respaldo en kv para vigilar el crecimiento desde /api/status.
            self._kv("backup_bytes", str(len(content)))
            self._kv("backup_at", _stamp())
            self._kv("backup_reason", "")
        return None

    def _record_reason(self, exc: BaseException) -> str:
        """Guarda el motivo en kv para que /api/status lo publique tras un reinicio."""
        reason = backup_reason(exc)
        try:
            self._kv("backup_reason", reason)
        except Exception:  # el motivo no puede tapar el fallo original
            log.warning("No se pudo registrar el motivo del respaldo.")
        return reason

    async def restore_work(self) -> bool:
        """Recupera observaciones e incidentes. Si falla, se sigue: los datos de trabajo se vuelven a juntar.

        OPS-818: mide por separado la descarga, la descompresión y la verificación más copia:
        es lo que más tarda el arranque en frío y sin el desglose no se sabe cuánto es cada parte.
        """
        total = time.perf_counter()
        parts: dict[str, int | None] = {"download_ms": None, "gunzip_ms": None, "check_copy_ms": None}

        def _ms(since: float) -> int:
            return round((time.perf_counter() - since) * 1000)

        try:
            t = time.perf_counter()
            content = await self.storage.get(WORK_KEY)
            parts["download_ms"] = _ms(t)
            if content is None:
                return False
            t = time.perf_counter()
            raw = await asyncio.to_thread(gzip.decompress, content)
            parts["gunzip_ms"] = _ms(t)
            t = time.perf_counter()
            await asyncio.to_thread(self.db.restore_work, raw)
            parts["check_copy_ms"] = _ms(t)
        except Exception as exc:
            log.warning("No se pudo restaurar work.db: %s", exc)
            return False
        finally:
            self.restore_work_ms = _ms(total)
            self.restore_work_parts = parts
        # Tamaño lógico de la base restaurada (page_count × page_size): coincide con lo que
        # pesaba el respaldo y con lo que ocupará el archivo al integrarse el -wal. El stat()
        # del archivo no sirve aquí porque la copia queda en el -wal mientras otras conexiones
        # la tienen abierta; tampoco sumamos el -wal: esto mide datos, no espacio en disco.
        pages = self.db.one("PRAGMA work.page_count")["page_count"]
        self.work_db_bytes = pages * self.db.one("PRAGMA work.page_size")["page_size"]
        log.info("Datos de trabajo restaurados (%s KB comprimidos).", len(content) // 1024)
        return True

    async def flush_work(self, force: bool = False) -> bool:
        """Sube work.db si pasó una hora desde la última subida (o si se fuerza). Devuelve si subió.

        La hora la manda `work_backup_at` en kv: es reloj de pared y sobrevive al reinicio. Con un
        contador del proceso no alcanzaba nunca a cumplirse, porque el contenedor duerme entre
        ciclos del cron y despierta con el reloj a cero (issue de monitoreo del 24-10).
        """
        if not self.storage or not self.ready:
            return False
        if not force and self._edad_respaldo_work() < WORK_EVERY_S:
            return False
        content = await asyncio.to_thread(lambda: gzip.compress(self.db.snapshot_work(), 6))
        try:
            await self.storage.put(WORK_KEY, content, "application/gzip")
        except Exception as exc:
            # Un fallo de subida no corta el ciclo: se reintenta en la próxima vuelta (o al cerrar).
            log.warning("No se pudo respaldar work.db: %s", exc)
            return False
        self._kv("work_backup_bytes", str(len(content)))
        self._kv("work_backup_at", _stamp())
        return True

    def _edad_respaldo_work(self) -> float:
        """Segundos desde el último respaldo de work.db; infinito si no hay marca legible."""
        marca = self.db.kv_get("work_backup_at")
        if not marca:
            return float("inf")
        try:
            subido = datetime.fromisoformat(marca.replace("Z", "+00:00"))
        except ValueError:
            return float("inf")
        if subido.tzinfo is None:
            subido = subido.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - subido).total_seconds()

    def _kv(self, key: str, value: str) -> None:
        """Igual que db.kv_set pero sin notificar: kv es escritura de usuario y reactivaría el bucle."""
        with self.db.connect() as conn:
            conn.execute("INSERT INTO kv(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))

    def mark_dirty(self) -> None:
        if self.storage:
            self._dirty.set()

    def start(self) -> None:
        if self.storage and self._task is None:
            self._task = asyncio.create_task(self._loop())

    async def _loop(self) -> None:
        while True:
            await self._dirty.wait()
            await asyncio.sleep(self.debounce_s)
            try:
                reason = await self.flush()
            except Exception as exc:  # se reintenta con el próximo cambio
                log.warning("No se pudo respaldar la base: %s", exc)
                self._dirty.set()
                reason = backup_reason(exc)
            if reason is not None:
                await asyncio.sleep(15)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        if self.storage and self._dirty.is_set():
            try:
                await self.flush()
            except Exception as exc:
                log.warning("Respaldo final falló: %s", exc)
        try:
            await self.flush_work(force=True)
        except Exception as exc:
            log.warning("Respaldo final de work.db falló: %s", exc)

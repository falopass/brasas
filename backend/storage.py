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

import httpx

from backend.db import Database

log = logging.getLogger("brasa.storage")
DB_KEY = "db/brasa.db"
WORK_KEY = "db/work.db.gz"
WORK_EVERY_S = 3600


class RemoteStorage:
    def __init__(self, base_url: str, client: httpx.AsyncClient, token: str = ""):
        self.base = base_url.rstrip("/")
        self.client = client
        self.headers = {"X-Internal-Token": token} if token else {}

    async def get(self, key: str) -> bytes | None:
        response = await self.client.get(f"{self.base}/{key}", headers=self.headers, timeout=60)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.content

    async def put(self, key: str, content: bytes, content_type: str = "application/octet-stream") -> None:
        response = await self.client.put(f"{self.base}/{key}", content=content, headers={**self.headers, "Content-Type": content_type}, timeout=60)
        response.raise_for_status()


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
        self._work_at = 0.0

    @property
    def enabled(self) -> bool:
        return self.storage is not None

    async def restore(self) -> bool:
        if not self.storage:
            return False
        await self.restore_work()
        content = await self.storage.get(DB_KEY)
        if content is None:
            log.info("No hay respaldo previo: se parte con una base vacía.")
            self.ready = True
            return False
        await asyncio.to_thread(self.db.restore, content)
        self.ready = True
        log.info("Datos restaurados desde el respaldo (%s KB).", len(content) // 1024)
        return True

    async def flush(self) -> bool:
        if not self.storage:
            return False
        if not self.ready:
            raise RuntimeError("El respaldo aún no se ha restaurado; no se sobrescribe.")
        async with self._lock:
            self._dirty.clear()
            content = await asyncio.to_thread(self.db.snapshot)
            await self.storage.put(DB_KEY, content, "application/vnd.sqlite3")
        return True

    async def restore_work(self) -> bool:
        """Recupera observaciones e incidentes. Si falla, se sigue: los datos de trabajo se vuelven a juntar."""
        try:
            content = await self.storage.get(WORK_KEY)
            if content is None:
                return False
            await asyncio.to_thread(lambda: self.db.restore_work(gzip.decompress(content)))
        except Exception as exc:
            log.warning("No se pudo restaurar work.db: %s", exc)
            return False
        self._work_at = time.monotonic()  # recién restaurada: no hace falta subirla de inmediato
        log.info("Datos de trabajo restaurados (%s KB comprimidos).", len(content) // 1024)
        return True

    async def flush_work(self, force: bool = False) -> bool:
        """Sube work.db si pasó una hora desde la última vez (o si se fuerza). Devuelve si subió."""
        if not self.storage or not self.ready:
            return False
        if not force and self._work_at and time.monotonic() - self._work_at < WORK_EVERY_S:
            return False
        content = await asyncio.to_thread(lambda: gzip.compress(self.db.snapshot_work(), 6))
        await self.storage.put(WORK_KEY, content, "application/gzip")
        self._work_at = time.monotonic()
        return True

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
                await self.flush()
            except Exception as exc:  # se reintenta con el próximo cambio
                log.warning("No se pudo respaldar la base: %s", exc)
                self._dirty.set()
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

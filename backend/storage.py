"""Respaldo remoto de los datos de las personas (brasa.db) y de las fotos de reportes.

Se activa con BRASA_STORAGE_URL. En Cloudflare apunta a <URL pública>/_internal/storage: el Worker valida
el INTERNAL_TOKEN y guarda en R2, así que el contenedor no necesita credenciales de R2.
Cualquier servidor que acepte GET/PUT por ruta sirve igual (por ejemplo, para pruebas).
"""
from __future__ import annotations

import asyncio
import logging

import httpx

from backend.db import Database

log = logging.getLogger("brasa.storage")
DB_KEY = "db/brasa.db"


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

    @property
    def enabled(self) -> bool:
        return self.storage is not None

    async def restore(self) -> bool:
        if not self.storage:
            return False
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

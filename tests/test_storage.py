"""QA-29: `Persistence` (backend/storage.py) decide si brasa.db y work.db sobreviven a un reinicio.

Lo que no puede cambiar: sin almacenamiento remoto todo es un no-op inofensivo; un respaldo
dañado no debe romper la base local; una subida que falla deja el cambio pendiente para el
próximo intento; work.db se sube a lo más una vez por hora salvo que se fuerce; y el bucle
de respaldo arranca y se detiene limpio.
"""
from __future__ import annotations

import asyncio
import gzip
import sqlite3
import time

import pytest

from backend.db import Database
from backend.storage import DB_KEY, WORK_KEY, Persistence


class FakeStorage:
    """Doble en memoria de RemoteStorage, sin red. `fail_put` simula un corte de red."""

    def __init__(self, files: dict[str, bytes] | None = None):
        self.files = dict(files or {})
        self.puts: list[tuple[str, bytes, str]] = []  # (key, content, content_type) subidos
        self.fail_put = False

    async def get(self, key: str):
        return self.files.get(key)

    async def put(self, key: str, content: bytes, content_type: str = "application/octet-stream"):
        if self.fail_put:
            raise OSError("red caída")
        self.puts.append((key, content, content_type))
        self.files[key] = content


def make_backup(tmp_path) -> dict[str, bytes]:
    """Respaldos remotos válidos: una brasa.db con un dato y la work.db de esa misma base."""
    src = Database(tmp_path / "origen.db", tmp_path / "origen-work.db")
    src.kv_set("saludo", "hola")
    src.insert("INSERT INTO work.ingest_runs(provider, product, started_at) VALUES (?,?,?)",
               ("prueba", "demo", "2027-01-01T00:00:00Z"))
    return {DB_KEY: src.snapshot(), WORK_KEY: gzip.compress(src.snapshot_work(), 6)}


def integrity_ok(path) -> bool:
    conn = sqlite3.connect(path)
    try:
        return conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        conn.close()


def test_disabled_without_remote_storage(tmp_path):
    async def main():
        p = Persistence(Database(tmp_path / "brasa.db"), None)
        assert p.enabled is False
        assert await p.restore() is False
        assert await p.flush() is False
        p.mark_dirty()  # no debe lanzar
        p.start()
        await p.stop()
    asyncio.run(main())


def test_restore_writes_the_database_from_the_backup(tmp_path):
    async def main():
        storage = FakeStorage(make_backup(tmp_path))
        db = Database(tmp_path / "brasa.db")
        assert await Persistence(db, storage).restore() is True
        assert db.kv_get("saludo") == "hola"
        assert db.one("SELECT provider FROM work.ingest_runs")["provider"] == "prueba"
    asyncio.run(main())


def test_a_damaged_backup_does_not_break_the_local_database(tmp_path):
    async def main():
        storage = FakeStorage({DB_KEY: b"esto no es una base sqlite"})
        db = Database(tmp_path / "brasa.db")
        p = Persistence(db, storage)
        assert await p.restore() is False
        assert integrity_ok(db.path) and db.is_empty()  # la base local quedó intacta
        # El respaldo remoto quedó confirmado inservible: el próximo flush lo reemplaza.
        assert await p.flush() is True
        assert storage.files[DB_KEY].startswith(b"SQLite format 3")
    asyncio.run(main())


def test_flush_never_overwrites_before_restore(tmp_path):
    async def main():
        p = Persistence(Database(tmp_path / "brasa.db"), FakeStorage())
        with pytest.raises(RuntimeError):
            await p.flush()
    asyncio.run(main())


def test_a_failed_flush_stays_dirty_and_retries(tmp_path):
    async def main():
        storage = FakeStorage(make_backup(tmp_path))
        db = Database(tmp_path / "brasa.db")
        p = Persistence(db, storage)
        assert await p.restore() is True
        storage.fail_put = True
        p.mark_dirty()
        assert await p.flush() is False
        assert p._dirty.is_set()  # sigue pendiente: el bucle lo reintenta solo
        storage.fail_put = False
        assert await p.flush() is True
        assert storage.puts[-1][0] == DB_KEY
        assert storage.files[DB_KEY].startswith(b"SQLite format 3")
    asyncio.run(main())


def test_flush_work_uploads_once_per_hour_unless_forced(tmp_path):
    async def main():
        storage = FakeStorage(make_backup(tmp_path))
        db = Database(tmp_path / "brasa.db")
        p = Persistence(db, storage)
        assert await p.restore() is True  # work.db recién restaurada: aún no hay nada que subir
        assert await p.flush_work() is False
        assert all(key != WORK_KEY for key, _, _ in storage.puts)
        assert await p.flush_work(force=True) is True
        assert storage.puts[-1][0] == WORK_KEY
        assert gzip.decompress(storage.puts[-1][1]).startswith(b"SQLite format 3")
    asyncio.run(main())


def test_the_backup_loop_flushes_changes_and_stops_clean(tmp_path):
    async def main():
        storage = FakeStorage(make_backup(tmp_path))
        db = Database(tmp_path / "brasa.db")
        p = Persistence(db, storage, debounce_s=0.01)
        assert await p.restore() is True
        p.start()
        p.mark_dirty()
        for _ in range(200):  # el bucle agrupa el cambio y lo sube solo
            if any(key == DB_KEY for key, _, _ in storage.puts):
                break
            await asyncio.sleep(0.01)
        assert any(key == DB_KEY for key, _, _ in storage.puts)
        p.mark_dirty()  # un cambio de último minuto, pendiente al cerrar
        started = time.monotonic()
        await p.stop()
        assert time.monotonic() - started < 1.0
        assert p._task is not None and p._task.done()
        keys = [key for key, _, _ in storage.puts]
        assert keys.count(DB_KEY) >= 2  # stop() respaldó el cambio pendiente
        assert WORK_KEY in keys         # y subió work.db al cerrar
    asyncio.run(main())

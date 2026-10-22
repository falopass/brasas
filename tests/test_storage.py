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

import httpx
import pytest

from backend.db import Database
from backend.providers import _retry
from backend.storage import DB_KEY, STORAGE_DELAYS, WORK_KEY, Persistence, RemoteStorage


@pytest.fixture
def sleeps(monkeypatch):
    """Espía que reemplaza `asyncio.sleep` y anota cada espera pedida (como en test_retry)."""
    waits: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        waits.append(seconds)

    monkeypatch.setattr(_retry.asyncio, "sleep", fake_sleep)
    # Estas pruebas miden las esperas reales: se deshace el «sin espera» global de conftest.
    import backend.storage as storage_mod
    monkeypatch.setattr(storage_mod, "STORAGE_DELAYS", STORAGE_DELAYS)
    return waits


def remote(handler) -> RemoteStorage:
    return RemoteStorage("https://respaldo.test", httpx.AsyncClient(transport=httpx.MockTransport(handler)))


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
    src.insert("INSERT INTO work.ingest_runs(provider, product, started_at) VALUES (?,?,?)", ("prueba", "demo", "2027-01-01T00:00:00Z"))
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
        assert await p.flush() == "sin_credenciales"
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
        assert await p.flush() is None
        assert storage.files[DB_KEY].startswith(b"SQLite format 3")

    asyncio.run(main())


def test_flush_never_overwrites_before_restore(tmp_path):
    async def main():
        p = Persistence(Database(tmp_path / "brasa.db"), FakeStorage())
        with pytest.raises(RuntimeError):
            await p.flush()

    asyncio.run(main())


@pytest.mark.parametrize(("where", "reason"), [("put", "excepcion:OSError"), ("snapshot", "excepcion:RuntimeError")])
def test_un_fallo_de_respaldo_sigue_pendiente_y_reintenta(tmp_path, where, reason):
    """Ni una subida caída ni un `snapshot()` que lanza borran el cambio pendiente."""

    async def main():
        storage = FakeStorage(make_backup(tmp_path))
        db = Database(tmp_path / "brasa.db")
        p = Persistence(db, storage)
        assert await p.restore() is True
        if where == "put":
            storage.fail_put = True
        else:

            def locked():
                raise RuntimeError("database is locked")

            db.snapshot = locked
        p.mark_dirty()
        assert await p.flush() == reason
        if where == "put":
            assert db.kv_get("backup_reason") == reason
        assert p._dirty.is_set()  # sigue pendiente: el bucle lo reintenta solo
        storage.fail_put = False
        if where == "snapshot":
            del db.snapshot  # vuelve el método real
        assert await p.flush() is None
        if where == "put":
            assert db.kv_get("backup_reason") == ""  # al subir se limpia el motivo anterior
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
        storage.fail_put = True
        assert await p.flush_work(force=True) is False  # no lanza: el ciclo lo reintenta luego
        assert db.kv_get("work_backup_at") is None
        storage.fail_put = False
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
        assert WORK_KEY in keys  # y subió work.db al cerrar

    asyncio.run(main())


def test_get_permanent_502_raises_after_retries(sleeps):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(502)

    async def main():
        return await remote(handler).get(DB_KEY)

    with pytest.raises(_retry.Failure) as excinfo:
        asyncio.run(main())
    total = len(STORAGE_DELAYS) + 1
    assert excinfo.value.attempts == total
    assert len(calls) == total
    assert sleeps == list(STORAGE_DELAYS)


@pytest.mark.parametrize(
    ("failure", "reason"),
    [(401, "sin_credenciales"), (403, "sin_credenciales"), (413, "tamaño"), (418, "excepcion:HTTP418"), ("red", "red")],
)
def test_flush_reason_maps_failures(tmp_path, sleeps, failure, reason):
    """OPS-44: el motivo distingue credenciales, tamaño, red y el resto sin exponer la URL."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(404)
        if failure == "red":
            raise httpx.ConnectError("sin red")
        return httpx.Response(failure)

    async def main():
        db = Database(tmp_path / "brasa.db")
        p = Persistence(db, remote(handler))
        assert await p.restore() is False
        assert await p.flush() == reason
        assert db.kv_get("backup_reason") == reason

    asyncio.run(main())


def test_flush_survives_a_transient_502(tmp_path, sleeps):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.method == "GET":
            return httpx.Response(404)
        puts = sum(1 for call in calls if call.method == "PUT")
        return httpx.Response(502 if puts == 1 else 200)

    async def main():
        db = Database(tmp_path / "brasa.db")
        p = Persistence(db, remote(handler))
        assert await p.restore() is False  # sin respaldo previo: queda listo para subir
        assert await p.flush() is None
        assert db.kv_get("backup_at") is not None

    asyncio.run(main())
    assert sum(1 for call in calls if call.method == "PUT") == 2

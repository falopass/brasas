"""OPS-18: el tamaño de los respaldos queda en kv y /api/status lo publica.

Lo que no puede cambiar: tras cada subida exitosa se registra el largo exacto del contenido
subido (el gzip en work.db) y su marca de tiempo; si el put falla, no se registra un tamaño
falso; y /api/status devuelve nulls cuando aún no hay respaldo.
"""

from __future__ import annotations

import asyncio
import gzip

from backend.db import Database
from backend.storage import DB_KEY, WORK_KEY, Persistence

from tests.test_storage import FakeStorage, make_backup


def test_flush_records_backup_size(tmp_path):
    async def main():
        storage = FakeStorage(make_backup(tmp_path))
        db = Database(tmp_path / "brasa.db")
        p = Persistence(db, storage)
        assert await p.restore() is True
        assert await p.flush() is True
        assert await p.flush_work(force=True) is True
        uploaded = dict((key, content) for key, content, _ in storage.puts)
        assert int(db.kv_get("backup_bytes")) == len(uploaded[DB_KEY])
        assert db.kv_get("backup_at") is not None
        # El valor publicado es el tamaño comprimido, no el de la base sin comprimir.
        assert int(db.kv_get("work_backup_bytes")) == len(uploaded[WORK_KEY])
        assert int(db.kv_get("work_backup_bytes")) == len(gzip.compress(db.snapshot_work(), 6))
        assert db.kv_get("work_backup_at") is not None

    asyncio.run(main())


def test_a_failed_put_leaves_no_fake_size(tmp_path):
    async def main():
        storage = FakeStorage(make_backup(tmp_path))
        db = Database(tmp_path / "brasa.db")
        p = Persistence(db, storage)
        assert await p.restore() is True
        storage.fail_put = True
        assert await p.flush() is False
        assert db.kv_get("backup_bytes") is None
        try:
            await p.flush_work(force=True)
        except OSError:
            pass
        assert db.kv_get("work_backup_bytes") is None

    asyncio.run(main())


def test_status_publishes_backup_sizes(make_client):
    with make_client() as client:
        body = client.get("/api/status").json()
        assert body["backup"] == {"bytes": None, "updated_at": None, "work_bytes": None, "work_updated_at": None}
        svc = client.app.state.services
        svc.db.kv_set("backup_bytes", "12345")
        svc.db.kv_set("backup_at", "2026-10-19T00:00:00Z")
        svc.db.kv_set("work_backup_bytes", "678")
        svc.db.kv_set("work_backup_at", "2026-10-19T01:00:00Z")
        backup = client.get("/api/status").json()["backup"]
        assert backup == {
            "bytes": 12345,
            "updated_at": "2026-10-19T00:00:00Z",
            "work_bytes": 678,
            "work_updated_at": "2026-10-19T01:00:00Z",
        }

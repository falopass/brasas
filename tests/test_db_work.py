"""DEBT-12: la caché de work.db se purga al abrir y WORK_TABLES cubre todo el esquema.

`cache_purge` existía desde el primer día sin ninguna llamada, así que las filas vencidas
se quedaban para siempre y se pagaban en cada respaldo horario de work.db a R2. Y la lista
de tablas de trabajo no incluía `risk_snapshot` ni `report_corroborations`, así que la
limpieza de instalaciones v0.2 no las borraba de brasa.db (una tabla que sobrevive en main
gana sobre la de work y se escribe en el archivo que se respalda como dato de personas).
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from backend.db import WORK_TABLES, Database, _snapshot_file

ROOT = Path(__file__).resolve().parents[1]


def test_work_tables_cover_every_table_in_the_schema():
    """Guarda contra la desincronización: la lista debe ser igual al esquema de work.db."""
    source = (ROOT / "backend" / "db.py").read_text(encoding="utf-8")
    declared = set(re.findall(r"CREATE TABLE IF NOT EXISTS work\.(\w+)", source))
    assert declared == set(WORK_TABLES)


def test_opening_the_base_purges_expired_cache_rows(tmp_path):
    path = tmp_path / "brasa.db"
    db = Database(path)
    db.insert("INSERT INTO subscribers(id, created_at) VALUES ('s1', '2027-01-01T00:00:00Z')")
    db.cache_set("vencida", {"valor": 1}, ttl_seconds=-60)
    db.cache_set("vigente", {"valor": 2}, ttl_seconds=3600)
    # Contrato intacto: una clave vencida se lee como ausente, aunque la fila exista.
    assert db.cache_get("vencida") is None
    db.close_all()

    db = Database(path)  # reabrir corre la purga sobre el mismo work.db
    assert db.one("SELECT COUNT(*) AS n FROM work.cache")["n"] == 1
    assert db.one("SELECT key FROM work.cache")["key"] == "vigente"
    assert db.cache_get("vigente") == {"valor": 2}
    assert db.one("SELECT COUNT(*) AS n FROM subscribers")["n"] == 1  # la purga no toca brasa.db


def test_snapshot_work_is_compact_restores_and_keeps_wal(tmp_path):
    """OPS-818: el respaldo de work.db se genera con `VACUUM INTO` —sin páginas libres, el
    archivo que sube a R2 sí se achica tras la poda— y `restore_work` lo acepta igual,
    con la base viva quedando en WAL tras restaurar."""
    db = Database(tmp_path / "brasa.db")
    db.cache_set("x", "y", ttl_seconds=9e12)
    # Páginas libres de verdad: se siembran filas grandes, se borran y se baja el WAL al archivo.
    big = "9" * 8_000
    for i in range(50):
        db.cache_set(f"tmp{i}", big, ttl_seconds=9e12)
    for i in range(50):
        db.execute("DELETE FROM cache WHERE key = ?", (f"tmp{i}",))
    with db.connect() as conn:
        conn.execute("PRAGMA work.wal_checkpoint(TRUNCATE)")
    assert db.one("PRAGMA work.freelist_count")["freelist_count"] > 0

    old_snapshot = _snapshot_file(db.work_path)  # respaldo hecho con el método anterior
    compact = db.snapshot_work()

    snap_path = tmp_path / "snap.db"
    snap_path.write_bytes(compact)
    conn = sqlite3.connect(snap_path)
    assert conn.execute("PRAGMA freelist_count").fetchone()[0] == 0
    conn.close()
    assert len(compact) < len(old_snapshot)  # ya no arrastra el hueco de las páginas libres

    fresh = Database(tmp_path / "b" / "brasa.db")
    fresh.restore_work(compact)
    assert fresh.cache_get("x") == "y"
    assert fresh.one("PRAGMA work.journal_mode")["journal_mode"] == "wal"

    # Y un respaldo hecho con el método anterior (API de backup) sigue restaurándose:
    # un despliegue debe poder leer lo que subió la versión previa.
    older = Database(tmp_path / "c" / "brasa.db")
    older.restore_work(old_snapshot)
    assert older.cache_get("x") == "y"
    assert older.one("PRAGMA work.journal_mode")["journal_mode"] == "wal"

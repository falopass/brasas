"""DEBT-12: la caché de work.db se purga al abrir y WORK_TABLES cubre todo el esquema.

`cache_purge` existía desde el primer día sin ninguna llamada, así que las filas vencidas
se quedaban para siempre y se pagaban en cada respaldo horario de work.db a R2. Y la lista
de tablas de trabajo no incluía `risk_snapshot` ni `report_corroborations`, así que la
limpieza de instalaciones v0.2 no las borraba de brasa.db (una tabla que sobrevive en main
gana sobre la de work y se escribe en el archivo que se respalda como dato de personas).
"""

from __future__ import annotations

import re
from pathlib import Path

from backend.db import WORK_TABLES, Database

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

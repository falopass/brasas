"""Persistencia local en SQLite, en dos archivos.

- brasa.db ("main"): datos de las personas que no se pueden reconstruir —dispositivos, lugares,
  alertas, reportes y claves (VAPID, Telegram)—. Es pequeña y es la que se respalda (por ejemplo,
  en R2 al desplegar en Cloudflare).
- work.db ("work", adjunta): observaciones, procedencia de ingestas, riesgo y caché. Se reconstruye
  sola con la ingesta, así que no se respalda.

SQLite resuelve los nombres de tabla sin prefijo buscando en main y luego en las bases adjuntas,
por lo que las consultas no necesitan saber en qué archivo vive cada tabla.
El esquema replica las entidades del diseño PostGIS de docs/ARQUITECTURA.md.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

WORK_TABLES = ("ingest_runs", "observations", "risk_daily", "risk_hourly", "cache")
_USER_WRITE = re.compile(r"^\s*(insert|update|delete|replace)\b.*?\b(subscribers|places|alerts|reports|kv)\b", re.I | re.S)

WORK_SCHEMA = """
CREATE TABLE IF NOT EXISTS work.ingest_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  provider TEXT NOT NULL,
  product TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  ok INTEGER NOT NULL DEFAULT 0,
  n_records INTEGER NOT NULL DEFAULT 0,
  n_new INTEGER NOT NULL DEFAULT 0,
  source_ref TEXT,
  sha256 TEXT,
  message TEXT
);
CREATE INDEX IF NOT EXISTS work.ingest_runs_product ON ingest_runs(product, started_at DESC);
CREATE INDEX IF NOT EXISTS work.ingest_runs_ref ON ingest_runs(source_ref);

CREATE TABLE IF NOT EXISTS work.observations (
  id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  sensor TEXT,
  satellite TEXT,
  resolution_m INTEGER,
  lat REAL NOT NULL,
  lon REAL NOT NULL,
  observed_at TEXT NOT NULL,
  frp_mw REAL,
  brightness_k REAL,
  confidence TEXT,
  confidence_raw TEXT,
  comuna_code INTEGER,
  run_id INTEGER,
  ingested_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS work.observations_time ON observations(observed_at DESC);
CREATE INDEX IF NOT EXISTS work.observations_comuna ON observations(comuna_code, observed_at DESC);

CREATE TABLE IF NOT EXISTS work.risk_daily (
  comuna_code INTEGER NOT NULL,
  date TEXT NOT NULL,
  level TEXT NOT NULL,
  score INTEGER NOT NULL,
  hours_3of3 INTEGER NOT NULL,
  hours_2of3 INTEGER NOT NULL,
  tmax REAL, rhmin REAL, windmax REAL, gustmax REAL,
  computed_at TEXT NOT NULL,
  PRIMARY KEY (comuna_code, date)
);

CREATE TABLE IF NOT EXISTS work.risk_hourly (
  comuna_code INTEGER PRIMARY KEY,
  computed_at TEXT NOT NULL,
  payload TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS work.cache (
  key TEXT PRIMARY KEY,
  expires_at REAL NOT NULL,
  payload TEXT NOT NULL
);
"""

USER_SCHEMA = """
CREATE TABLE IF NOT EXISTS subscribers (
  id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  push_endpoint TEXT,
  push_p256dh TEXT,
  push_auth TEXT,
  telegram_chat_id TEXT,
  link_code TEXT UNIQUE
);

CREATE TABLE IF NOT EXISTS places (
  id TEXT PRIMARY KEY,
  subscriber_id TEXT NOT NULL REFERENCES subscribers(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'casa',
  lat REAL NOT NULL,
  lon REAL NOT NULL,
  radius_km REAL NOT NULL DEFAULT 10,
  comuna_code INTEGER,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS places_subscriber ON places(subscriber_id);

CREATE TABLE IF NOT EXISTS alerts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  place_id TEXT NOT NULL REFERENCES places(id) ON DELETE CASCADE,
  observation_id TEXT NOT NULL,
  level TEXT NOT NULL,
  distance_km REAL NOT NULL,
  bearing_deg REAL NOT NULL,
  upwind INTEGER NOT NULL DEFAULT 0,
  lat REAL NOT NULL,
  lon REAL NOT NULL,
  observed_at TEXT NOT NULL,
  created_at TEXT NOT NULL,
  payload TEXT NOT NULL,
  delivered TEXT NOT NULL DEFAULT '[]',
  UNIQUE(place_id, observation_id)
);
CREATE INDEX IF NOT EXISTS alerts_place ON alerts(place_id, created_at DESC);

CREATE TABLE IF NOT EXISTS reports (
  id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  lat REAL NOT NULL,
  lon REAL NOT NULL,
  comuna_code INTEGER,
  kind TEXT NOT NULL,
  description TEXT NOT NULL,
  photo TEXT,
  status TEXT NOT NULL DEFAULT 'no_verificado',
  moderated_at TEXT,
  moderator_note TEXT
);
CREATE INDEX IF NOT EXISTS reports_status ON reports(status, created_at DESC);

CREATE TABLE IF NOT EXISTS kv (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: Path, work_path: Path | None = None):
        self.path = path
        self.work_path = work_path or path.with_name("work.db")
        self.on_user_write = None  # callback: se llama tras escribir datos de las personas
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA work.journal_mode = WAL")
            # Instalaciones v0.2 previas tenían todo en brasa.db: esas tablas son reconstruibles.
            conn.execute("PRAGMA foreign_keys = OFF")  # observations → ingest_runs: el orden de borrado no importa así
            for table in WORK_TABLES:
                if conn.execute("SELECT 1 FROM main.sqlite_master WHERE type = 'table' AND name = ?", (table,)).fetchone():
                    conn.execute(f"DROP TABLE main.{table}")
            conn.execute("PRAGMA foreign_keys = ON")
            conn.executescript(USER_SCHEMA + WORK_SCHEMA)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("ATTACH DATABASE ? AS work", (str(self.work_path),))
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def query(self, sql: str, params: tuple | dict = ()) -> list[dict[str, Any]]:
        with self.connect() as conn:
            return [dict(row) for row in conn.execute(sql, params).fetchall()]

    def one(self, sql: str, params: tuple | dict = ()) -> dict[str, Any] | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def execute(self, sql: str, params: tuple | dict = ()) -> int:
        """Ejecuta y devuelve el número de filas afectadas."""
        with self.connect() as conn:
            count = conn.execute(sql, params).rowcount
        self._notify(sql, count)
        return count

    def _notify(self, sql: str, count: int) -> None:
        if count and self.on_user_write and _USER_WRITE.match(sql):
            self.on_user_write()

    def insert(self, sql: str, params: tuple | dict = ()) -> int:
        """Inserta y devuelve el id de la fila nueva (0 si INSERT OR IGNORE no insertó nada)."""
        with self.connect() as conn:
            cursor = conn.execute(sql, params)
            row_id = cursor.lastrowid if cursor.rowcount else 0
        self._notify(sql, 1 if row_id else 0)
        return row_id

    # --- respaldo de los datos de las personas (solo brasa.db) ---
    def snapshot(self) -> bytes:
        """Copia consistente de brasa.db (API de respaldo de SQLite), aunque haya escrituras en curso."""
        fd, tmp = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            src = sqlite3.connect(self.path, timeout=30)
            dst = sqlite3.connect(tmp)
            with dst:
                src.backup(dst)
            src.close()
            dst.execute("PRAGMA journal_mode = DELETE")
            dst.close()
            return Path(tmp).read_bytes()
        finally:
            Path(tmp).unlink(missing_ok=True)

    def restore(self, content: bytes) -> None:
        """Reemplaza brasa.db con un respaldo, tras verificar que es una base SQLite íntegra."""
        if not content.startswith(b"SQLite format 3\x00"):
            raise ValueError("El respaldo no es una base SQLite.")
        fd, tmp = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            Path(tmp).write_bytes(content)
            src = sqlite3.connect(tmp)
            if src.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                src.close()
                raise ValueError("El respaldo está dañado.")
            dst = sqlite3.connect(self.path, timeout=30)
            with dst:
                src.backup(dst)
            src.close()
            dst.close()
        finally:
            Path(tmp).unlink(missing_ok=True)
        with self.connect() as conn:  # crea tablas nuevas si el respaldo es de una versión anterior
            conn.executescript(USER_SCHEMA)

    def is_empty(self) -> bool:
        return self.one("SELECT COUNT(*) AS n FROM subscribers")["n"] == 0

    # --- caché clave/valor con expiración (respuestas de proveedores externos) ---
    def cache_get(self, key: str) -> Any | None:
        row = self.one("SELECT payload, expires_at FROM cache WHERE key = ?", (key,))
        if not row or row["expires_at"] < time.time():
            return None
        return json.loads(row["payload"])

    def cache_set(self, key: str, value: Any, ttl_seconds: float) -> None:
        self.execute(
            "INSERT INTO cache(key, expires_at, payload) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET expires_at = excluded.expires_at, payload = excluded.payload",
            (key, time.time() + ttl_seconds, json.dumps(value, ensure_ascii=False)),
        )

    def cache_purge(self) -> None:
        self.execute("DELETE FROM cache WHERE expires_at < ?", (time.time(),))

    def kv_get(self, key: str) -> str | None:
        row = self.one("SELECT value FROM kv WHERE key = ?", (key,))
        return row["value"] if row else None

    def kv_set(self, key: str, value: str) -> None:
        self.execute("INSERT INTO kv(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))

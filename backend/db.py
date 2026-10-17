"""Persistencia local en SQLite.

El esquema replica las entidades del diseño PostGIS de docs/ARQUITECTURA.md (observaciones,
procedencia, lugares, alertas, riesgo y reportes) para que la migración sea directa.
"""
from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

SCHEMA = """
PRAGMA journal_mode = WAL;
CREATE TABLE IF NOT EXISTS ingest_runs (
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
CREATE INDEX IF NOT EXISTS ingest_runs_product ON ingest_runs(product, started_at DESC);

CREATE TABLE IF NOT EXISTS observations (
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
  run_id INTEGER REFERENCES ingest_runs(id),
  ingested_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS observations_time ON observations(observed_at DESC);
CREATE INDEX IF NOT EXISTS observations_comuna ON observations(comuna_code, observed_at DESC);

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

CREATE TABLE IF NOT EXISTS risk_daily (
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

CREATE TABLE IF NOT EXISTS risk_hourly (
  comuna_code INTEGER PRIMARY KEY,
  computed_at TEXT NOT NULL,
  payload TEXT NOT NULL
);

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

CREATE TABLE IF NOT EXISTS cache (
  key TEXT PRIMARY KEY,
  expires_at REAL NOT NULL,
  payload TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS kv (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
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
            return conn.execute(sql, params).rowcount

    def insert(self, sql: str, params: tuple | dict = ()) -> int:
        """Inserta y devuelve el id de la fila nueva (0 si INSERT OR IGNORE no insertó nada)."""
        with self.connect() as conn:
            cursor = conn.execute(sql, params)
            return cursor.lastrowid if cursor.rowcount else 0

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

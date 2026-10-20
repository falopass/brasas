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
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

WORK_TABLES = (
    "ingest_runs",
    "observations",
    "risk_daily",
    "risk_hourly",
    "cache",
    "incidents",
    "incident_observations",
    "incident_merges",
    "boton_rojo",
    "official_fires",
    "fwi_daily",
    "dmc_alerts",
    "rain_normal",
    "rain_season",
)
_USER_WRITE = re.compile(
    r"^\s*(insert|update|delete|replace)\b.*?\b(subscribers|places|alerts|reports|kv|moderators|moderation_log)\b", re.I | re.S
)

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
  ingested_at TEXT NOT NULL,
  alerts_evaluated_at TEXT        -- cuándo se miró si generaba aviso (NULL = pendiente)
);
CREATE INDEX IF NOT EXISTS work.observations_time ON observations(observed_at DESC);
CREATE INDEX IF NOT EXISTS work.observations_comuna ON observations(comuna_code, observed_at DESC);

-- Incidentes: evidencia agrupada en el espacio y el tiempo (un punto de calor no es un incendio).
CREATE TABLE IF NOT EXISTS work.incidents (
  id TEXT PRIMARY KEY,
  status TEXT NOT NULL,              -- anomalia | posible | reportado | confirmado | controlado | extinguido | descartado
  status_changed_at TEXT NOT NULL,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  lat REAL NOT NULL,
  lon REAL NOT NULL,
  min_lat REAL NOT NULL, max_lat REAL NOT NULL, min_lon REAL NOT NULL, max_lon REAL NOT NULL,
  n_obs INTEGER NOT NULL DEFAULT 0,
  n_reliable INTEGER NOT NULL DEFAULT 0,
  sensors TEXT NOT NULL DEFAULT '',
  max_frp REAL,
  comuna_code INTEGER,
  fixed_source INTEGER NOT NULL DEFAULT 0, -- toda la evidencia cae en una fuente de calor fija probable
  fixed_reason TEXT,                     -- por qué se marcó así, en palabras (FIX-03)
  official_ref TEXT,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS work.incidents_active ON incidents(status, last_seen_at DESC);
CREATE TABLE IF NOT EXISTS work.incident_observations (
  observation_id TEXT PRIMARY KEY,
  incident_id TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS work.incident_obs_incident ON incident_observations(incident_id);

-- Alias de fusiones: cuando dos incidentes se unen, el id borrado queda apuntando al vigente para
-- que los enlaces guardados en los avisos sigan abriendo la ficha.
CREATE TABLE IF NOT EXISTS work.incident_merges (
  dead_id TEXT PRIMARY KEY,
  live_id TEXT NOT NULL,
  merged_at TEXT NOT NULL
);

-- CONAF Botón Rojo (pronóstico oficial a 5 días): horas en condición Botón Rojo por comuna y día.
CREATE TABLE IF NOT EXISTS work.boton_rojo (
  comuna_code INTEGER NOT NULL,
  date TEXT NOT NULL,
  hours INTEGER NOT NULL,
  area_ha REAL NOT NULL,
  proportion REAL NOT NULL,
  fetched_at TEXT NOT NULL,
  PRIMARY KEY (comuna_code, date)
);

-- Incendios informados por CONAF (reporte público de GEPRIF): la única base de «confirmado».
CREATE TABLE IF NOT EXISTS work.official_fires (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  status TEXT NOT NULL,              -- confirmado | controlado | extinguido (traducido desde status_raw)
  status_raw TEXT NOT NULL,          -- tal como lo publica CONAF: En combate, Controlado, Extinguido, Bajo observacion…
  started_at TEXT NOT NULL,
  controlled_at TEXT,
  extinguished_at TEXT,
  area_ha REAL,
  lat REAL NOT NULL,
  lon REAL NOT NULL,
  comuna TEXT,
  region TEXT,
  ambito TEXT,
  fuel TEXT,
  detected_at TEXT,                  -- f_deteccion de CONAF: permite medir cuánto antes detecta BRASA (FIX-14)
  alerted_at TEXT,                   -- f_aviso
  dispatched_at TEXT,                -- f_despacho
  season TEXT,                       -- temporada, por ejemplo «2025-2026»
  first_fetched_at TEXT NOT NULL,
  fetched_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS work.official_fires_time ON official_fires(started_at DESC);

CREATE TABLE IF NOT EXISTS work.risk_daily (
  comuna_code INTEGER NOT NULL,
  date TEXT NOT NULL,
  level TEXT NOT NULL,            -- regla 30-30-30 sola
  score INTEGER NOT NULL,
  hours_3of3 INTEGER NOT NULL,
  hours_2of3 INTEGER NOT NULL,
  tmax REAL, rhmin REAL, windmax REAL, gustmax REAL,
  level_combined TEXT,            -- 30-30-30 + FWI (backend/risk.py: combine)
  fwi REAL, fwi_level TEXT,
  reasons TEXT,                   -- JSON: por qué ese nivel, en palabras
  computed_at TEXT NOT NULL,
  PRIMARY KEY (comuna_code, date)
);

CREATE TABLE IF NOT EXISTS work.risk_hourly (
  comuna_code INTEGER PRIMARY KEY,
  computed_at TEXT NOT NULL,
  payload TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS work.fwi_daily (
  comuna_code INTEGER NOT NULL,
  date TEXT NOT NULL,
  ffmc REAL NOT NULL, dmc REAL NOT NULL, dc REAL NOT NULL,
  isi REAL NOT NULL, bui REAL NOT NULL, fwi REAL NOT NULL,
  level TEXT NOT NULL,
  computed_at TEXT NOT NULL,
  PRIMARY KEY (comuna_code, date)
);
CREATE INDEX IF NOT EXISTS work.fwi_daily_date ON fwi_daily(date);

CREATE TABLE IF NOT EXISTS work.dmc_alerts (
  id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  event TEXT NOT NULL,
  headline TEXT NOT NULL,
  severity TEXT, urgency TEXT,
  onset TEXT, expires TEXT,
  web TEXT,
  areas TEXT NOT NULL,      -- JSON: [{desc, comunas:[códigos]}]
  comunas TEXT NOT NULL,    -- JSON: [códigos] que toca el aviso
  fetched_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS work.dmc_alerts_expires ON dmc_alerts(expires);

CREATE TABLE IF NOT EXISTS work.rain_normal (
  comuna_code INTEGER PRIMARY KEY,
  days INTEGER NOT NULL,          -- días del año que cubre la normal (junio a octubre)
  daily_normals TEXT NOT NULL,    -- JSON: {"MM-DD": mm} promedio diario 1991-2020
  computed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS work.rain_season (
  comuna_code INTEGER NOT NULL,
  year INTEGER NOT NULL,        -- año de la temporada (la que empieza en junio)
  current_mm REAL, normal_mm REAL, ratio REAL,
  level TEXT, computed_at TEXT NOT NULL,
  PRIMARY KEY (comuna_code, year)
);

CREATE TABLE IF NOT EXISTS work.risk_snapshot (
  snapshot_date TEXT NOT NULL,   -- día en que se emitió este pronóstico
  comuna_code INTEGER NOT NULL,
  target_date TEXT NOT NULL,     -- día pronosticado
  level TEXT NOT NULL,           -- regla 30-30-30 sola
  level_combined TEXT,           -- 30-30-30 + FWI
  score INTEGER NOT NULL,
  PRIMARY KEY (snapshot_date, comuna_code, target_date)
);
CREATE INDEX IF NOT EXISTS work.risk_snapshot_comuna ON risk_snapshot(comuna_code, snapshot_date DESC);

CREATE TABLE IF NOT EXISTS work.cache (
  key TEXT PRIMARY KEY,
  expires_at REAL NOT NULL,  payload TEXT NOT NULL
);

-- Corroboraciones: un segundo aviso del mismo hecho no abre otra fila en la cola, pero deja
-- constancia de que otro vecino lo vio. El dispositivo se guarda solo para no contarlo dos
-- veces; nunca se expone, solo el total. Vive en work.db: sin el reporte original no dice nada.
CREATE TABLE IF NOT EXISTS work.report_corroborations (
  report_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  subscriber_id TEXT
);
CREATE INDEX IF NOT EXISTS work.report_corroborations_report ON report_corroborations(report_id);
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
  created_at TEXT NOT NULL,
  older_adult INTEGER NOT NULL DEFAULT 0,  -- vive una persona mayor o alguien que necesita ayuda para salir
  share_token TEXT,                         -- enlace de solo lectura para la familia (modo vecino)
  daily_brief INTEGER NOT NULL DEFAULT 0    -- quiere el aviso preventivo de la mañana (ALR-04)
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
  delivered_at TEXT,                 -- cuándo se intentó entregar (NULL = pendiente de reintento)
  reminded_at TEXT,                  -- cuándo se reenvió el urgente (NULL = aún no; una sola vez, ALR-10)
  feedback TEXT,                     -- opinión de la persona sobre el aviso: sirvio | no_sirvio | quema
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
  moderator_note TEXT,
  subscriber_id TEXT            -- dispositivo que lo envió (opcional): permite contarle qué pasó
);
CREATE INDEX IF NOT EXISTS reports_status ON reports(status, created_at DESC);
-- El índice de autor se crea en _migrate_user, después de asegurar la columna: en una base ya
-- desplegada `CREATE TABLE IF NOT EXISTS` no agrega `subscriber_id`, y crearlo aquí rompía el
-- arranque con «no such column».

CREATE TABLE IF NOT EXISTS kv (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

-- Moderadores voluntarios (SEC-10): cada uno con su token; en la base solo vive el SHA-256.
CREATE TABLE IF NOT EXISTS moderators (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  token_hash TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL,
  revoked_at TEXT            -- NULL = vigente; revocar no borra: el registro conserva el nombre
);

-- Quién decidió qué y cuándo sobre cada reporte (SEC-10). moderator_id NULL = el ADMIN_TOKEN.
CREATE TABLE IF NOT EXISTS moderation_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  moderator_id TEXT REFERENCES moderators(id),
  action TEXT NOT NULL,      -- estado que dejó la decisión: verificado | descartado | no_verificado
  report_id TEXT NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS moderation_log_time ON moderation_log(created_at DESC);
"""


# Columnas agregadas después de la primera versión: (tabla, columna, definición).
USER_COLUMNS = [
    ("places", "older_adult", "INTEGER NOT NULL DEFAULT 0"),
    ("places", "share_token", "TEXT"),
    ("places", "daily_brief", "INTEGER NOT NULL DEFAULT 0"),
    ("reports", "subscriber_id", "TEXT"),
    ("alerts", "delivered_at", "TEXT"),
    ("alerts", "reminded_at", "TEXT"),
    ("alerts", "feedback", "TEXT"),
]


def _migrate_user(conn: sqlite3.Connection) -> None:
    """Agrega columnas nuevas y después los índices que dependen de ellas.

    El orden importa: en una base ya desplegada la tabla `reports` no tiene `subscriber_id`, así que
    un índice sobre esa columna creado antes de la migración falla con «no such column» y deja el
    arranque (o la restauración de un respaldo) sin poder abrir la base.
    """
    for table, column, definition in USER_COLUMNS:
        existing = {row[1] for row in conn.execute(f"PRAGMA main.table_info({table})")}
        if column not in existing:
            conn.execute(f"ALTER TABLE main.{table} ADD COLUMN {column} {definition}")
            if (table, column) == ("alerts", "delivered_at"):
                # Las alertas ya escritas pasaron por su intento de entrega: la marca se usa
                # para reintentar solo las que quedaron a medio entregar.
                conn.execute("UPDATE main.alerts SET delivered_at = created_at")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS main.places_share ON places(share_token)")
    conn.execute("CREATE INDEX IF NOT EXISTS main.reports_author ON reports(subscriber_id, created_at DESC)")


# Columnas agregadas al esquema de trabajo después de la primera versión: (tabla, columna, definición).
# `work.db` se puede reconstruir, pero migrar en el sitio evita perder el historial de riesgo y FWI.
WORK_COLUMNS = [
    ("risk_daily", "level_combined", "TEXT"),
    ("risk_daily", "fwi", "REAL"),
    ("risk_daily", "fwi_level", "TEXT"),
    ("risk_daily", "reasons", "TEXT"),
    ("official_fires", "detected_at", "TEXT"),
    ("official_fires", "alerted_at", "TEXT"),
    ("official_fires", "dispatched_at", "TEXT"),
    ("official_fires", "season", "TEXT"),
    ("observations", "alerts_evaluated_at", "TEXT"),
    ("incidents", "fixed_reason", "TEXT"),
]


def _migrate_work(conn: sqlite3.Connection) -> None:
    for table, column, definition in WORK_COLUMNS:
        existing = {row[1] for row in conn.execute(f"PRAGMA work.table_info({table})")}
        if column not in existing:
            conn.execute(f"ALTER TABLE work.{table} ADD COLUMN {column} {definition}")


def _snapshot_file(path: Path) -> bytes:
    fd, tmp = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        src = sqlite3.connect(path, timeout=30)
        dst = sqlite3.connect(tmp)
        with dst:
            src.backup(dst)
        src.close()
        dst.execute("PRAGMA journal_mode = DELETE")
        dst.close()
        return Path(tmp).read_bytes()
    finally:
        Path(tmp).unlink(missing_ok=True)


class Database:
    def __init__(self, path: Path, work_path: Path | None = None):
        self.path = path
        self.work_path = work_path or path.with_name("work.db")
        self.on_user_write = None  # callback: se llama tras escribir datos de las personas
        self._local = threading.local()  # una conexión por hilo: sqlite3 prohíbe compartirlas entre hilos
        self._gen = 0  # lo sube close_all: cada hilo renueva su conexión marcada
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
            _migrate_user(conn)
            _migrate_work(conn)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = getattr(self._local, "conn", None)
        if conn is not None and self._local.gen != self._gen:  # close_all la marcó en otro hilo
            conn.close()
            conn = None
        if conn is None:
            conn = sqlite3.connect(self.path, timeout=30)
            conn.row_factory = sqlite3.Row
            conn.execute("ATTACH DATABASE ? AS work", (str(self.work_path),))
            conn.execute("PRAGMA foreign_keys = ON")
            self._local.conn = conn
        self._local.gen = self._gen
        try:
            yield conn
            conn.commit()
        except BaseException:
            # Antes lo hacía conn.close() al salir; sin el rollback la transacción abierta
            # retendría el candado de escritor hasta la próxima consulta del hilo.
            conn.rollback()
            raise

    def close_all(self) -> None:
        """Cierra las conexiones abiertas por esta base.

        sqlite3 solo permite cerrar cada conexión desde el hilo que la creó, así que la del hilo
        actual se cierra aquí y las demás quedan marcadas: cada hilo cierra la suya al entrar a
        su próxima consulta (y las de hilos ya terminados se cerraron solas al salir). La base
        sigue utilizable: quien consulte después obtiene una conexión nueva.
        """
        self._gen += 1
        conn = getattr(self._local, "conn", None)
        self._local.conn = None
        if conn is not None:
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
        return _snapshot_file(self.path)

    def snapshot_work(self) -> bytes:
        """Copia consistente de work.db (observaciones e incidentes), para no perderlos al reiniciar."""
        return _snapshot_file(self.work_path)

    def restore_work(self, content: bytes) -> None:
        if not content.startswith(b"SQLite format 3\x00"):
            raise ValueError("El respaldo de trabajo no es una base SQLite.")
        fd, tmp = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            Path(tmp).write_bytes(content)
            src = sqlite3.connect(tmp)
            if src.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                src.close()
                raise ValueError("El respaldo de trabajo está dañado.")
            dst = sqlite3.connect(self.work_path, timeout=30)
            with dst:
                src.backup(dst)
            src.close()
            dst.close()
        finally:
            Path(tmp).unlink(missing_ok=True)
        # El respaldo puede ser de una versión anterior: executescript crea las tablas que falten
        # (CREATE TABLE IF NOT EXISTS no toca las existentes), y la migración agrega las columnas
        # nuevas. Sin esto, las consultas que leen esas columnas fallan hasta que se regenere todo.
        with self.connect() as conn:
            conn.executescript(WORK_SCHEMA)
            _migrate_work(conn)

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
        with self.connect() as conn:  # crea tablas y columnas nuevas si el respaldo es de una versión anterior
            conn.executescript(USER_SCHEMA)
            _migrate_user(conn)

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

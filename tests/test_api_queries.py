"""QA-40 — guarda del número de consultas por request en las rutas calientes (sin N+1).

Es la contraparte determinista de `test_incidents_perf.py` (FIX-15): allí se miden
segundos, que dependen de la máquina; aquí se fija el número de lecturas a la base,
que no cambia con la carga ni con el hardware.

Cómo cuenta: `db_reads` envuelve `Database.connect` y cuenta cada `execute`/`executemany`/
`executescript` de lectura (SELECT/WITH/PRAGMA/EXPLAIN/VALUES) que corre dentro de un
`with db.connect()`. Como `query`, `one`, `kv_get` y `cache_get` pasan por `connect`, y
las funciones del backend que leen directo de la conexión también, el contador ve todas
las lecturas del request sin depender del SQL concreto de cada ruta.

La guarda se verificó puesta en rojo a mano: agregando en `observations`
(`backend/routes/public.py`) una consulta por fila del estilo
`svc.db.one("SELECT 1 FROM incidents WHERE id = ?", (row["incident_id"],))` dentro del
`for row in rows`, `test_observations_query_count_does_not_grow_with_data` falló
(102 lecturas con ~100 detecciones contra 5 002 con ~5 000). El cambio se revirtió antes
de entregar.
"""

from __future__ import annotations

import random
import re
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import pytest

from backend.db import Database

_READ = re.compile(r"^\s*(select|with|pragma|explain|values)\b", re.I)


@pytest.fixture
def db_reads(monkeypatch):
    """Cuenta las lecturas SQL que hace cualquier `Database` durante la prueba."""
    counter = {"n": 0}
    real_connect = Database.connect

    class CountedConn:
        def __init__(self, conn):
            self._conn = conn

        def __getattr__(self, name):
            return getattr(self._conn, name)

        def execute(self, sql, *args, **kwargs):
            if _READ.match(sql):
                counter["n"] += 1
            return self._conn.execute(sql, *args, **kwargs)

        def executemany(self, sql, *args, **kwargs):
            if _READ.match(sql):
                counter["n"] += 1
            return self._conn.executemany(sql, *args, **kwargs)

        def executescript(self, sql, *args, **kwargs):
            if _READ.match(sql):
                counter["n"] += 1
            return self._conn.executescript(sql, *args, **kwargs)

    @contextmanager
    def counting_connect(self):
        with real_connect(self) as conn:
            yield CountedConn(conn)

    monkeypatch.setattr(Database, "connect", counting_connect)
    return counter


def seed_detections(db: Database, start: int, n: int, n_incidents: int = 5) -> None:
    """Inserta `n` detecciones recientes (ids desde `start`) repartidas en `n_incidents`
    incidentes creados si aún no existen. Inserts directos: la agrupación real ya la
    cubre `test_incidents_props.py`; aquí solo importa el volumen leído por request."""
    rng = random.Random(40040)
    now = datetime.now(timezone.utc)
    with db.connect() as conn:
        for i in range(n_incidents):
            iid = f"seedinc{i:06d}"
            at = (now - timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
            conn.execute(
                "INSERT OR IGNORE INTO incidents(id, status, status_changed_at, first_seen_at, last_seen_at, "
                "lat, lon, min_lat, max_lat, min_lon, max_lon, n_obs, n_reliable, sensors, max_frp, comuna_code, "
                "fixed_source, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,?)",
                (iid, "posible", at, at, at, -33.5, -70.8, -33.6, -33.4, -70.9, -70.7, 0, 0, "VIIRS", 10.0, 13101, at),
            )
        for i in range(start, start + n):
            at = (now - timedelta(minutes=rng.randrange(1, 47 * 60))).strftime("%Y-%m-%dT%H:%M:%SZ")
            oid = f"seedobs{i:07d}"
            conn.execute(
                "INSERT INTO observations(id, source, sensor, satellite, resolution_m, lat, lon, observed_at, "
                "frp_mw, confidence, comuna_code, run_id, ingested_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL,?)",
                (oid, "gen", "VIIRS", "GEN", 375, -33.5 + rng.gauss(0, 0.01), -70.8 + rng.gauss(0, 0.01), at, 10.0, "nominal", 13101, at),
            )
            conn.execute(
                "INSERT INTO incident_observations(observation_id, incident_id) VALUES (?, ?)", (oid, f"seedinc{i % n_incidents:06d}")
            )


def read_count(db_reads, client, path: str) -> int:
    db_reads["n"] = 0
    r = client.get(path)
    assert r.status_code == 200, r.text
    return db_reads["n"]


def test_observations_query_count_does_not_grow_with_data(make_client, db_reads):
    """`/api/observations?hours=48` hace un número fijo de lecturas por request
    (medido: 2 — la consulta de puntos con su join y el `kv_get` de `data_as_of`),
    con ~100 o con ~5 000 detecciones."""
    with make_client() as client:
        db = client.app.state.services.db
        seed_detections(db, 0, 100)
        small = read_count(db_reads, client, "/api/observations?hours=48")
        seed_detections(db, 100, 4900)
        big = read_count(db_reads, client, "/api/observations?hours=48")
        assert small == big


def test_incidents_query_count_does_not_grow_with_data(make_client, db_reads):
    """`/api/incidents?hours=48`: mismo criterio, 5 000 detecciones en pocos incidentes.
    Medido: 2 lecturas (la lista de incidentes y el `kv_get` de `data_as_of`)."""
    with make_client() as client:
        db = client.app.state.services.db
        seed_detections(db, 0, 100)
        small = read_count(db_reads, client, "/api/incidents?hours=48")
        seed_detections(db, 100, 4900)
        big = read_count(db_reads, client, "/api/incidents?hours=48")
        assert small == big


def test_status_and_risk_comuna_stay_bounded(make_client, db_reads):
    """Estas rutas leen varias tablas por request, pero un número fijo:
    - `/api/status` medido: 14 lecturas (estado de fuentes, últimas ejecuciones, barridos
      GOES, resumen de errores, fallos de 24 h, incidentes abiertos, detecciones más
      nuevas por fuente y los `kv_get` de marcas de tiempo).
    - `/api/risk/{code}` medido: 12 lecturas (días, horas, botón rojo, FWI, lluvia, DMC y
      marcas). Los límites dejan holgura para unas lecturas auxiliares futuras, no para un N+1.
    """
    with make_client() as client:
        db = client.app.state.services.db
        seed_detections(db, 0, 100)
        assert read_count(db_reads, client, "/api/status") <= 19
        assert read_count(db_reads, client, "/api/risk/5109") <= 16

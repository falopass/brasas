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
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import pytest

from backend.db import Database

_READ = re.compile(r"^\s*(select|with|pragma|explain|values)\b", re.I)


def _normalize_sql(sql: str) -> str:
    """La sentencia en una línea: mismo SQL con distinto sangrado cuenta como una."""
    return " ".join(sql.split())


@pytest.fixture
def db_reads(monkeypatch):
    """Cuenta las lecturas SQL que hace cualquier `Database` durante la prueba.

    `counter["n"]` es el total y `counter["by_sql"]` el desglose por sentencia
    normalizada, para que un presupuesto fallido diga qué consulta se repitió.
    """
    counter = {"n": 0, "by_sql": Counter()}
    real_connect = Database.connect

    def count(sql):
        if _READ.match(sql):
            counter["n"] += 1
            counter["by_sql"][_normalize_sql(sql)] += 1

    class CountedConn:
        def __init__(self, conn):
            self._conn = conn

        def __getattr__(self, name):
            return getattr(self._conn, name)

        def execute(self, sql, *args, **kwargs):
            count(sql)
            return self._conn.execute(sql, *args, **kwargs)

        def executemany(self, sql, *args, **kwargs):
            count(sql)
            return self._conn.executemany(sql, *args, **kwargs)

        def executescript(self, sql, *args, **kwargs):
            count(sql)
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
    db_reads["by_sql"].clear()
    r = client.get(path)
    assert r.status_code == 200, r.text
    return db_reads["n"]


def reads_breakdown(db_reads) -> list[tuple[str, int]]:
    """Desglose de lecturas por sentencia normalizada: `(sentencia, veces)`
    ordenado de mayor a menor."""
    return db_reads["by_sql"].most_common()


def reads_diagnosis(db_reads, path: str, limit: int) -> str:
    """Mensaje de un presupuesto de lecturas pasado: la sentencia más repetida
    primero, con su conteo, para no tener que partir el tren de merges para
    encontrar al culpable."""
    top = "; ".join(f"{n}× {sql}" for sql, n in reads_breakdown(db_reads)[:5])
    return f"{path}: {db_reads['n']} lecturas (techo {limit}); por sentencia: {top}"


@pytest.mark.parametrize("path", ["/api/observations?hours=48", "/api/incidents?hours=48"])
def test_query_count_does_not_grow_with_data(make_client, db_reads, path):
    """`/api/observations` y `/api/incidents` hacen un número fijo de lecturas por request
    (medido: 2 — la consulta de la ruta y el `kv_get` de `data_as_of`), con ~100 o con
    ~5 000 detecciones."""
    with make_client() as client:
        db = client.app.state.services.db
        seed_detections(db, 0, 100)
        small = read_count(db_reads, client, path)
        seed_detections(db, 100, 4900)
        assert read_count(db_reads, client, path) == small


def test_status_and_risk_reads_stay_fixed_and_bounded(make_client, db_reads):
    """`/api/status` y `/api/risk/{code}` leen un número fijo por request y bajo un techo.

    Medido: 19 lecturas en /api/status (estado de fuentes, últimas ejecuciones, barridos
    GOES, resumen de errores, fallos de 24 h, incidentes abiertos, detecciones más nuevas
    por fuente, los `kv_get` de marcas de tiempo y la cobertura de OPS-19) y 12 en
    /api/risk/{code} (días, horas, botón rojo, FWI, lluvia, DMC y marcas). Los techos
    (22 y 18) llevan margen a propósito: el tren de merges integra varios PRs antes de
    correr `dev.py check`, y un tope sin holgura bloquea la cola completa cuando una ruta
    suma una lectura legítima. La garantía fuerte es la invariancia con el volumen; si hay
    que apretar, se aprieta la ruta, no el test.
    """
    techos = {"/api/status": 22, "/api/risk/5109": 18}
    with make_client() as client:
        db = client.app.state.services.db
        seed_detections(db, 0, 100)
        small = {}
        for path, techo in techos.items():
            small[path] = read_count(db_reads, client, path)
            assert small[path] <= techo, reads_diagnosis(db_reads, path, techo)
        seed_detections(db, 100, 4900)
        for path, techo in techos.items():
            assert read_count(db_reads, client, path) == small[path], reads_diagnosis(db_reads, path, techo)


def test_reads_diagnosis_names_the_repeated_query():
    """QA-124: cuando el presupuesto se pasa, el fallo nombra la sentencia que se
    repitió y cuántas veces — no hace falta dividir el tren para encontrarla."""
    sql = "SELECT * FROM observations WHERE comuna_code = ?"
    db_reads = {"n": 20, "by_sql": Counter({sql: 20})}
    assert reads_breakdown(db_reads) == [(sql, 20)]
    with pytest.raises(AssertionError) as excinfo:
        assert db_reads["n"] <= 19, reads_diagnosis(db_reads, "/api/status", 19)
    texto = str(excinfo.value)
    assert sql in texto and "20×" in texto

"""OPS-813: poda de `ingest_runs` y consultas del estado sin recorrido completo de la tabla."""

import re
from datetime import timedelta
from types import SimpleNamespace

import pytest

from backend.db import Database
from backend.services import INGEST_RUNS_RETENTION_DAYS, prune_ingest_runs, stamp, utcnow
from backend.status import build


@pytest.fixture
def db(tmp_path) -> Database:
    return Database(tmp_path / "brasa.db")


def seed_run(db: Database, product: str, days_ago: float, ok: bool) -> None:
    marca = stamp(utcnow() - timedelta(days=days_ago))
    db.execute(
        "INSERT INTO ingest_runs(provider, product, started_at, finished_at, ok, n_records, n_new, message) "
        "VALUES (?,?,?,?,?,?,?,?)",
        ("prueba", product, marca, marca, int(ok), 0, 0, ""),
    )


def test_poda_borra_lo_viejo_y_conserva_lo_que_el_estado_necesita(db):
    """La ventana se va, pero nunca la última corrida ni la última buena de cada producto:
    `runs[]` y `last_ok_at` no pueden quedar vacíos aunque una fuente deje de correr."""
    # VIEJO: tres corridas fuera de la ventana; deben quedar la última (8 días, fallida)
    # y la última buena (9 días); la de 12 días se borra.
    seed_run(db, "VIEJO", 12, False)
    seed_run(db, "VIEJO", 9, True)
    seed_run(db, "VIEJO", 8, False)
    # FRESCO: una buena vieja borrable (no es ni la última ni la última buena del producto)
    # y tres recientes intocables.
    seed_run(db, "FRESCO", INGEST_RUNS_RETENTION_DAYS + 3, True)
    seed_run(db, "FRESCO", 2, True)
    seed_run(db, "FRESCO", 1, True)
    seed_run(db, "FRESCO", 0, True)

    borradas = prune_ingest_runs(db)
    assert borradas == 2

    restantes = {
        p: sorted(
            r["edad_dias"]
            for r in db.query(
                "SELECT CAST(julianday('now') - julianday(started_at) AS INTEGER) AS edad_dias "
                "FROM ingest_runs WHERE product = ?",
                (p,),
            )
        )
        for p in ("VIEJO", "FRESCO")
    }
    assert restantes["VIEJO"] == [8, 9]         # última y última buena, aunque ya vencieron
    assert restantes["FRESCO"] == [0, 1, 2]     # lo reciente no se toca

    # La última corrida global sigue en la tabla: el estado la muestra en `runs[]`.
    assert db.one("SELECT COUNT(*) AS n FROM ingest_runs")["n"] == 5


class RegistraSQL:
    """Base envolvente: delega en la real y anota cada consulta para revisar su plan."""

    def __init__(self, db: Database):
        self.db = db
        self.consultas: list[tuple[str, tuple]] = []

    def query(self, sql, params=()):
        self.consultas.append((sql, params))
        return self.db.query(sql, params)

    def one(self, sql, params=()):
        self.consultas.append((sql, params))
        return self.db.one(sql, params)

    def kv_get(self, key):
        return self.db.kv_get(key)

    def kv_many(self, keys):
        return self.db.kv_many(keys)


def _aliases_ingest_runs(sql: str) -> set[str]:
    """Nombre y alias con que la consulta nombra a `ingest_runs` (FROM/JOIN ingest_runs [AS] x)."""
    nombres = {"ingest_runs"}
    for match in re.finditer(r"(?:FROM|JOIN)\s+ingest_runs(?:\s+(?:AS\s+)?(\w+))?", sql, re.IGNORECASE):
        if match.group(1):
            nombres.add(match.group(1))
    return nombres


def test_estado_no_recorre_toda_la_tabla_ingest_runs(db):
    """~20.000 corridas: ninguna lectura del armado de /api/status hace `SCAN ingest_runs`.

    `SCAN ingest_runs USING COVERING INDEX` sí pasa: lee solo el índice (nunca la tabla) y
    la poda acota su tamaño a `INGEST_RUNS_RETENTION_DAYS` días. Lo que queda prohibido es el
    `SCAN` sin `USING`, que lee la tabla completa y crecía sin freno (OPS-813).
    """
    inicio = utcnow() - timedelta(hours=48)
    with db.connect() as conn:
        conn.executemany(
            "INSERT INTO ingest_runs(provider, product, started_at, finished_at, ok, n_records, n_new, message, source_ref) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            [
                (
                    "NOAA GOES" if i % 7 == 0 else "prueba",
                    f"PROD-{i % 7}",
                    (marca := stamp(inicio + timedelta(seconds=8 * i))),
                    marca,
                    1 if i % 11 else 0,
                    0, 0, "detalle", f"ref/{i}",
                )
                for i in range(20_000)
            ],
        )
    # Un producto cuyas corridas recientes son todas fallidas: ejercita la consulta de
    # respaldo que busca la última buena más allá de la ventana de `productos()`.
    for i in range(8):
        seed_run(db, "TODAS_MALAS", i / 24.0, False)
    assert db.one("SELECT COUNT(*) AS n FROM ingest_runs")["n"] == 20_008

    registrada = RegistraSQL(db)
    svc = SimpleNamespace(
        db=registrada,
        last_cycle=None,
        persistence=SimpleNamespace(enabled=False),
        settings=SimpleNamespace(scheduler_enabled=False, internal_token=None, firms_map_key=None),
        open_meteo_day=lambda: 0,
        process_started_at=stamp(),
        startup_ms=1,
    )
    build(svc, history=3, coverage=False)
    assert registrada.consultas, "el armado debió consultar la base"

    with db.connect() as conn:
        for sql, params in registrada.consultas:
            nombres = _aliases_ingest_runs(sql)
            for _id, _parent, _notused, detail in conn.execute("EXPLAIN QUERY PLAN " + sql, params):
                escanea = re.match(r"SCAN (\w+)", detail)
                assert not (escanea and escanea.group(1) in nombres and "USING" not in detail), (
                    f"recorrido completo de ingest_runs: {detail}\n{sql}"
                )

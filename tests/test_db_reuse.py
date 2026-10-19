"""FIX-16: `Database` reutiliza una conexión SQLite por hilo, con el ATTACH hecho una vez.

Lo que no puede cambiar: el commit al salir de cada `with`, el aviso `on_user_write` solo en
tablas de las personas, y que varios hilos puedan consultar y escribir a la vez sin
«database is locked».
"""
from __future__ import annotations

import threading

from backend.db import Database


def test_query_sees_what_execute_and_insert_wrote(tmp_path):
    db = Database(tmp_path / "brasa.db")
    db.execute("INSERT INTO kv(key, value) VALUES ('saludo', 'hola')")
    assert db.one("SELECT value FROM kv WHERE key = 'saludo'") == {"value": "hola"}
    row_id = db.insert("INSERT INTO subscribers(id, created_at) VALUES ('s1', '2027-01-01T00:00:00Z')")
    assert row_id > 0
    assert db.one("SELECT id FROM subscribers WHERE id = 's1'") == {"id": "s1"}


def test_work_tables_answer_through_the_attach(tmp_path):
    db = Database(tmp_path / "brasa.db")
    assert db.one("PRAGMA work.journal_mode")["journal_mode"] == "wal"
    run = db.insert("INSERT INTO work.ingest_runs(provider, product, started_at) VALUES (?,?,?)",
                    ("prueba", "demo", "2027-01-01T00:00:00Z"))
    assert db.one("SELECT provider FROM work.ingest_runs WHERE id = ?", (run,))["provider"] == "prueba"


def test_threads_query_and_write_without_database_locked(tmp_path):
    db = Database(tmp_path / "brasa.db")
    errors = []

    def worker(tag):
        try:
            for i in range(50):
                db.query("SELECT 1")
                db.execute("INSERT INTO work.cache(key, expires_at, payload) VALUES (?,?,?) "
                           "ON CONFLICT(key) DO UPDATE SET payload = excluded.payload",
                           (f"{tag}-{i % 5}", 9e9, "{}"))
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors, errors
    assert db.one("SELECT COUNT(*) AS n FROM work.cache")["n"] == 4 * 5
    db.close_all()  # cierra la conexión de este hilo; las de los hilos terminados ya se cerraron solas
    assert db.query("SELECT 1")


def test_on_user_write_only_fires_for_people_tables(tmp_path):
    db = Database(tmp_path / "brasa.db")
    calls = []
    db.on_user_write = lambda: calls.append(1)
    db.execute("INSERT INTO subscribers(id, created_at) VALUES ('s1', '2027-01-01T00:00:00Z')")
    db.execute("INSERT INTO places(id, subscriber_id, name, lat, lon, created_at) "
               "VALUES ('p1', 's1', 'casa', -36.8, -73.0, '2027-01-01')")
    db.execute("INSERT INTO alerts(place_id, observation_id, level, distance_km, bearing_deg, lat, lon, observed_at, "
               "created_at, payload) VALUES ('p1', 'o1', 'aviso', 1.0, 0, -36.8, -73.0, '2027-01-01', '2027-01-01', '{}')")
    db.execute("INSERT INTO work.ingest_runs(provider, product, started_at) VALUES ('a', 'b', '2027-01-01')")
    db.execute("UPDATE work.cache SET payload = '{}' WHERE key = 'nada'")
    assert len(calls) == 3

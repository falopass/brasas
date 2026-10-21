"""OPS-14: /api/status publica un resumen de errores de la ingesta, sin datos personales."""

import asyncio
import json
import time
from datetime import datetime, timedelta, timezone

from backend import diagnostics
from backend.diagnostics import error_summary, failures_24h
from backend.providers import firms
from backend.services import stamp, utcnow

ERROR_KEYS = {"window_h", "by_product", "cycle_errors"}
PRODUCT_KEYS = {"runs", "failed", "last_failed_at"}


def seed_run(db, product: str, hours_ago: float, ok: bool, message: str = "detalle que no debe publicarse") -> str:
    started = stamp(utcnow() - timedelta(hours=hours_ago))
    db.execute(
        "INSERT INTO ingest_runs(provider, product, started_at, finished_at, ok, n_records, n_new, message) VALUES (?,?,?,?,?,?,?,?)",
        ("prueba", product, started, started, int(ok), 0, 0, message),
    )
    return started


def test_error_summary_counts_by_product_and_window(make_client):
    with make_client() as client:
        db = client.app.state.services.db
        seed_run(db, "VIIRS", 1, True)
        last_fail = seed_run(db, "VIIRS", 2, False)
        seed_run(db, "VIIRS", 30, False)  # fuera de la ventana de 24 h: no cuenta
        goes_fail = seed_run(db, "GOES-19", 3, False)

        body = client.get("/api/status").json()
        errors = body["errors"]
        assert errors["window_h"] == 24
        assert errors["by_product"] == {
            "GOES-19": {"runs": 1, "failed": 1, "last_failed_at": goes_fail},
            "VIIRS": {"runs": 2, "failed": 1, "last_failed_at": last_fail},
        }


def test_error_summary_cycle_errors_from_last_cycle(make_client):
    with make_client() as client:
        db = client.app.state.services.db
        assert client.get("/api/status").json()["errors"]["cycle_errors"] == []
        db.kv_set("last_cycle", json.dumps({"started_at": stamp(), "fwi_error": True, "backup_error": "x", "backup": False}))
        assert client.get("/api/status").json()["errors"]["cycle_errors"] == ["backup_error", "fwi_error"]


def test_error_summary_shape_and_empty_db(make_client):
    """El bloque solo trae las claves documentadas: conteos e instantes, nada de mensajes libres."""
    with make_client() as client:
        r = client.get("/api/status")
        assert r.status_code == 200
        errors = r.json()["errors"]
        assert set(errors) == ERROR_KEYS
        assert errors["window_h"] == 24 and errors["by_product"] == {} and errors["cycle_errors"] == []
        seed_run(client.app.state.services.db, "VIIRS", 1, False)
        for info in client.get("/api/status").json()["errors"]["by_product"].values():
            assert set(info) == PRODUCT_KEYS


def test_failures_24h_empty(make_client):
    with make_client() as client:
        r = client.get("/api/status")
        assert r.status_code == 200
        assert r.json()["failures_24h"] == {}


def test_failures_24h_counts_and_last_error(make_client):
    with make_client() as client:
        db = client.app.state.services.db
        seed_run(db, "VIIRS", 1, True)
        seed_run(db, "VIIRS", 2, True)
        last_fail = seed_run(db, "VIIRS", 3, False, message="x" * 200)
        failures = client.get("/api/status").json()["failures_24h"]
        assert failures["VIIRS"] == {"runs": 3, "failed": 1, "last_failed_at": last_fail, "last_error": "x" * 160}


def test_failures_24h_ignores_runs_older_than_window(make_client):
    with make_client() as client:
        db = client.app.state.services.db
        seed_run(db, "VIIRS", 30, False, message="viejo")
        assert client.get("/api/status").json()["failures_24h"] == {}


def test_failures_24h_product_without_failures(make_client):
    with make_client() as client:
        db = client.app.state.services.db
        seed_run(db, "GOES-19", 1, True)
        failures = client.get("/api/status").json()["failures_24h"]
        assert failures["GOES-19"] == {"runs": 1, "failed": 0, "last_failed_at": None, "last_error": None}


def test_errors_y_failures_24h_coinciden_por_producto(make_client):
    """Los dos bloques de fallas salen de la misma consulta: dicen lo mismo, sin `last_error` en `errors`."""
    with make_client() as client:
        db = client.app.state.services.db
        seed_run(db, "VIIRS", 1, True)
        seed_run(db, "VIIRS", 2, False)
        seed_run(db, "GOES-19", 3, False)
        seed_run(db, "GOES-19", 4, True)
        seed_run(db, "GOES-19", 30, False)  # fuera de la ventana de 24 h: no cuenta

        body = client.get("/api/status").json()
        errors = body["errors"]["by_product"]
        failures = body["failures_24h"]
        assert set(errors) == set(failures) == {"GOES-19", "VIIRS"}
        for product, info in errors.items():
            assert info == {key: failures[product][key] for key in PRODUCT_KEYS}


class DbQueCuenta:
    """Base de prueba que anota cada `query` para contar las consultas a `ingest_runs`."""

    def __init__(self, db):
        self._db = db
        self.consultas = []

    def query(self, sql, params=()):
        self.consultas.append(sql)
        return self._db.query(sql, params)

    def kv_get(self, key):
        return self._db.kv_get(key)


def test_los_dos_bloques_comparten_una_sola_consulta_a_ingest_runs(make_client):
    """Sin el GROUP BY duplicado: una sola forma de consulta, ejecutada una vez por bloque."""
    with make_client() as client:
        seed_run(client.app.state.services.db, "VIIRS", 1, False)
        db = DbQueCuenta(client.app.state.services.db)
        error_summary(db)
        failures_24h(db)
        consultas = [sql for sql in db.consultas if "ingest_runs" in sql]
        assert len(set(consultas)) == 1
        # Dos ejecuciones: `public.py` pide los dos bloques por separado (no se toca en este ítem).
        assert len(consultas) == 2


def test_bloques_de_status_conservan_el_json_de_referencia(make_client, monkeypatch):
    """DET-26: tres productos con fallos mezclados publican byte a byte lo mismo que antes del cambio.

    La referencia se generó con el código previo (d7f2cf5) y la hora fija, para que `last_failed_at`
    sea literal: un cambio de forma, de orden o de tipo en cualquiera de los dos bloques falla aquí.
    """
    monkeypatch.setattr(diagnostics, "utcnow", lambda: datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc))
    with make_client() as client:
        db = client.app.state.services.db
        for product, started, ok, message in (
            ("GOES-19", "2026-10-20T09:00:00Z", 0, "fallo goes"),
            ("GOES-19", "2026-10-20T07:00:00Z", 1, ""),
            ("MODIS", "2026-10-20T08:00:00Z", 1, ""),
            ("MODIS", "2026-10-20T06:00:00Z", 0, "x" * 200),
            ("VIIRS", "2026-10-20T11:00:00Z", 1, ""),
            ("VIIRS", "2026-10-19T11:00:00Z", 0, "fuera de ventana"),
        ):
            db.execute(
                "INSERT INTO ingest_runs(provider, product, started_at, finished_at, ok, n_records, n_new, message) "
                "VALUES (?,?,?,?,?,?,?,?)",
                ("prueba", product, started, started, ok, 0, 0, message),
            )
        db.kv_set("last_cycle", json.dumps({"started_at": "2026-10-20T12:00:00Z", "fwi_error": True, "backup": False}))

        body = client.get("/api/status").json()
        published = json.dumps({"errors": body["errors"], "failures_24h": body["failures_24h"]}, separators=(",", ":"))
        assert published == (
            '{"errors":{"window_h":24,"by_product":{'
            '"GOES-19":{"runs":2,"failed":1,"last_failed_at":"2026-10-20T09:00:00Z"},'
            '"MODIS":{"runs":2,"failed":1,"last_failed_at":"2026-10-20T06:00:00Z"},'
            '"VIIRS":{"runs":1,"failed":0,"last_failed_at":null}},'
            '"cycle_errors":["fwi_error"]},'
            '"failures_24h":{'
            '"GOES-19":{"runs":2,"failed":1,"last_failed_at":"2026-10-20T09:00:00Z","last_error":"fallo goes"},'
            '"MODIS":{"runs":2,"failed":1,"last_failed_at":"2026-10-20T06:00:00Z","last_error":"' + "x" * 160 + '"},'
            '"VIIRS":{"runs":1,"failed":0,"last_failed_at":null,"last_error":null}}}'
        )


def test_status_firms_quota_no_espera_a_firms(make_client, monkeypatch):
    """ROB-01: con el cupo vencido y FIRMS colgado, /api/status responde lo guardado en <1 s."""

    async def cuelgue(*_args, **_kwargs):
        await asyncio.sleep(60)
        return {}

    monkeypatch.setattr(firms, "key_status", cuelgue)
    with make_client(FIRMS_MAP_KEY="map-key-secreta-123") as client:
        db = client.app.state.services.db
        db.kv_set("firms_quota", json.dumps({"limit": 5000, "used": 12, "checked_at": "2020-01-01T00:00:00Z"}))
        inicio = time.perf_counter()
        r = client.get("/api/status")
        demora = time.perf_counter() - inicio
        assert r.status_code == 200 and demora < 1.0
        assert r.json()["firms_quota"] == {"limit": 5000, "used": 12, "checked_at": "2020-01-01T00:00:00Z", "error": True}


def test_status_firms_quota_sin_lectura_guardada(make_client):
    """ROB-01: sin lectura previa en `kv` el bloque sale con nulos y error, sin esperar a FIRMS."""
    with make_client(FIRMS_MAP_KEY="map-key-secreta-123") as client:
        r = client.get("/api/status")
        assert r.status_code == 200
        assert r.json()["firms_quota"] == {"limit": None, "used": None, "checked_at": None, "error": True}

"""OPS-14: /api/status publica un resumen de errores de la ingesta, sin datos personales."""

import asyncio
import json
import logging
import time
from datetime import timedelta

import httpx

from backend.diagnostics import error_summary, failures_24h
from backend.providers import _retry, firms
from backend.services import stamp, utcnow

ERROR_KEYS = {"window_h", "by_product", "cycle_errors", "cycle_detail", "desfase"}
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


def test_failures_24h_counts_and_last_error(make_client):
    with make_client() as client:
        db = client.app.state.services.db
        seed_run(db, "VIIRS", 1, True)
        seed_run(db, "VIIRS", 2, True)
        last_fail = seed_run(db, "VIIRS", 3, False, message="x" * 200)
        failures = client.get("/api/status").json()["failures_24h"]
        assert failures["VIIRS"] == {"runs": 3, "failed": 1, "last_failed_at": last_fail, "last_error": "x" * 160}


class CountingDB:
    """Base de prueba: delega en la real y separa el agregado de la consulta del último error."""

    def __init__(self, db):
        self.db = db
        self.aggregate_sql: list[str] = []
        self.last_error_sql: list[str] = []

    def query(self, sql, params=()):
        if "COUNT(*) AS runs" in sql:
            self.aggregate_sql.append(sql)
        if "MAX(id) AS id" in sql:
            self.last_error_sql.append(sql)
        return self.db.query(sql, params)

    def kv_get(self, key):
        return self.db.kv_get(key)


def test_los_dos_bloques_coinciden_por_producto(make_client):
    """Ambos bloques comparten `_by_product`: mismos conteos e instantes, sin `last_error`."""
    with make_client() as client:
        db = client.app.state.services.db
        seed_run(db, "VIIRS", 1, True)
        seed_run(db, "VIIRS", 2, False)
        seed_run(db, "GOES-19", 3, False)

        body = client.get("/api/status").json()
        assert set(body["errors"]["by_product"]) == set(body["failures_24h"])
        for product, info in body["failures_24h"].items():
            assert body["errors"]["by_product"][product] == {k: info[k] for k in PRODUCT_KEYS}


def test_cada_funcion_consulta_el_group_by_una_vez(make_client):
    """`error_summary` y `failures_24h` comparten `_by_product`: un agregado por función.

    La segunda consulta de `failures_24h` (el `MAX(id)` por producto) es distinta y solo
    la ejecuta ese bloque.
    """
    with make_client() as client:
        db = client.app.state.services.db
        seed_run(db, "VIIRS", 1, False)
        counting = CountingDB(db)

        error_summary(counting)
        assert len(counting.aggregate_sql) == 1
        assert "last_error" not in counting.aggregate_sql[0]
        assert counting.last_error_sql == []

        failures_24h(counting)
        assert len(counting.aggregate_sql) == 2
        assert len(set(counting.aggregate_sql)) == 1
        assert len(counting.last_error_sql) == 1


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


def test_backup_error_publico_sin_texto_crudo(make_client, monkeypatch, caplog):
    """OPS-43: `last_cycle.backup_error` dice en palabras que el respaldo falló, sin pegar
    el `str(exc)` (multilínea y con URLs); el detalle completo queda en el registro."""
    with make_client() as client:
        svc = client.app.state.services

        async def sin_ingesta():
            return {}

        request = httpx.Request("PUT", "https://almacenamiento.invalid/db/work.db.gz")
        response = httpx.Response(500, request=request)
        error_http = _retry.Failure(
            httpx.HTTPStatusError(
                "Server error '500 Internal Server Error' for url 'https://almacenamiento.invalid/db/work.db.gz'\n"
                "For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/500",
                request=request,
                response=response,
            ),
            attempts=4,
        )

        class RespaldoQueFalla:
            enabled = True

            async def flush(self):
                raise error_http

            async def flush_work(self):
                raise TimeoutError("agotado en https://almacenamiento.invalid/db/work.db.gz")

            async def stop(self):
                pass

        monkeypatch.setattr(svc, "tick", sin_ingesta)
        monkeypatch.setattr(svc, "persistence", RespaldoQueFalla())
        with caplog.at_level(logging.WARNING, logger="brasa"):
            asyncio.run(svc.tick_and_backup())

        body = client.get("/api/status").json()
        publicado = body["last_cycle"]["backup_error"]
        assert "backup_error" in body["errors"]["cycle_errors"]
        assert "http" not in publicado and "developer.mozilla" not in publicado and "\n" not in publicado
        assert publicado == (
            "No se pudo subir el respaldo (error 500 del almacenamiento). work: No se pudo subir el respaldo (TimeoutError)."
        )
        # El detalle completo, con la URL y la traza del cliente HTTP, sigue en el registro.
        assert "developer.mozilla.org" in caplog.text
        assert "almacenamiento.invalid" in caplog.text

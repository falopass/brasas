"""QA-3.2: descartes por fuente en «Calidad de los datos».

Fija tres cosas: que los parsers cuenten lo que dejaron fuera (`csv_hotspots`,
`fetch_hotspots`, `parse_fdc` exponen `.descartes` sin cambiar la lista que devuelven),
que la migración agregue `ingest_runs.discards` a una base vieja y que
`GET /api/observability/descartes` sume por fuente con null donde no se midió.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3

import httpx
import pytest

from backend.db import Database
from backend.providers import firms, goes
from backend.services import stamp
from tests.test_goes import synthetic_fdc

CSV = """latitude,longitude,bright_ti4,acq_date,acq_time,frp,confidence,daynight
-35.43,-71.66,330.1,2026-10-16,0140,21.5,n,N
-35.43,-65.00,330.1,2026-10-16,0140,10.1,n,N
malformed,-71.66,330.1,2026-10-16,0140,21.5,n,N
-35.40,-71.60,331.0,2026-10-16,140,,h,D
-35.41,-71.61,331.0,2026-10-16,0975,3.0,h,D
"""
MAULE = [-72.85, -36.25, -70.25, -34.65]


def test_csv_hotspots_cuenta_recibidas_y_descartes_por_motivo():
    puntos = firms.csv_hotspots(CSV, "VIIRS_SNPP_NRT", MAULE)
    assert len(puntos) == 2  # la lista no cambia
    # -65.00 cae fuera del bbox; la latitud «malformed» y el minuto 75 son filas inválidas.
    assert puntos.descartes == {"recibidas": 5, "fuera_de_chile": 1, "fila_invalida": 2}


def test_fetch_hotspots_agrega_los_descartes_por_fuente():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=CSV)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await firms.fetch_hotspots("k", MAULE, ("VIIRS_SNPP_NRT", "MODIS_NRT"), client=client)

    puntos, _notices = asyncio.run(run())
    esperado = {"recibidas": 5, "fuera_de_chile": 1, "fila_invalida": 2}
    assert puntos.descartes == {"VIIRS_SNPP_NRT": esperado, "MODIS_NRT": esperado}


def test_parse_fdc_cuenta_los_pixeles_fuera_de_chile():
    content = synthetic_fdc([(-35.0, -71.5, 10, 61.0), (-31.5, -68.0, 10, 50.0)])  # Hualañé y San Juan (Argentina)
    puntos = goes.parse_fdc(content, "G19")
    assert len(puntos) == 1
    assert puntos.descartes == {"GOES19_FDCF": {"recibidas": 2, "fuera_de_chile": 1, "fila_invalida": 0}}


def test_parse_fdc_sin_fuegos_tambien_informa_la_medicion():
    puntos = goes.parse_fdc(synthetic_fdc([]), "G19")
    assert puntos == []
    assert puntos.descartes == {"GOES19_FDCF": {"recibidas": 0, "fuera_de_chile": 0, "fila_invalida": 0}}


def test_migracion_agrega_discards_a_una_base_vieja(tmp_path):
    path = tmp_path / "brasa.db"
    vieja = sqlite3.connect(path.with_name("work.db"))
    vieja.execute(
        "CREATE TABLE ingest_runs (id INTEGER PRIMARY KEY AUTOINCREMENT, provider TEXT NOT NULL, "
        "product TEXT NOT NULL, started_at TEXT NOT NULL, finished_at TEXT, ok INTEGER NOT NULL DEFAULT 0, "
        "n_records INTEGER NOT NULL DEFAULT 0, n_new INTEGER NOT NULL DEFAULT 0, source_ref TEXT, "
        "sha256 TEXT, message TEXT)")
    vieja.execute("INSERT INTO ingest_runs(provider, product, started_at) VALUES ('NOAA GOES', 'GOES19_FDCF', '2026-01-01T00:00:00Z')")
    vieja.commit()
    vieja.close()
    db = Database(path)
    columnas = {row["name"] for row in db.query("PRAGMA work.table_info(ingest_runs)")}
    assert "discards" in columnas
    # La corrida antigua queda intacta y sin medir: NULL, no un JSON vacío.
    assert db.one("SELECT product, discards FROM ingest_runs") == {"product": "GOES19_FDCF", "discards": None}


def _run(db, provider: str, product: str, *, ok: int = 1, n_records: int = 0, discards=None) -> int:
    at = stamp()
    db.execute(
        "INSERT INTO ingest_runs(provider, product, started_at, finished_at, ok, n_records, n_new, discards) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (provider, product, at, at, ok, n_records, 0, json.dumps(discards, ensure_ascii=False) if discards else None),
    )
    return db.one("SELECT MAX(id) AS id FROM ingest_runs")["id"]


def _obs(db, oid: str, source: str, confidence: str, run_id: int, incident_id: str | None = None) -> None:
    at = stamp()
    db.execute(
        "INSERT INTO observations(id, source, sensor, lat, lon, observed_at, confidence, run_id, ingested_at) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (oid, source, "VIIRS", -33.5, -70.8, at, confidence, run_id, at),
    )
    if incident_id:
        db.execute("INSERT INTO incident_observations(observation_id, incident_id) VALUES (?,?)", (oid, incident_id))


def _incidente(db, iid: str, *, fixed: int = 0, status: str = "posible") -> None:
    at = stamp()
    db.execute(
        "INSERT INTO incidents(id, status, status_changed_at, first_seen_at, last_seen_at, lat, lon, "
        "min_lat, max_lat, min_lon, max_lon, n_obs, n_reliable, sensors, comuna_code, fixed_source, updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (iid, status, at, at, at, -33.5, -70.8, -33.5, -33.5, -70.8, -70.8, 1, 1, "VIIRS", None, fixed, at),
    )


def _fuentes(body: dict) -> dict[str, dict]:
    return {fila["source"]: fila for fila in body["fuentes"]}


def test_ruta_suma_por_fuente_y_marca_null_lo_no_medido(make_client):
    with make_client() as client:
        db = client.app.state.services.db
        firms_run = _run(
            db, "NASA FIRMS", "VIIRS_SNPP_NRT,MODIS_NRT", n_records=9,
            discards={"VIIRS_SNPP_NRT": {"recibidas": 10, "fuera_de_chile": 3, "fila_invalida": 1},
                      "MODIS_NRT": {"recibidas": 4, "fuera_de_chile": 1, "fila_invalida": 0}},
        )
        goes_run = _run(db, "NOAA GOES", "GOES19_FDCF", n_records=5)          # sin medir
        _run(db, "NOAA GOES", "GOES19_FDCF", ok=0)                            # la fallida no cuenta
        _run(db, "NOAA GOES", "GOES19_GLM")                                   # GLM no es fuente de focos
        _incidente(db, "fijo", fixed=1)
        _incidente(db, "fuera", status="descartado")
        _obs(db, "goes:1", "GOES19_FDCF", "alta", goes_run, "fijo")
        _obs(db, "goes:2", "GOES19_FDCF", "nominal", goes_run)
        _obs(db, "viirs:1", "VIIRS_SNPP_NRT", "baja", firms_run, "fuera")
        _obs(db, "viirs:2", "VIIRS_SNPP_NRT", "nominal", firms_run)
        _obs(db, "modis:1", "MODIS_NRT", "nominal", firms_run)
        body = client.get("/api/observability/descartes").json()
    assert body["horas"] == 24 and body["method"] and body["note"]
    fuentes = _fuentes(body)
    assert "GOES19_GLM" not in fuentes
    viirs = fuentes["VIIRS_SNPP_NRT"]
    assert viirs["corridas"] == 1 and viirs["corridas_sin_medir"] == 0
    assert (viirs["recibidas"], viirs["fuera_de_chile"], viirs["fila_invalida"]) == (10, 3, 1)
    assert viirs["nuevas"] == 2 and viirs["repetidas"] == 4  # 10 - 3 - 1 entregadas, 2 nuevas
    assert viirs["confianza_baja"] == 1 and viirs["fuera_del_pais"] == 1
    goes_fila = fuentes["GOES19_FDCF"]
    assert goes_fila["corridas"] == 1 and goes_fila["corridas_sin_medir"] == 1
    assert goes_fila["recibidas"] is None and goes_fila["fuera_de_chile"] is None
    assert goes_fila["nuevas"] == 2 and goes_fila["repetidas"] == 3  # n_records 5 - 2 nuevas
    assert goes_fila["fuente_fija"] == 1
    assert fuentes["MODIS_NRT"]["nuevas"] == 1 and fuentes["MODIS_NRT"]["repetidas"] == 2


def test_ruta_descartes_sin_corridas_devuelve_lista_vacia(make_client):
    with make_client() as client:
        body = client.get("/api/observability/descartes?horas=24").json()
    assert body["fuentes"] == []


@pytest.mark.parametrize("horas, esperado", [(0, 422), (169, 422), (1, 200), (168, 200)])
def test_ruta_descartes_valida_el_rango_de_horas(make_client, horas, esperado):
    with make_client() as client:
        assert client.get(f"/api/observability/descartes?horas={horas}").status_code == esperado

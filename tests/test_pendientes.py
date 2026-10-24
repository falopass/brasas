"""FUEGO-45: la pendiente real del terreno entra al escenario de propagación.

`backend/providers/elevation.py` pide la grilla 3×3 de 90 m a la API de elevación de
Open-Meteo (Copernicus DEM GLO-90) una sola vez por punto, calcula pendiente y orientación
con el método de Horn y deja el resultado en la caché permanente de la base.
`spread.estimate` la recibe por `terrain` o la lee de esa caché: con dato el escenario la
declara como estimada, sin dato sigue en terreno plano y también lo dice.
Sin red: el transporte HTTP está simulado (`tests/conftest.py::FakeWeb`).
"""

from __future__ import annotations

import asyncio
import json
import math
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
import pytest

from backend import spread
from backend.db import Database
from backend.providers import elevation, weather
from tests.conftest import json_response

CHILE = ZoneInfo("America/Santiago")
LAT, LON = -35.42, -71.65
NOW = datetime(2026, 1, 20, 17, 0, tzinfo=timezone.utc)
ROW = {"id": "inc-1", "comuna_code": 13101, "lat": LAT, "lon": LON}


@pytest.fixture(autouse=True)
def _contador_limpio(monkeypatch):
    """El contador de cupo de Open-Meteo es estado global: cada prueba arranca en cero."""
    monkeypatch.setattr(
        weather,
        "_calls",
        {"since": None, "day": None, "calls": 0, "locations": 0, "by_endpoint": {}, "by_endpoint_locations": {}, "rate_limited": 0},
    )


def _db(tmp_path) -> Database:
    return Database(tmp_path / "brasa.db")


async def _fetch(db: Database, handler):
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        return await elevation.slope_aspect(db, client, LAT, LON)


def _elevation_route(web, z: list[float]) -> None:
    web.add(lambda r: r.url.path == "/v1/elevation", lambda r: json_response({"elevation": z}))


def _plano(deg: float, cara: str) -> list[float]:
    """Grilla de un plano inclinado `deg` grados que BAJA hacia `cara` (norte o este)."""
    h = elevation.GRID_STEP_M * math.tan(math.radians(deg))
    # Orden de la grilla: NO, N, NE, O, C, E, SO, S, SE. Bajar al norte = subir al sur.
    return {
        "norte": [-h, -h, -h, 0.0, 0.0, 0.0, h, h, h],
        "este": [h, 0.0, -h, h, 0.0, -h, h, 0.0, -h],
    }[cara]


def _semilla_clima(db: Database, now: datetime) -> None:
    """El clima que la ingesta ya guardó para la comuna: FFMC del día y viento pronosticado."""
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    today = now.astimezone(CHILE).date().isoformat()
    db.execute(
        "INSERT INTO fwi_daily(comuna_code, date, ffmc, dmc, dc, isi, bui, fwi, level, computed_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (13101, today, 88.0, 20.0, 100.0, 5.0, 50.0, 15.0, "moderado", stamp),
    )
    hour = (now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%MZ")
    db.execute(
        "INSERT INTO risk_hourly(comuna_code, computed_at, payload) VALUES (?,?,?)",
        (13101, stamp, json.dumps([{"time": hour, "wind": 25.0, "dir": 250.0}])),
    )


def test_grilla_plana_da_pendiente_cero():
    slope, _ = elevation.slope_aspect_from_grid([500.0] * 9)
    assert slope == pytest.approx(0.0, abs=1e-9)


@pytest.mark.parametrize(("cara", "aspect_want"), [("norte", 0.0), ("este", 90.0)])
def test_plano_inclinado_da_la_pendiente_y_orientacion_esperadas(cara, aspect_want):
    """Un plano de 20° que baja al norte da pendiente 20° y ladera que mira al norte."""
    slope, aspect = elevation.slope_aspect_from_grid(_plano(20.0, cara))
    assert slope == pytest.approx(20.0, abs=1.0)
    assert aspect == pytest.approx(aspect_want, abs=1.0)


def test_la_consulta_pide_la_grilla_3x3_en_una_sola_llamada(tmp_path, web):
    db = _db(tmp_path)
    _elevation_route(web, [100.0] * 9)
    asyncio.run(_fetch(db, web.handler))
    [req] = web.requests
    lats = req.url.params["latitude"].split(",")
    lons = req.url.params["longitude"].split(",")
    assert len(lats) == len(lons) == 9
    assert f"{LAT:.4f}" in lats and f"{LON:.4f}" in lons
    # Una ubicación de cupo por punto de la grilla, en la misma contabilidad de Open-Meteo.
    assert weather.counts()["locations"] == 9


def test_api_caida_devuelve_none_y_el_escenario_queda_plano(tmp_path, web):
    db = _db(tmp_path)
    # Sin ruta simulada la FakeWeb responde 503: la API se cayó.
    assert asyncio.run(_fetch(db, web.handler)) is None
    _semilla_clima(db, NOW)
    out = spread.estimate(db, ROW, now=NOW)
    assert out is not None
    assert out["slope_deg"] is None and out["aspect_deg"] is None
    assert any("terreno plano" in a.lower() for a in out["assumptions"])


def test_cache_fresca_no_repite_la_llamada(tmp_path, web):
    db = _db(tmp_path)
    _elevation_route(web, _plano(20.0, "norte"))
    first = asyncio.run(_fetch(db, web.handler))
    assert first == (pytest.approx(20.0, abs=1.0), pytest.approx(0.0, abs=1.0))
    second = asyncio.run(_fetch(db, web.handler))
    assert second == first
    assert len(web.requests) == 1, "la segunda consulta del mismo punto sale de la caché"


def test_escenario_cuesta_arriba_mas_rapido_que_en_plano(tmp_path):
    """Con el mismo viento, el escenario con pendiente avanza más rápido que en terreno plano."""
    db = _db(tmp_path)
    _semilla_clima(db, NOW)
    flat = spread.estimate(db, ROW, now=NOW)
    uphill = spread.estimate(db, ROW, now=NOW, terrain=(20.0, 180.0))
    assert flat is not None and uphill is not None
    assert uphill["speed_m_min"] > flat["speed_m_min"]
    assert uphill["slope_deg"] == 20.0 and uphill["aspect_deg"] == 180.0
    assert any("Copernicus GLO-90" in a for a in uphill["assumptions"])
    assert uphill["kind"] == "escenario_estimado"
    assert any("terreno plano" in a.lower() for a in flat["assumptions"])


def test_estimacion_usa_el_relieve_ya_cacheado(tmp_path):
    """Sin `terrain` explícito, `estimate` lee la caché permanente que dejó la consulta al DEM:
    el mismo dato sirve al aviso y a la ficha sin otra llamada."""
    db = _db(tmp_path)
    _semilla_clima(db, NOW)
    db.cache_set(elevation.cache_key(LAT, LON), [20.0, 180.0], elevation.CACHE_TTL_S)
    out = spread.estimate(db, ROW, now=NOW)
    assert out["slope_deg"] == 20.0 and out["aspect_deg"] == 180.0
    assert not any("terreno plano" in a.lower() for a in out["assumptions"])


# ------------------------------------------------------- calentamiento en el ciclo

def _deteccion_reciente(db: Database, ident: str = "obs-1") -> None:
    """Una detección guardada pero no evaluada: el ciclo la recupera, la agrupa en un
    incidente y calienta su relieve antes de evaluar los avisos."""
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    db.execute(
        "INSERT INTO observations(id, source, sensor, satellite, resolution_m, lat, lon, observed_at, "
        "frp_mw, confidence, comuna_code, run_id, ingested_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL,?)",
        (ident, "firms", "VIIRS", "N20", 375, LAT, LON, stamp, 20.0, "alta", None, stamp))


def test_el_ciclo_calienta_la_pendiente_del_incidente_una_sola_vez(make_client, web):
    """FUEGO-45: el incidente tocado paga una sola llamada de 9 ubicaciones al DEM;
    la siguiente detección del mismo punto sale de la caché permanente."""
    _elevation_route(web, _plano(20.0, "norte"))
    with make_client(GOES_ENABLED="0") as client:
        svc = client.app.state.services
        _deteccion_reciente(svc.db)
        assert asyncio.run(svc.ingest_cycle())["incidents"] == 1
        assert len([r for r in web.requests if r.url.path == "/v1/elevation"]) == 1
        assert svc.db.cache_get(elevation.cache_key(LAT, LON)) is not None
        # Otra detección del mismo punto toca el mismo relieve: la caché responde, no la red.
        _deteccion_reciente(svc.db, "obs-2")
        asyncio.run(svc.ingest_cycle())
        assert len([r for r in web.requests if r.url.path == "/v1/elevation"]) == 1


def test_un_fallo_del_proveedor_de_elevacion_no_rompe_el_ciclo(make_client, web, monkeypatch):
    """La consulta al DEM es de mejor esfuerzo: un error inesperado se registra y el ciclo
    sigue con los avisos igual (el escenario queda en terreno plano)."""

    async def boom(*_args, **_kwargs):
        raise RuntimeError("caído")

    monkeypatch.setattr(elevation, "slope_aspect", boom)
    with make_client(GOES_ENABLED="0") as client:
        svc = client.app.state.services
        _deteccion_reciente(svc.db)
        result = asyncio.run(svc.ingest_cycle())
        assert result["incidents"] == 1 and result["failed_sources"] == []

"""AGUA-207: aviso diario de humo para personas sensibles.

Los lugares con `smoke_alerts` reciben un «aviso» cuando el MP2,5 máximo pronosticado por CAMS
(vía Open-Meteo) para mañana en su comuna supera la norma primaria diaria chilena (50 µg/m³,
D.S. N° 12/2011 del MMA). Una vez al día por lugar (`humo:<fecha>`); sin dato de CAMS no hay
aviso, y el dato se consulta una vez por comuna en la pasada.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from backend import alerts
from backend.db import Database
from backend.geo import territory

NOW = datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc)   # 09:00 en Chile continental
COMUNA_CODE = 13101


def _aire(pm25):
    async def lookup(_comuna):
        return {"pm25_tomorrow_max": pm25}
    return lookup


@pytest.fixture
def db(tmp_path):
    d = Database(tmp_path / "brasa.db")
    d.execute("INSERT INTO subscribers(id, created_at) VALUES ('s1','2026-01-01T00:00:00Z')")
    d.execute("INSERT INTO places(id, subscriber_id, name, kind, lat, lon, radius_km, comuna_code, created_at, "
              "smoke_alerts) VALUES ('casa','s1','Casa','casa',-33.05,-71.55,10,?,'2026-01-01T00:00:00Z',1)",
              (COMUNA_CODE,))
    return d


def test_sobre_la_norma_avisa_una_vez_al_dia(db):
    created = asyncio.run(alerts.evaluate_smoke(db, _aire(62.0), now=NOW))
    assert len(created) == 1
    payload = created[0]["payload"]
    hoy = NOW.astimezone(alerts.CHILE_TZ).date().isoformat()
    assert payload["level"] == "aviso"
    assert payload["observation"]["id"] == f"humo:{hoy}"
    for texto in ("62", "CAMS", "Open-Meteo", "50", "MINSAL"):
        assert texto in payload["body"], texto
    # segunda pasada del mismo día: el UNIQUE(place_id, observation_id) la deja en cero
    assert asyncio.run(alerts.evaluate_smoke(db, _aire(62.0), now=NOW)) == []


def test_sin_dato_cams_no_hay_aviso(db):
    async def sin_dato(_comuna):
        return None
    assert asyncio.run(alerts.evaluate_smoke(db, sin_dato, now=NOW)) == []
    assert asyncio.run(alerts.evaluate_smoke(db, _aire(None), now=NOW)) == []


def test_bajo_la_norma_no_avisa(db):
    assert asyncio.run(alerts.evaluate_smoke(db, _aire(49.9), now=NOW)) == []
    assert asyncio.run(alerts.evaluate_smoke(db, _aire(50.0), now=NOW)) == []   # la norma, justo en el borde


def test_solo_lugares_con_el_interruptor_reciben(db):
    db.execute("UPDATE places SET smoke_alerts = 0 WHERE id = 'casa'")
    assert asyncio.run(alerts.evaluate_smoke(db, _aire(80.0), now=NOW)) == []


def test_lugar_sin_comuna_no_avisa(db):
    db.execute("UPDATE places SET comuna_code = NULL WHERE id = 'casa'")
    assert asyncio.run(alerts.evaluate_smoke(db, _aire(80.0), now=NOW)) == []


def test_una_consulta_por_comuna_en_la_pasada(db):
    """Dos lugares de la misma comuna comparten la lectura: la pasada no multiplica llamadas."""
    db.execute("INSERT INTO places(id, subscriber_id, name, kind, lat, lon, radius_km, comuna_code, created_at, "
               "smoke_alerts) VALUES ('trabajo','s1','Trabajo','trabajo',-33.06,-71.56,10,?,'2026-01-02T00:00:00Z',1)",
               (COMUNA_CODE,))
    calls: list[int] = []

    async def aire(comuna):
        calls.append(comuna.code)
        return {"pm25_tomorrow_max": 60.0}

    created = asyncio.run(alerts.evaluate_smoke(db, aire, now=NOW))
    assert len(created) == 2
    assert calls == [COMUNA_CODE]


def test_el_aviso_de_humo_no_tapa_focos_reales(db):
    """Su lat/lon es el centro de la comuna: si contara en la deduplicación satelital,
    silenciaría detecciones reales a menos de DEDUPE_KM de ese centro (regla de `daily:`)."""
    asyncio.run(alerts.evaluate_smoke(db, _aire(70.0), now=NOW))
    comuna = territory().by_code.get(COMUNA_CODE)
    db.execute("UPDATE places SET lat = ?, lon = ?, radius_km = 30 WHERE id = 'casa'",
               (comuna.center[1], comuna.center[0]))
    obs = {"id": "o-real", "source": "firms", "sensor": "VIIRS", "satellite": "N20", "resolution_m": 375,
           "lat": comuna.center[1], "lon": comuna.center[0], "frp_mw": 20.0, "confidence": "alta",
           "observed_at": NOW.strftime("%Y-%m-%dT%H:%M:%SZ")}
    created = asyncio.run(alerts.evaluate(db, [obs], now=NOW))
    assert created and created[0]["payload"]["observation"]["id"] == "o-real"

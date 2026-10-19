"""Regla de frescura de 30 minutos: bordes de `age_seconds` y `status`.

`backend/freshness.py` es la única regla que decide si BRASA dice «al día» o «atrasada»
(píldora, Mi zona, ficha del incidente, modo vecino, Riesgo y Calidad). Estas pruebas fijan
los bordes: marca ausente, sin zona horaria, inválida, futura y el límite exacto de 1800 s.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend import freshness

NOW = datetime(2026, 10, 19, 12, 0, 0, tzinfo=timezone.utc)


def test_age_seconds_iso_z():
    assert freshness.age_seconds("2026-10-19T11:00:00Z", NOW) == 3600


def test_age_seconds_iso_offset_equivalente_a_z():
    # 08:00 -03:00 son las 11:00 UTC: una hora antes de NOW, igual que una marca con Z.
    assert freshness.age_seconds("2026-10-19T08:00:00-03:00", NOW) == 3600


def test_age_seconds_sin_zona_se_interpreta_como_utc():
    assert freshness.age_seconds("2026-10-19T11:30:00", NOW) == 1800


def test_age_seconds_marca_invalida_y_none():
    assert freshness.age_seconds("no-es-fecha", NOW) is None
    assert freshness.age_seconds(None, NOW) is None


def test_age_seconds_futuro_nunca_negativo():
    futuro = (NOW + timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert freshness.age_seconds(futuro, NOW) == 0


def test_status_sin_marca_es_atrasado():
    assert freshness.status(None, NOW) == {
        "last_ingest_at": None, "age_seconds": None, "stale_after_s": 1800, "stale": True}


def test_status_29_min_59_s_al_dia():
    marca = (NOW - timedelta(minutes=29, seconds=59)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert freshness.status(marca, NOW)["stale"] is False


def test_status_exactamente_30_min_al_dia():
    # El límite no se pasa: `stale` usa `age > STALE_AFTER_S`, así que 1800 s sigue al día.
    marca = (NOW - timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert freshness.status(marca, NOW) == {
        "last_ingest_at": marca, "age_seconds": 1800, "stale_after_s": 1800, "stale": False}


def test_status_30_min_1_s_atrasado():
    marca = (NOW - timedelta(minutes=30, seconds=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert freshness.status(marca, NOW)["stale"] is True


def test_status_endpoint_expone_claves_del_contrato(make_client):
    with make_client() as client:
        fresh = client.get("/api/status").json()["freshness"]
    assert {"age_seconds", "stale_after_s", "stale"} <= set(fresh)
    assert fresh["stale_after_s"] == 1800

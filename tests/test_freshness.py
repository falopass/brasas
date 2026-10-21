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
    assert freshness.status(None, NOW) == {"last_ingest_at": None, "age_seconds": None, "stale_after_s": 1800, "stale": True}


def test_status_29_min_59_s_al_dia():
    marca = (NOW - timedelta(minutes=29, seconds=59)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert freshness.status(marca, NOW)["stale"] is False


def test_status_exactamente_30_min_al_dia():
    # El límite no se pasa: `stale` usa `age > STALE_AFTER_S`, así que 1800 s sigue al día.
    marca = (NOW - timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert freshness.status(marca, NOW) == {"last_ingest_at": marca, "age_seconds": 1800, "stale_after_s": 1800, "stale": False}


def test_status_30_min_1_s_atrasado():
    marca = (NOW - timedelta(minutes=30, seconds=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert freshness.status(marca, NOW)["stale"] is True


def _hace(**kwargs) -> str:
    return (NOW - timedelta(**kwargs)).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_por_fuente_una_vieja_y_otra_al_dia():
    # GOES caído hace 2 horas, FIRMS entrando: el global dice «al día» pero aquí no.
    res = freshness.status_por_fuente({"goes": _hace(hours=2), "firms": _hace(minutes=10)}, NOW)
    assert res["stale"] is True
    assert res["fuentes_viejas"] == ["goes"]
    assert res["fuentes"]["goes"]["stale"] is True
    assert res["fuentes"]["firms"]["stale"] is False


def test_por_fuente_todas_al_dia():
    res = freshness.status_por_fuente({"goes": _hace(minutes=10), "firms": _hace(hours=2)}, NOW)
    assert res["stale"] is False
    assert res["fuentes_viejas"] == []
    assert set(res["fuentes"]) == {"goes", "firms"}


def test_por_fuente_marca_ausente_o_ilegible_es_vieja():
    res = freshness.status_por_fuente({"goes": None, "firms": "no-es-fecha"}, NOW)
    assert res["stale"] is True
    assert res["fuentes_viejas"] == ["goes", "firms"]
    assert res["fuentes"]["goes"]["age_seconds"] is None


def test_por_fuente_umbral_propio_de_cada_fuente():
    # Hace 40 minutos: para el umbral por omisión (30 min) está vieja, para GOES (45 min) no.
    res = freshness.status_por_fuente({"goes": _hace(minutes=40), "otra": _hace(minutes=40)}, NOW)
    assert res["fuentes"]["goes"]["stale"] is False
    assert res["fuentes"]["goes"]["stale_after_s"] == 45 * 60
    assert res["fuentes"]["otra"]["stale"] is True
    assert res["fuentes"]["otra"]["stale_after_s"] == 1800
    assert res["fuentes_viejas"] == ["otra"]


def test_por_fuente_vacio_no_dice_al_dia_ni_viejo():
    res = freshness.status_por_fuente({}, NOW)
    assert res == {"fuentes": {}, "fuentes_viejas": [], "stale": False}


def test_status_contrato_sin_cambios():
    # El consumidor de /api/status sigue recibiendo las mismas cuatro claves.
    assert set(freshness.status(None, NOW)) == {"last_ingest_at", "age_seconds", "stale_after_s", "stale"}


def test_status_endpoint_expone_claves_del_contrato(make_client):
    with make_client() as client:
        fresh = client.get("/api/status").json()["freshness"]
    assert {"age_seconds", "stale_after_s", "stale"} <= set(fresh)
    assert fresh["stale_after_s"] == 1800

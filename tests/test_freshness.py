"""Regla de frescura de 30 minutos: bordes de `age_seconds` y `status`.

`backend/freshness.py` es la única regla que decide si BRASA dice «al día» o «atrasada»
(píldora, Mi zona, ficha del incidente, modo vecino, Riesgo y Calidad). Estas pruebas fijan
los bordes: marca ausente, sin zona horaria, inválida, futura y el límite exacto de 1800 s.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend import freshness

NOW = datetime(2026, 10, 19, 12, 0, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "marca,segundos",
    [
        ("2026-10-19T11:00:00Z", 3600),
        ("2026-10-19T08:00:00-03:00", 3600),  # 08:00 -03:00 son las 11:00 UTC
        ("2026-10-19T11:30:00", 1800),        # sin zona se interpreta como UTC
    ],
)
def test_age_seconds(marca, segundos):
    assert freshness.age_seconds(marca, NOW) == segundos


def test_age_seconds_marca_invalida_y_none():
    assert freshness.age_seconds("no-es-fecha", NOW) is None
    assert freshness.age_seconds(None, NOW) is None


def test_age_seconds_futuro_nunca_negativo():
    futuro = (NOW + timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert freshness.age_seconds(futuro, NOW) == 0


def test_status_sin_marca_es_atrasado_y_declara_el_contrato():
    assert freshness.status(None, NOW) == {"last_ingest_at": None, "age_seconds": None, "stale_after_s": 1800, "stale": True}


@pytest.mark.parametrize(
    "edad,stale",
    [
        (timedelta(minutes=29, seconds=59), False),
        (timedelta(minutes=30), False),        # el límite no se pasa: `stale` usa age > 1800
        (timedelta(minutes=30, seconds=1), True),
    ],
)
def test_status_borde_de_30_minutos(edad, stale):
    marca = (NOW - edad).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert freshness.status(marca, NOW)["stale"] is stale


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
    # Hace 40 minutos: para el umbral por omisión (30 min) está vieja, para FIRMS (3 h) no.
    res = freshness.status_por_fuente({"firms": _hace(minutes=40), "otra": _hace(minutes=40)}, NOW)
    assert res["fuentes"]["firms"]["stale"] is False
    assert res["fuentes"]["firms"]["stale_after_s"] == 3 * 3600
    assert res["fuentes"]["otra"]["stale"] is True
    assert res["fuentes"]["otra"]["stale_after_s"] == 1800
    assert res["fuentes_viejas"] == ["otra"]


def test_umbrales_por_fuente_documentados():
    # FUEGO-08: la tabla de docs/FUENTES.md hecha constante.
    assert freshness.STALE_POR_FUENTE == {"goes": 1800, "firms": 3 * 3600, "conaf": 6 * 3600, "open-meteo": 6 * 3600}


def test_por_fuente_vacio_no_dice_al_dia_ni_viejo():
    res = freshness.status_por_fuente({}, NOW)
    assert res == {"fuentes": {}, "fuentes_viejas": [], "stale": False}


def test_status_endpoint_expone_el_contrato(make_client):
    """El consumidor de /api/status recibe exactamente las cuatro claves del contrato."""
    with make_client() as client:
        fresh = client.get("/api/status").json()["freshness"]
    assert set(fresh) == {"last_ingest_at", "age_seconds", "stale_after_s", "stale"}
    assert fresh["stale_after_s"] == 1800


# --- FUEGO-08: frescura por familia de la ingesta (`products`) ------------------


def test_products_firms_caido_marca_stale_global():
    # FIRMS lleva 2 h sin corrida buena y fallando; GOES al día. El global no dice «al día».
    products = {
        "FIRMS": {"last_ok_at": _hace(hours=2), "fallos_seguidos": 3},
        "GOES": {"last_ok_at": _hace(minutes=10), "fallos_seguidos": 0},
    }
    res = freshness.status(_hace(minutes=5), NOW, products=products)
    assert res["products"]["FIRMS"]["stale"] is True
    assert res["products"]["FIRMS"]["stale_after_s"] == 3 * 3600
    assert res["products"]["GOES"]["stale"] is False
    assert res["stale"] is True
    # El contrato del cliente actual no cambia.
    assert res["age_seconds"] == 300 and res["stale_after_s"] == 1800


def test_products_vacios_no_inventan_ni_dicen_al_dia():
    assert freshness.status(None, NOW, products={}) == freshness.status(None, NOW)
    assert "products" not in freshness.status(_hace(minutes=5), NOW, products={})


def test_products_familia_vieja_por_edad_sin_fallos():
    products = {"CONAF": {"last_ok_at": _hace(hours=7), "fallos_seguidos": 0}}
    res = freshness.status(_hace(minutes=5), NOW, products=products)
    assert res["products"]["CONAF"]["stale"] is True
    assert res["stale"] is True


def test_products_sin_marca_es_vieja():
    res = freshness.status(_hace(minutes=5), NOW, products={"GOES": {"last_ok_at": None, "fallos_seguidos": 0}})
    assert res["products"]["GOES"]["stale"] is True
    assert res["products"]["GOES"]["age_seconds"] is None


def test_productos_por_fuente_agrupa_por_familia():
    corridas = [
        {"provider": "NOAA GOES", "product": "GOES19_FDCF", "ok": 0},
        {"provider": "NOAA GOES", "product": "GOES19_FDCF", "ok": 0},
        {"provider": "NOAA GOES", "product": "GOES19_FDCF", "ok": 1},
        {"provider": "NOAA GOES", "product": "GOES19_GLM", "ok": 1},
        {"provider": "NASA FIRMS", "product": "VIIRS_NOAA20_NRT", "ok": 1},
        {"provider": "Dirección Meteorológica de Chile (DMC)", "product": "DMC_CAP", "ok": 1},
    ]
    last_ok = {"GOES19_FDCF": _hace(minutes=20), "GOES19_GLM": _hace(minutes=30), "VIIRS_NOAA20_NRT": _hace(hours=1)}
    familias = freshness.productos_por_fuente(corridas, last_ok)
    assert set(familias) == {"GOES", "FIRMS"}  # la DMC no mide frescura del mapa
    assert familias["GOES"] == {"last_ok_at": _hace(minutes=20), "fallos_seguidos": 2}
    assert familias["FIRMS"]["fallos_seguidos"] == 0


def test_status_endpoint_publica_products(make_client):
    """Con corridas reales en la base, freshness.products nombra la familia atrasada."""
    from backend.services import stamp, utcnow

    with make_client() as client:
        db = client.app.state.services.db
        vieja = stamp(utcnow() - timedelta(hours=4))
        reciente = stamp(utcnow() - timedelta(minutes=5))
        db.execute(
            "INSERT INTO ingest_runs(provider, product, started_at, finished_at, ok, n_records, n_new) VALUES (?,?,?,?,1,0,0)",
            ("NASA FIRMS", "VIIRS_NOAA20_NRT", vieja, vieja),
        )
        db.execute(
            "INSERT INTO ingest_runs(provider, product, started_at, finished_at, ok, n_records, n_new) VALUES (?,?,?,?,1,0,0)",
            ("NOAA GOES", "GOES19_FDCF", reciente, reciente),
        )
        db.kv_set("last_ingest_at", reciente)
        fresh = client.get("/api/status").json()["freshness"]
    assert fresh["stale"] is True  # FIRMS lleva 4 h sin corrida buena
    assert fresh["products"]["FIRMS"]["stale"] is True
    assert fresh["products"]["GOES"]["stale"] is False

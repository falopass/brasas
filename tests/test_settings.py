"""Pruebas de `backend/settings.py`: diagnóstico de variables de entorno mal escritas."""

import pytest

from backend import settings
from backend.settings import load

# Únicas variables que pueden generar una advertencia: las que pasan por _bool/_int.
PARSED_KEYS = [
    "BRASA_SCHEDULER",
    "INGEST_INTERVAL_MIN",
    "RISK_INTERVAL_MIN",
    "GOES_ENABLED",
    "EXPLORE_DAILY_LIMIT",
    "CONAF_PERIMETRO_ENABLED",
    "RAIN_NORMALS_PER_RUN",
]


@pytest.fixture(autouse=True)
def entorno_limpio(monkeypatch):
    """Aísla las pruebas del .env local y del ambiente de CI."""
    for key in PARSED_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_bool_mal_escrito_aplica_falso_y_avisa(monkeypatch):
    monkeypatch.setenv("GOES_ENABLED", "ture")
    s = load()
    assert s.goes_enabled is False
    assert "GOES_ENABLED" in {w["name"] for w in s.warnings}


def test_int_mal_escrito_aplica_default_y_avisa(monkeypatch):
    monkeypatch.setenv("INGEST_INTERVAL_MIN", "1O")
    s = load()
    assert s.ingest_interval_min == 10
    assert "INGEST_INTERVAL_MIN" in {w["name"] for w in s.warnings}


def test_bool_vacio_es_default_sin_aviso(monkeypatch):
    monkeypatch.setenv("GOES_ENABLED", "")
    s = load()
    assert s.goes_enabled is True
    assert s.warnings == ()


def test_advertencia_no_expone_valor_de_secreto(monkeypatch):
    """Una variable sensible mal escrita avisa, pero nunca con su valor crudo."""
    monkeypatch.setenv("ADMIN_TOKEN", "s3cret0-mal-escrito")
    warnings: list[dict] = []
    settings._bool("ADMIN_TOKEN", True, warnings)
    assert [w["name"] for w in warnings] == ["ADMIN_TOKEN"]
    assert "s3cret0-mal-escrito" not in str(warnings)


def test_load_sin_variables_no_lanza_y_sin_avisos():
    s = load()
    assert s.warnings == ()

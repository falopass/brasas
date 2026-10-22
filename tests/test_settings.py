"""Pruebas de `backend/settings.py`: diagnóstico de variables de entorno mal escritas."""

import pytest

from backend import settings
from backend.settings import load

# Variables que pueden generar una advertencia: las que pasan por _bool/_int y las de
# texto validadas (_url/_contacto/_data_dir/_secreto).
PARSED_KEYS = [
    "BRASA_SCHEDULER",
    "INGEST_INTERVAL_MIN",
    "RISK_INTERVAL_MIN",
    "GOES_ENABLED",
    "EXPLORE_DAILY_LIMIT",
    "CONAF_PERIMETRO_ENABLED",
    "RAIN_NORMALS_PER_RUN",
    "PUBLIC_BASE_URL",
    "VAPID_CONTACT",
    "BRASA_DATA_DIR",
    "INTERNAL_TOKEN",
    "TELEGRAM_WEBHOOK_SECRET",
]


@pytest.fixture(autouse=True)
def entorno_limpio(monkeypatch):
    """Aísla las pruebas del .env local y del ambiente de CI."""
    for key in PARSED_KEYS:
        monkeypatch.delenv(key, raising=False)


@pytest.mark.parametrize(
    "variable, valor, atributo, esperado",
    [
        ("GOES_ENABLED", "ture", "goes_enabled", False),
        ("INGEST_INTERVAL_MIN", "1O", "ingest_interval_min", 10),
    ],
)
def test_valor_mal_escrito_aplica_default_y_avisa(monkeypatch, variable, valor, atributo, esperado):
    monkeypatch.setenv(variable, valor)
    s = load()
    assert getattr(s, atributo) == esperado
    assert variable in {w["name"] for w in s.warnings}


def test_bool_vacio_es_default_sin_aviso(monkeypatch):
    monkeypatch.setenv("GOES_ENABLED", "")
    s = load()
    assert s.goes_enabled is True
    assert s.warnings == ()


@pytest.mark.parametrize(
    "valor, esperado, avisa",
    [
        pytest.param("contacto@brasa.cl", "mailto:contacto@brasa.cl", True, id="correo-pelado"),
        pytest.param("mailto:hola@brasa.cl", "mailto:hola@brasa.cl", False, id="bien-escrito"),
        pytest.param("no-es-un-correo", "mailto:contacto@example.org", True, id="invalido"),
    ],
)
def test_vapid_contact_se_corrige_y_avisa(monkeypatch, valor, esperado, avisa):
    monkeypatch.setenv("VAPID_CONTACT", valor)
    s = load()
    assert s.vapid_contact == esperado
    assert ("VAPID_CONTACT" in {w["name"] for w in s.warnings}) is avisa


@pytest.mark.parametrize(
    "valor, esperado, avisa",
    [
        pytest.param("brasa.cl", "https://brasa.cl", True, id="sin-esquema"),
        # Vacío no es «sin configurar»: significa tomar el host de la primera visita por HTTPS.
        pytest.param("", "", False, id="vacia"),
        pytest.param("https://brasa.cl/", "https://brasa.cl", False, id="slash-final"),
    ],
)
def test_public_base_url_se_normaliza(monkeypatch, valor, esperado, avisa):
    monkeypatch.setenv("PUBLIC_BASE_URL", valor)
    s = load()
    assert s.public_base_url == esperado
    assert ("PUBLIC_BASE_URL" in {w["name"] for w in s.warnings}) is avisa


def test_data_dir_apuntando_a_un_archivo_avisa_y_cae_al_default(monkeypatch, tmp_path):
    archivo = tmp_path / "ocupado.txt"
    archivo.write_text("no es un directorio")
    monkeypatch.setenv("BRASA_DATA_DIR", str(archivo))
    s = load()
    assert s.data_dir == settings.ROOT / "data"
    assert "BRASA_DATA_DIR" in {w["name"] for w in s.warnings}


@pytest.mark.parametrize(
    "variable, valor, atributo",
    [
        ("INTERNAL_TOKEN", "tok3n con espacio", "internal_token"),
        ("TELEGRAM_WEBHOOK_SECRET", "corto123", "telegram_webhook_secret"),
    ],
)
def test_secreto_debil_avisa_sin_exponer_el_valor_y_se_usa_igual(monkeypatch, variable, valor, atributo):
    monkeypatch.setenv(variable, valor)
    s = load()
    assert getattr(s, atributo) == valor
    assert variable in {w["name"] for w in s.warnings}
    assert valor not in str(s.warnings)


def test_secreto_valido_sin_aviso(monkeypatch):
    monkeypatch.setenv("INTERNAL_TOKEN", "a" * 32)
    assert load().warnings == ()

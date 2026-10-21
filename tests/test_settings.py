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


def test_vapid_contact_correo_pelado_se_corrige_y_avisa(monkeypatch):
    monkeypatch.setenv("VAPID_CONTACT", "contacto@brasa.cl")
    s = load()
    assert s.vapid_contact == "mailto:contacto@brasa.cl"
    assert "VAPID_CONTACT" in {w["name"] for w in s.warnings}


def test_vapid_contact_bien_escrito_sin_aviso(monkeypatch):
    monkeypatch.setenv("VAPID_CONTACT", "mailto:hola@brasa.cl")
    s = load()
    assert s.vapid_contact == "mailto:hola@brasa.cl"
    assert s.warnings == ()


def test_vapid_contact_invalido_cae_al_default(monkeypatch):
    monkeypatch.setenv("VAPID_CONTACT", "no-es-un-correo")
    s = load()
    assert s.vapid_contact == "mailto:contacto@example.org"
    assert "VAPID_CONTACT" in {w["name"] for w in s.warnings}


def test_public_base_url_sin_esquema_se_corrige_y_avisa(monkeypatch):
    monkeypatch.setenv("PUBLIC_BASE_URL", "brasa.cl")
    s = load()
    assert s.public_base_url == "https://brasa.cl"
    assert "PUBLIC_BASE_URL" in {w["name"] for w in s.warnings}


def test_public_base_url_vacia_aprende_del_primer_https(monkeypatch):
    # Vacío no es «sin configurar»: significa tomar el host de la primera visita por HTTPS.
    monkeypatch.setenv("PUBLIC_BASE_URL", "")
    s = load()
    assert s.public_base_url == ""
    assert s.warnings == ()


def test_public_base_url_con_slash_final_sin_aviso(monkeypatch):
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://brasa.cl/")
    s = load()
    assert s.public_base_url == "https://brasa.cl"
    assert s.warnings == ()


def test_data_dir_apuntando_a_un_archivo_avisa_y_cae_al_default(monkeypatch, tmp_path):
    archivo = tmp_path / "ocupado.txt"
    archivo.write_text("no es un directorio")
    monkeypatch.setenv("BRASA_DATA_DIR", str(archivo))
    s = load()
    assert s.data_dir == settings.ROOT / "data"
    assert "BRASA_DATA_DIR" in {w["name"] for w in s.warnings}


def test_secreto_debil_avisa_sin_exponer_el_valor(monkeypatch):
    monkeypatch.setenv("INTERNAL_TOKEN", "tok3n con espacio")
    s = load()
    assert "INTERNAL_TOKEN" in {w["name"] for w in s.warnings}
    assert "tok3n con espacio" not in str(s.warnings)


def test_secreto_corto_avisa_y_se_usa_igual(monkeypatch):
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "corto123")
    s = load()
    assert s.telegram_webhook_secret == "corto123"
    assert "TELEGRAM_WEBHOOK_SECRET" in {w["name"] for w in s.warnings}
    assert "corto123" not in str(s.warnings)


def test_secreto_valido_sin_aviso(monkeypatch):
    monkeypatch.setenv("INTERNAL_TOKEN", "a" * 32)
    assert load().warnings == ()

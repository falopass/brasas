"""Un solo diccionario de variantes de nombre de comuna (INE/CONAF → territorio BCN).

Las fuentes oficiales no siempre usan la grafía del índice territorial: el INE escribe
«Marchihue»/«Trehuaco» y CONAF «Paiguano»/«Llay-Llay». `scripts/nombres_comuna.py`
centraliza esas variantes para que la validación y la calibración no pierdan incendios.
"""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))  # los scripts importan backend.* y scripts.*

from scripts.nombres_comuna import VARIANTES, normalizar  # noqa: E402

spec = importlib.util.spec_from_file_location("validar_deteccion", ROOT / "scripts" / "validar_deteccion.py")
validar = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validar)

spec = importlib.util.spec_from_file_location("calibrar_riesgo", ROOT / "scripts" / "calibrar_riesgo.py")
calibrar = importlib.util.module_from_spec(spec)
spec.loader.exec_module(calibrar)

FIRE_COLS = (
    "id, name, status, status_raw, started_at, area_ha, lat, lon, comuna, region, "
    "detected_at, alerted_at, season, first_fetched_at, fetched_at"
)


def test_normalizar_aplica_la_variante_y_despues_pliega():
    assert VARIANTES["MARCHIHUE"] == "Marchigüe"
    assert normalizar("MARCHIHUE") == "marchigue"
    assert normalizar("Trehuaco") == "treguaco"
    assert normalizar("PAIGUANO") == "paihuano"
    assert normalizar("Llay-Llay") == "llaillay"
    # Sin variante conocida, normalizar es solo el _fold de backend/geo.py.
    assert normalizar("Curicó") == "curico"
    assert normalizar("  Hualañé ") == "hualane"


def test_marchihue_resuelve_el_codigo_de_marchigue():
    fires = [{"comuna": "MARCHIHUE"}, {"comuna": "TREHUACO"}]
    assert validar.resolve_comunas(fires) == []
    assert fires[0]["comuna_code"] == 6204  # Marchigüe, O'Higgins
    assert fires[1]["comuna_code"] == 16207  # Treguaco, Ñuble


def test_sin_calce_queda_en_la_lista_y_render_lo_imprime(tmp_path):
    """Un incendio en «COMUNA INVENTADA» no resuelve: queda en la lista y el informe la muestra."""
    from backend.db import Database

    db = Database(tmp_path / "brasa.db")
    db.execute(
        f"INSERT INTO work.official_fires({FIRE_COLS}) VALUES ({','.join('?' * 15)})",
        (
            "inc-x",
            "Foco X",
            "confirmado",
            "En combate",
            "2026-01-10T10:00:00Z",
            1.0,
            -34.98,
            -71.24,
            "COMUNA INVENTADA",
            "Maule",
            "2026-01-10T12:00:00Z",
            None,
            "2025-2026",
            "2026-01-15T00:00:00Z",
            "2026-01-15T00:00:00Z",
        ),
    )
    result = validar.validate(tmp_path / "work.db")
    assert result["sin_comuna_reconocida"] == ["COMUNA INVENTADA"]
    text = validar.render(result)
    assert "sin calce" in text and "| COMUNA INVENTADA | 1 |" in text


def test_render_sin_sin_calce_no_imprime_la_seccion(tmp_path):
    from backend.db import Database

    db = Database(tmp_path / "brasa.db")
    db.execute(
        f"INSERT INTO work.official_fires({FIRE_COLS}) VALUES ({','.join('?' * 15)})",
        (
            "inc-x",
            "Foco X",
            "confirmado",
            "En combate",
            "2026-01-10T10:00:00Z",
            1.0,
            -34.98,
            -71.24,
            "MARCHIHUE",
            "O'Higgins",
            "2026-01-10T12:00:00Z",
            None,
            "2025-2026",
            "2026-01-15T00:00:00Z",
            "2026-01-15T00:00:00Z",
        ),
    )
    result = validar.validate(tmp_path / "work.db")
    assert result["sin_comuna_reconocida"] == []
    fire = result["incendios"][0]
    assert fire["comuna_code"] == 6204
    assert "sin calce" not in validar.render(result)


def test_calibrar_riesgo_usa_la_variante(tmp_path):
    """«MARCHIHUE» cuenta como evento de Marchigüe (6204), no como comuna sin calce."""
    from backend.db import Database

    db = Database(tmp_path / "brasa.db", tmp_path / "work.db")
    db.execute(
        "INSERT INTO official_fires(id, name, status, status_raw, started_at, lat, lon, "
        "comuna, region, first_fetched_at, fetched_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (
            "f1",
            "f1",
            "confirmado",
            "En combate",
            "2026-01-10T15:00:00Z",
            -34.4,
            -71.6,
            "MARCHIHUE",
            "O'Higgins",
            "2026-01-20T00:00:00Z",
            "2026-01-20T00:00:00Z",
        ),
    )
    db.execute(
        "INSERT INTO risk_daily(comuna_code, date, level, score, hours_3of3, hours_2of3, "
        "level_combined, fwi_level, computed_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (6204, "2026-01-10", "alto", 50, 0, 0, "alto", "alto", "2026-01-20T00:00:00Z"),
    )
    db.close_all()
    result = calibrar.calibrate(tmp_path / "work.db")
    assert result["conteo"]["incendios_usados"] == 1
    assert result["conteo"]["sin_calce_comuna"] == 0
    assert result["comunas_sin_calce"] == []

"""ALR-26/ALR-24: el aviso de foco cierra con un paso concreto y la edad en palabras."""
from backend.alerts import ACTION_LINE, compose

PLACE = {"id": "casa", "name": "Mi casa", "lat": -35.4, "lon": -71.65}
OBS = {"id": "viirs:1", "observed_at": "2026-10-22T11:00:00Z", "confidence": "nominal",
       "lat": -35.4, "lon": -71.6, "source": "FIRMS", "sensor": "VIIRS", "satellite": "NOAA-20",
       "comuna": None, "region": None}


def cuerpo(level, older=False):
    return compose({**PLACE, "older_adult": older}, OBS, 1.2, 90, False, level, None, 0)["body"]


def test_urgente_tiene_accion_concreta_sin_promesas():
    b = cuerpo("urgente")
    assert any(v in b for v in ("Aleja", "ten agua", "cierra", "Sigue"))
    assert "predicción" not in b and "va a llegar" not in b
    assert "hace" in b  # la edad en palabras


def test_posible_no_repite_la_frase_urgente():
    assert "Aleja a tu familia" not in cuerpo("posible")


def test_persona_mayor_no_repite_la_salida():
    b = cuerpo("urgente", older=True)
    assert b.count("esperar a ver el fuego") <= 1


def test_aviso_no_gana_accion_nueva():
    assert "Aleja a tu familia" not in cuerpo("aviso")
    assert "teléfono cargado" not in cuerpo("aviso")


def test_action_line_exactamente_una_vez():
    assert cuerpo("urgente").count(ACTION_LINE) == 1

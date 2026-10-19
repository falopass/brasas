"""Boletín radial (IDEA-05): plantillas por reglas, tope de palabras y fuentes.

Los fixtures son respuestas fijas de /api/risk, /api/official-fires y /api/incidents:
ninguna prueba toca la red. `build_block` recibe None en la fuente que «no respondió».
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "local"))
import boletin  # noqa: E402

HORA = "08:30"
FUENTE = "Fuente: CONAF (Botón Rojo e incendios) y Open-Meteo vía BRASA al 08:30."

# Región mínima de prueba: «Maule» con dos comunas reales (Curicó 7301, Talca 7101).
REGION = {"code": 7, "name": "Maule", "fold": "maule", "comunas": {7301, 7101}}
REGIONES = [REGION, {"code": 8, "name": "Biobío", "fold": "biobio", "comunas": {8101}}]
COMUNA_REGION = {"curico": 7, "curicó": 7, "talca": 7, "concepcion": 8, "concepción": 8}

RISK = {
    "date": "2026-10-19",
    "comunas": {"7301": {"level": "alto", "level_combined": "alto"},
                "7101": {"level": "moderado", "level_combined": "alto"},
                "8101": {"level": "bajo", "level_combined": "bajo"}},
    "boton_rojo": {},
}
FIRES = [
    {"id": "1", "name": "EL BELLOTO", "status": "confirmado", "area_ha": 35.5,
     "comuna": "Curicó", "region": "Del Maule"},
    {"id": "2", "name": "VIEJO", "status": "extinguido", "area_ha": 10.0,
     "comuna": "Talca", "region": "Del Maule"},
    {"id": "3", "name": "OTRO", "status": "confirmado", "area_ha": 5.0,
     "comuna": "Concepción", "region": "Del Biobío"},
]
INCIDENTS = [
    {"id": "aaaabbbbcccc", "status": "posible", "comuna": "Talca", "region": "Maule"},
    {"id": "dddddddddddd", "status": "confirmado", "comuna": "Curicó", "region": "Maule"},
]


def build(risk=RISK, fires=FIRES, incidents=INCIDENTS, region=REGION):
    return boletin.build_block(region, risk, fires, incidents, HORA, COMUNA_REGION, REGIONES)


def test_region_sin_incendios_activos() -> None:
    b = build(fires=[])
    assert "riesgo" in b["texto"].lower() or "condiciones" in b["texto"].lower()
    assert "alto" in b["texto"] and "2 comunas" in b["texto"]
    assert "CONAF no informa incendios activos" in b["texto"]
    assert "incendio activo:" not in b["texto"]
    assert b["palabras"] <= boletin.MAX_PALABRAS


def test_region_con_boton_rojo() -> None:
    risk = {**RISK, "boton_rojo": {"7301": {"hours": 4, "area_ha": 1500, "proportion": 0.05}}}
    b = build(risk=risk)
    assert "Botón Rojo en 1 comuna" in b["texto"]
    assert b["palabras"] <= boletin.MAX_PALABRAS


def test_incendios_con_comuna_y_hectareas() -> None:
    b = build()
    assert "1 incendio activo" in b["texto"]
    assert "Curicó (35.5 ha)" in b["texto"]
    # El extinguido y el de otra región no entran al bloque.
    assert "VIEJO" not in b["texto"] and "Concepción" not in b["texto"]


def test_fuente_caida_no_rompe_el_bloque() -> None:
    b = build(fires=None)
    assert "sin datos de conaf en este momento" in b["texto"].lower()
    assert "alto" in b["texto"]  # el resto del bloque sigue con sus cifras
    assert b["palabras"] <= boletin.MAX_PALABRAS

    b = build(risk=None)
    assert "sin datos de riesgo" in b["texto"].lower()

    b = build(incidents=None)
    assert "sin datos del monitoreo satelital" in b["texto"].lower()


def test_toda_cifra_termina_con_fuente_y_tope_de_palabras() -> None:
    for b in (build(), build(fires=None), build(fires=None, incidents=None)):
        assert b["texto"].endswith(FUENTE)
        assert b["fuentes"], "el bloque debe declarar de dónde salen sus cifras"
        assert b["palabras"] == len(b["texto"].split())
        assert b["palabras"] <= boletin.MAX_PALABRAS


def test_fuente_caida_no_se_declara_como_fuente() -> None:
    b = build(fires=None)
    assert "CONAF (incendios)" not in b["fuentes"]


def test_focos_satelitales_sin_confirmar_se_mencionan() -> None:
    b = build()
    assert "1 foco de calor sin confirmar" in b["texto"]
    # El incidente «confirmado» lo cubre CONAF, no se repite como foco satelital.
    assert "2 focos" not in b["texto"]


def test_region_desconocida_en_datos_no_se_atribuye() -> None:
    fires = [{"id": "9", "name": "LEJOS", "status": "confirmado", "area_ha": 90.0,
              "comuna": "Comuna Inexistente", "region": "Región Inventada"}]
    b = build(fires=fires)
    assert "LEJOS" not in b["texto"]

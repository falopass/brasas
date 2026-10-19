"""Boletín radial (IDEA-05): plantillas por reglas, tope de palabras y fuentes.

Los fixtures son respuestas fijas de /api/risk, /api/official-fires y /api/incidents:
ninguna prueba toca la red. `build_block` recibe None en la fuente que «no respondió».
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "local"))
import boletin  # noqa: E402

HORA = "08:30"
FUENTE = "Fuente: CONAF (Botón Rojo e incendios) y Open-Meteo vía BRASA al 08:30."
AHORA = datetime(2026, 10, 19, 12, 0, tzinfo=ZoneInfo("America/Santiago"))

# Región mínima de prueba: «Maule» con dos comunas reales (Curicó 7301, Talca 7101).
REGION = {"code": 7, "name": "Maule", "fold": "maule", "comunas": {7301, 7101}}
REGIONES = [REGION, {"code": 8, "name": "Biobío", "fold": "biobio", "comunas": {8101}}]
COMUNA_REGION = {"curico": 7, "curicó": 7, "talca": 7, "concepcion": 8, "concepción": 8}
COMUNA_NOMBRES = {7301: "Curicó", 7101: "Talca", 8101: "Concepción"}

RISK = {
    "date": "2026-10-19",
    "comunas": {
        "7301": {"level": "alto", "level_combined": "alto"},
        "7101": {"level": "moderado", "level_combined": "alto"},
        "8101": {"level": "bajo", "level_combined": "bajo"},
    },
    "boton_rojo": {},
}
FIRES = [
    {"id": "1", "name": "EL BELLOTO", "status": "confirmado", "area_ha": 35.5, "comuna": "Curicó", "region": "Del Maule"},
    {"id": "2", "name": "VIEJO", "status": "extinguido", "area_ha": 10.0, "comuna": "Talca", "region": "Del Maule"},
    {"id": "3", "name": "OTRO", "status": "confirmado", "area_ha": 5.0, "comuna": "Concepción", "region": "Del Biobío"},
]
INCIDENTS = [
    {"id": "aaaabbbbcccc", "status": "posible", "comuna": "Talca", "region": "Maule"},
    {"id": "dddddddddddd", "status": "confirmado", "comuna": "Curicó", "region": "Maule"},
]

# Un aviso DMC tal como llega en risk["dmc"]: vigente entre las 09:00 y las 18:00 del
# día del fixture (AHORA = 12:00).
AVISO_VIENTO = {
    "kind": "viento",
    "label": "Viento",
    "event": "Viento Normal a Moderado",
    "headline": "Viento en el valle central",
    "severity": "Moderate",
    "urgency": "Expected",
    "onset": "2026-10-19T09:00:00-03:00",
    "expires": "2026-10-19T18:00:00-03:00",
    "web": "https://archivos.meteochile.gob.cl/portaldmc/AAA/doc/evento.html",
}


def build(risk=RISK, fires=FIRES, incidents=INCIDENTS, region=REGION, ahora=AHORA):
    return boletin.build_block(region, risk, fires, incidents, HORA, COMUNA_REGION, REGIONES, comuna_nombres=COMUNA_NOMBRES, ahora=ahora)


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
    fires = [
        {"id": "9", "name": "LEJOS", "status": "confirmado", "area_ha": 90.0, "comuna": "Comuna Inexistente", "region": "Región Inventada"}
    ]
    b = build(fires=fires)
    assert "LEJOS" not in b["texto"]


def test_aviso_dmc_vigente_en_la_region_se_menciona() -> None:
    # El mismo aviso cubre dos comunas de la región: se nombra una sola vez.
    risk = {**RISK, "dmc": {"7301": [AVISO_VIENTO], "7101": [AVISO_VIENTO]}}
    b = build(risk=risk)
    assert "aviso oficial de viento" in b["texto"]
    assert "Curicó y Talca" in b["texto"]
    assert "hasta las 18:00" in b["texto"]
    assert "DMC (avisos oficiales)" in b["fuentes"]
    assert b["palabras"] <= boletin.MAX_PALABRAS


def test_aviso_dmc_de_otra_region_no_se_menciona() -> None:
    risk = {**RISK, "dmc": {"8101": [AVISO_VIENTO]}}  # Concepción, Biobío
    b = build(risk=risk)
    assert "aviso oficial" not in b["texto"]
    assert "DMC (avisos oficiales)" not in b["fuentes"]


def test_aviso_dmc_vencido_no_se_menciona() -> None:
    vencido = {**AVISO_VIENTO, "expires": "2026-10-19T10:00:00-03:00"}  # venció a las 10:00
    risk = {**RISK, "dmc": {"7301": [vencido]}}
    b = build(risk=risk)
    assert "aviso oficial" not in b["texto"]
    assert "DMC (avisos oficiales)" not in b["fuentes"]


def test_aviso_dmc_tiene_prioridad_sobre_focos_al_recortar(monkeypatch) -> None:
    # Con un tope más bajo, el detalle satelital sale primero y el aviso DMC queda.
    monkeypatch.setattr(boletin, "MAX_PALABRAS", 60)
    risk = {**RISK, "dmc": {"7301": [AVISO_VIENTO]}}
    b = build(risk=risk)
    assert "aviso oficial de viento" in b["texto"]
    assert "foco" not in b["texto"]
    assert b["palabras"] <= 60

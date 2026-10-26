"""Dieta de fuentes (PESO-02): las tipografías variables quedaron instanciadas a
los ejes que la interfaz usa y recortadas a los glifos que muestra. Estas guardas
fijan el resultado para que nadie suba la fuente completa por descuido y para que
los @font-face de app.css sigan declarando los rangos reales de cada archivo.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "local"))
import dieta_fuentes  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
FUENTES = Path(__file__).resolve().parents[1] / "web" / "vendor" / "fonts"

# Techos con ~5 % de holgura sobre lo medido el 2026-10-26 tras la segunda
# pasada de la dieta (Anybody 45,4 KB sin cambios; Public Sans 16,5 KB: wght
# 400–750, sin kern ni hinting). La versión completa de Anybody pesaba 55,6 KB:
# cualquier recarga de la fuente original rompe este techo.
TOPE_KB = {
    "anybody-latin-standard-normal.woff2": 48,
    "public-sans-latin-wght-normal.woff2": 17,
}


def test_fuentes_bajo_el_tope():
    for nombre, tope in TOPE_KB.items():
        ruta = FUENTES / nombre
        assert ruta.is_file(), f"falta {ruta}"
        kb = ruta.stat().st_size / 1024
        assert kb <= tope, f"{nombre} pesa {kb:.1f} KB y el tope es {tope} KB"


def test_ejes_instanciados_a_la_receta():
    fontTools = pytest.importorskip("fontTools.ttLib")
    for nombre, ejes in dieta_fuentes.FUENTES.items():
        fuente = fontTools.TTFont(FUENTES / nombre)
        fvar = {a.axisTag: (a.minValue, a.maxValue) for a in fuente["fvar"].axes}
        for tag, esperado in ejes.items():
            assert fvar.get(tag) == esperado, f"{nombre}: eje {tag} en {fvar.get(tag)}, se esperaba {esperado}"


def test_cubren_espanol_y_puntuacion_de_la_interfaz():
    fontTools = pytest.importorskip("fontTools.ttLib")
    texto = "áéíóúñüÁÍÚÑ¿¡«»·°—–…‹›−×±0123456789"
    for nombre in dieta_fuentes.FUENTES:
        cmap = set(fontTools.TTFont(FUENTES / nombre).getBestCmap())
        faltan = [c for c in texto if ord(c) not in cmap]
        assert not faltan, f"{nombre} no cubre {faltan}"


def test_descriptores_css_reflejan_los_ejes_instanciados():
    """Los @font-face declaran los rangos reales: pedir fuera del rango haría
    al navegador sintetizar en vez de interpolar."""
    css = (ROOT / "web" / "css" / "app.css").read_text(encoding="utf-8")
    assert "font-weight: 600 900" in css
    assert "font-stretch: 60% 130%" in css
    assert "font-weight: 400 750" in css


def test_check_del_script_pasa_sobre_lo_commiteado():
    pytest.importorskip("fontTools")
    assert dieta_fuentes.main(["--check"]) == 0

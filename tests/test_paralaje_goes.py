"""INV-05: paralaje por relieve de los píxeles GOES y su medición contra CONAF.

La geometría del producto FDC no corrige la altura del terreno (NOAA, ReadMe FDC).
Estas pruebas fijan dos cosas: que la geometría con altura recupera el punto real y
que la medición contra los perímetros versionados es reproducible.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

from backend.providers import goes

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

spec = importlib.util.spec_from_file_location("medir_paralaje_goes", ROOT / "scripts" / "local" / "medir_paralaje_goes.py")
paralaje = importlib.util.module_from_spec(spec)
spec.loader.exec_module(paralaje)

PROJ = paralaje.PROJ


def test_ida_y_vuelta_con_altura():
    """Sin altura da lo mismo que antes; con altura, el ángulo intersectado devuelve el punto real."""
    for lat, lon in [(-33.45, -70.67), (-36.83, -73.05), (-53.16, -70.91), (-18.48, -70.31)]:
        x0, y0 = goes.latlon_to_scan(PROJ, lat, lon)
        x, y = goes.latlon_to_scan(PROJ, lat, lon, 0.0)
        assert (x, y) == pytest.approx((x0, y0), abs=1e-12)
        la0, lo0 = goes.scan_to_latlon(PROJ, np.array([x0]), np.array([y0]))
        la, lo = goes.scan_to_latlon(PROJ, np.array([x]), np.array([y]), 0.0)
        assert float(la[0]) == pytest.approx(float(la0[0]), abs=1e-12)
        assert float(lo[0]) == pytest.approx(float(lo0[0]), abs=1e-12)
        for altura in (1000.0, 3000.0, 5000.0):
            x, y = goes.latlon_to_scan(PROJ, lat, lon, altura)
            la, lo = goes.scan_to_latlon(PROJ, np.array([x]), np.array([y]), altura)
            assert float(la[0]) == pytest.approx(lat, abs=1e-6)
            assert float(lo[0]) == pytest.approx(lon, abs=1e-6)


def test_santiago_3000_m_se_desplaza_al_sur_y_la_correccion_al_norte():
    """La tabla que fija INV-05: 2,45 km, corrección al norte con algo de oeste."""
    d = paralaje.desplazamiento(PROJ, -33.45, -70.67, 3000.0)
    assert 2.35 <= d["km"] <= 2.55
    assert 350.0 <= d["rumbo_correccion"] <= 354.0
    assert 170.0 <= d["rumbo_aparente"] <= 174.0
    # El píxel aparente queda al sur y muy ligeramente al este del punto real.
    assert d["lat_aparente"] < -33.45
    assert d["lon_aparente"] > -70.67
    # La corrección inversa recupera el punto real.
    lat, lon = paralaje.corregir(PROJ, d["lat_aparente"], d["lon_aparente"], 3000.0)
    assert lat == pytest.approx(-33.45, abs=1e-6)
    assert lon == pytest.approx(-70.67, abs=1e-6)


def test_el_desplazamiento_crece_con_la_altura_y_hacia_el_sur():
    assert paralaje.desplazamiento(PROJ, -33.45, -70.67, 0.0)["km"] < 1e-9
    d1000 = paralaje.desplazamiento(PROJ, -33.45, -70.67, 1000.0)["km"]
    d3000 = paralaje.desplazamiento(PROJ, -33.45, -70.67, 3000.0)["km"]
    assert 0.7 <= d1000 <= 0.9 and 2.3 <= d3000 <= 2.6
    # A la misma altura, el sur de Chile se ve con más ángulo y se desplaza más.
    sur = paralaje.desplazamiento(PROJ, -53.16, -70.91, 3000.0)["km"]
    assert sur > d3000


def test_medir_caso_sintetico_cuenta_dentro_y_fuera(tmp_path: Path):
    """Un cuadrado de 0,1° y tres píxeles: uno dentro y dos al sur, a 5,5 y 11,1 km."""
    case = {"id": "sintetico"}
    (tmp_path / "cases").mkdir()
    (tmp_path / "cases" / "sintetico.goes.json").write_text(
        json.dumps(
            {
                "rows": [
                    [0, -33.00, -71.00, 10.0, 300.0, 2],
                    [10, -33.10, -71.00, 10.0, 300.0, 2],
                    [20, -33.15, -71.00, 10.0, 300.0, 2],
                ],
            }
        ),
        encoding="utf-8",
    )
    ring = [[-71.05, -33.05], [-70.95, -33.05], [-70.95, -32.95], [-71.05, -32.95], [-71.05, -33.05]]
    (tmp_path / "cases" / "sintetico.perimeter.json").write_text(
        json.dumps(
            {
                "features": [{"properties": {"nombre": "cuadrado"}, "geometry": {"type": "Polygon", "coordinates": [ring]}}],
            }
        ),
        encoding="utf-8",
    )

    result = paralaje.medir_caso(case, data_dir=tmp_path, sample=100)
    assert result["rows"] == 3
    assert result["inside"] == 1
    assert result["outside"] == 2
    assert result["inside_fraction"] == pytest.approx(1 / 3, abs=1e-6)
    assert 7.5 <= result["median_km"] <= 9.0
    assert result["bearing_mean"] < 10.0 or result["bearing_mean"] > 350.0
    assert result["bearing_sectors"][0] == 2


def test_el_caso_real_vina_fija_la_medicion():
    """Caso fijo: GOES-16 del complejo Viña 2024 contra los 4 perímetros de CONAF."""
    result = paralaje.medir_caso({"id": "vina-del-mar-2024"}, data_dir=ROOT / "web" / "data", sample=2000)
    assert result["rows"] == 2667
    assert result["polygons"] == 4
    assert result["inside"] == 1404
    assert result["outside"] == 1263
    assert 0.50 <= result["inside_fraction"] <= 0.55
    assert 0.45 <= result["median_km"] <= 0.65

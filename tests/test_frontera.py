"""Frontera y costa: la tolerancia territorial no puede rotular fuegos extranjeros.

Decisión del 2026-10-20 (INV-28): un solo margen de 0,03° (~3,3 km) para el filtro de
FIRMS y para la anotación de `/api/explore`. La medición de 60 días dejó 46 detecciones
en la franja 0,03–0,16°: 45 al este de la frontera y ninguna en la costa. Con 0,16° un
foco 10 km dentro de Argentina quedaba como comuna chilena; con 0,03° no entra.
"""

from __future__ import annotations

import httpx
import pytest

from backend.geo import territory
from backend.providers import firms

# Rectángulo amplio a propósito: el filtro territorial (no el bbox) decide qué pasa.
SOUTH_AMERICA = [-90.0, -60.0, -60.0, -10.0]


def _csv_of(points):
    header = "latitude,longitude,bright_ti4,acq_date,acq_time,frp,confidence,daynight\n"
    return header + "".join(f"{lat},{lon},330.0,2026-10-16,0140,10.0,n,N\n" for lat, lon in points)


def test_la_tolerancia_del_filtro_es_0_03_grados():
    """El valor es parte de la decisión: 0,16° ≈ 18 km admitía focos del país vecino."""
    assert firms.TERRITORY_TOLERANCE_DEG == pytest.approx(0.03)


def test_foco_10_km_en_argentina_no_entra_por_el_margen():
    """Paso Pehuenche: ~9,5 km al este del polígono comunal, lado argentino.

    Con 0,16° caía en San Clemente; con 0,03° no debe entrar al archivo de FIRMS.
    """
    lat, lon = -36.0, -70.2707
    assert territory().locate(lat, lon, tolerance_deg=0.16) is not None
    rows = firms.csv_hotspots(_csv_of([(lat, lon)]), "VIIRS_NOAA21_NRT", SOUTH_AMERICA)
    assert rows == []


def test_foco_costero_a_1_km_de_constitucion_entra():
    """Un píxel ~1 km mar adentro frente a Constitución sigue siendo Chile."""
    lat, lon = -35.33, -72.4469
    t = territory()
    assert t.locate(lat, lon, tolerance_deg=0) is None
    comuna = t.locate(lat, lon, tolerance_deg=firms.TERRITORY_TOLERANCE_DEG)
    assert comuna is not None and comuna.name == "Constitución"
    rows = firms.csv_hotspots(_csv_of([(lat, lon)]), "VIIRS_NOAA21_NRT", SOUTH_AMERICA)
    assert len(rows) == 1


def test_foco_en_el_maule_entra_y_conserva_su_comuna():
    lat, lon = -35.43, -71.66
    rows = firms.csv_hotspots(_csv_of([(lat, lon)]), "VIIRS_NOAA21_NRT", SOUTH_AMERICA)
    assert len(rows) == 1
    assert territory().locate(rows[0]["lat"], rows[0]["lon"]).name == "Talca"


def test_el_margen_esta_en_grados_y_no_en_metros():
    """A 35°S, 0,03° son ~3,3 km de latitud: 1 km entra, 4 km no."""
    t = territory()
    assert t.locate(-35.33, -72.4469, tolerance_deg=firms.TERRITORY_TOLERANCE_DEG) is not None
    assert t.locate(-35.33, -72.4800, tolerance_deg=firms.TERRITORY_TOLERANCE_DEG) is None


def test_el_filtro_no_invierte_lat_lon_ni_cambia_la_hora_utc():
    """FIRMS entrega latitude,longitude y UTC; el filtro no debe tocar ninguno de los dos."""
    rows = firms.csv_hotspots(_csv_of([(-35.43, -71.66)]), "VIIRS_NOAA21_NRT", SOUTH_AMERICA)
    assert len(rows) == 1
    row = rows[0]
    assert (row["lat"], row["lon"]) == (-35.43, -71.66)
    assert row["observed_at"] == "2026-10-16T01:40:00Z"
    assert row["date"] == "2026-10-16"


def test_explore_no_devuelve_un_foco_10_km_en_argentina(make_client, web):
    """La vista histórica usa el mismo filtro: el foco argentino no se rotula como chileno."""
    csv = "latitude,longitude,bright_ti4,acq_date,acq_time,frp,confidence\n-36.0,-70.2707,330.0,2026-10-16,0140,10.0,n\n"
    web.add(lambda r: "firms" in r.url.host, lambda r: httpx.Response(200, text=csv))
    with make_client(FIRMS_MAP_KEY="k-123") as client:
        r = client.get("/api/explore?zone=chile&mode=historical&start=2026-10-10&days=3")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["points"] == []
        assert data["in_chile"] == 0 and data["outside_chile"] == 0

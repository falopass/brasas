"""Margen territorial de las detecciones satelitales (FUEGO-10).

La capa comunal se simplificó a ~450 m (`scripts/build_territory.py`) y el píxel de
FIRMS mide 375 m. El margen de 0,03° (~3 km) cubre el borde costero generalizado sin
alcanzar los países vecinos. Antes eran 0,16° (~18 km): un foco 11 km dentro de
Bolivia se asignaba a la comuna de Pica.
"""

from __future__ import annotations

from backend.geo import HOTSPOT_TOLERANCE_DEG, inside_chile, locate_hotspot
from backend.providers import firms

# Un rectángulo amplio a propósito: el filtro territorial (no el bbox) decide qué pasa.
SOUTH_AMERICA = [-90.0, -60.0, -60.0, -10.0]


def _csv_of(points):
    header = "latitude,longitude,bright_ti4,acq_date,acq_time,frp,confidence,daynight\n"
    return header + "".join(f"{lat},{lon},330.0,2026-10-16,0140,10.0,n,N\n" for lat, lon in points)


def test_border_foci_from_neighbors_are_dropped():
    # Puntos reales de la franja 0,03-0,16: Argentina (0,138°), Bolivia (0,099°) y
    # Perú (0,134°) del polígono chileno más cercano. Los tres están en el país vecino.
    rows = firms.csv_hotspots(
        _csv_of(
            [
                (-34.39337, -69.80880),  # Argentina, Mendoza
                (-19.90283, -68.42510),  # Bolivia, Potosí
                (-17.57430, -69.90985),  # Perú, Tacna
                (-35.43, -71.66),  # Talca
            ]
        ),
        "VIIRS_NOAA21_NRT",
        SOUTH_AMERICA,
    )
    assert [(r["lat"], r["lon"]) for r in rows] == [(-35.43, -71.66)]


def test_coastal_pixel_within_new_margin_is_kept():
    # ~2,2 km frente a Valparaíso: fuera del polígono comunal, dentro de 0,03°.
    assert inside_chile(-33.04, -71.68)
    rows = firms.csv_hotspots(_csv_of([(-33.04, -71.68)]), "VIIRS_NOAA21_NRT", SOUTH_AMERICA)
    assert len(rows) == 1


def test_ocean_pixel_beyond_new_margin_is_dropped():
    # El punto que el margen de 0,16° conservaba está en el océano, a ~4,9 km del polígono.
    assert not inside_chile(-33.05, -71.75)
    rows = firms.csv_hotspots(_csv_of([(-33.05, -71.75)]), "VIIRS_NOAA21_NRT", SOUTH_AMERICA)
    assert rows == []


def test_islands_and_southern_coast_are_inside_without_margin():
    # La tolerancia grande no hacía falta para tierra firme, islas ni fiordos.
    for lat, lon in [
        (-33.64, -78.83),  # Juan Fernández
        (-42.48, -73.77),  # Castro, Chiloé
        (-45.40, -72.90),  # Puerto Chacabuco, Aysén
        (-51.73, -72.50),  # Puerto Natales
        (-53.16, -70.91),  # Punta Arenas
    ]:
        assert inside_chile(lat, lon), (lat, lon)
        assert locate_hotspot(lat, lon) is not None, (lat, lon)


def test_margin_pins_lat_lon_order_units_and_utc():
    # FIRMS entrega latitude,longitude y acq_time en UTC. Si se invirtieran lat/lon,
    # Talca caería en el océano y se descartaría.
    rows = firms.csv_hotspots(_csv_of([(-35.43, -71.66)]), "VIIRS_NOAA21_NRT", SOUTH_AMERICA)
    assert len(rows) == 1
    row = rows[0]
    assert (row["lat"], row["lon"]) == (-35.43, -71.66)
    assert row["observed_at"] == "2026-10-16T01:40:00Z"  # UTC, no hora de Chile
    assert row["resolution_m"] == 375  # metros
    assert row["frp_mw"] == 10.0  # MW


def test_margin_is_the_single_policy_value():
    assert HOTSPOT_TOLERANCE_DEG == 0.03

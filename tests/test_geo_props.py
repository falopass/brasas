"""Pruebas de propiedades de geo.py: distancia, rumbo, cardinal y viento a favor.

Estas funciones alimentan el texto visible de los avisos («a 4,2 km al NE») y la
regla que decide si el fuego está a barlovento. Barridos deterministas con
`random.Random` y semillas fijas, sin dependencias nuevas.
"""

from __future__ import annotations

import random

import pytest

from backend.geo import CARDINALS, angle_diff, bearing_deg, cardinal, haversine_km, is_upwind

SEEDS = (1234, 7, 42, 99, 2026)
SANTIAGO = (-33.45, -70.66)
VALPARAISO = (-33.04, -71.63)
ANTIPODA_TOL = 0.01


def rand_point(rng: random.Random) -> tuple[float, float]:
    return rng.uniform(-56.0, -17.0), rng.uniform(-76.0, -66.0)


# --- haversine_km ---


@pytest.mark.parametrize("seed", SEEDS)
def test_haversine_is_symmetric_and_zero_to_itself(seed):
    rng = random.Random(seed)
    for _ in range(200):
        lat1, lon1 = rand_point(rng)
        lat2, lon2 = rand_point(rng)
        assert haversine_km(lat1, lon1, lat1, lon1) == pytest.approx(0.0, abs=1e-9)
        assert haversine_km(lat1, lon1, lat2, lon2) == pytest.approx(haversine_km(lat2, lon2, lat1, lon1), abs=1e-9)


def test_haversine_known_distances():
    assert haversine_km(*SANTIAGO, *VALPARAISO) == pytest.approx(100.0, abs=5.0)
    antipoda = (-SANTIAGO[0], SANTIAGO[1] + 180.0)
    assert haversine_km(*SANTIAGO, *antipoda) == pytest.approx(20015.0, rel=ANTIPODA_TOL)


# --- bearing_deg ---


@pytest.mark.parametrize("seed", SEEDS)
def test_bearing_stays_in_range(seed):
    rng = random.Random(seed)
    for _ in range(300):
        lat1, lon1 = rand_point(rng)
        lat2, lon2 = rand_point(rng)
        b = bearing_deg(lat1, lon1, lat2, lon2)
        assert 0.0 <= b < 360.0


@pytest.mark.parametrize("seed", SEEDS)
def test_bearing_there_and_back_differs_by_180(seed):
    """Ida y vuelta difieren ~180°. Sobre la esfera el rumbo de retorno se desvía
    (crece con la distancia y la latitud): en el barrido el máximo observado es ~6°."""
    rng = random.Random(seed)
    for _ in range(200):
        lat1, lon1 = rand_point(rng)
        lat2, lon2 = rand_point(rng)
        if (lat1, lon1) == (lat2, lon2):
            continue
        ida = bearing_deg(lat1, lon1, lat2, lon2)
        vuelta = bearing_deg(lat2, lon2, lat1, lon1)
        assert angle_diff(vuelta, (ida + 180.0) % 360.0) == pytest.approx(0.0, abs=7.0)


def test_bearing_north_south_on_the_same_meridian_is_exact():
    assert bearing_deg(-33.0, -70.0, -30.0, -70.0) == pytest.approx(0.0, abs=1e-9)
    assert bearing_deg(-30.0, -70.0, -33.0, -70.0) == pytest.approx(180.0, abs=1e-9)


# --- cardinal ---


def test_cardinal_direcciones_y_bordes():
    esperados = {
        0.0: "norte",
        45.0: "noreste",
        90.0: "este",
        135.0: "sureste",
        180.0: "sur",
        225.0: "suroeste",
        270.0: "oeste",
        315.0: "noroeste",
    }
    for deg, nombre in esperados.items():
        assert cardinal(deg) == nombre
    assert set(esperados.values()) == set(CARDINALS)
    assert cardinal(22.4) == "norte"
    assert cardinal(22.5) == "noreste"  # el borde cierra hacia el rumbo siguiente
    assert cardinal(337.4) == "noroeste"
    assert cardinal(337.5) == "norte"  # el borde envuelve de vuelta a norte
    assert cardinal(360.0) == "norte"


# --- angle_diff ---


@pytest.mark.parametrize("seed", SEEDS)
def test_angle_diff_in_range_and_symmetric(seed):
    rng = random.Random(seed)
    for _ in range(400):
        a, b = rng.uniform(-720.0, 720.0), rng.uniform(-720.0, 720.0)
        d = angle_diff(a, b)
        assert 0.0 <= d <= 180.0
        assert d == pytest.approx(angle_diff(b, a), abs=1e-9)


def test_angle_diff_known_values():
    assert angle_diff(10.0, 350.0) == pytest.approx(20.0)
    assert angle_diff(0.0, 180.0) == pytest.approx(180.0)
    assert angle_diff(45.0, 45.0) == pytest.approx(0.0)


# --- is_upwind ---


def test_is_upwind_needs_real_wind():
    assert not is_upwind(90.0, None, 30.0)
    assert not is_upwind(90.0, 270.0, None)
    assert not is_upwind(90.0, 270.0, 0.0)  # viento nulo no trae el fuego
    assert not is_upwind(90.0, 270.0, 7.9)  # bajo el mínimo tampoco


def test_is_upwind_within_and_outside_tolerance():
    # el foco está al este del lugar (rumbo 90) y el viento viene del este
    assert is_upwind(90.0, 90.0, 20.0)
    assert is_upwind(90.0, 90.0 + 44.9, 20.0)
    assert not is_upwind(90.0, 90.0 + 45.1, 20.0)
    assert not is_upwind(90.0, 270.0, 20.0)  # viento en contra: el humo se aleja

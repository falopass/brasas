"""RISK-07: la grilla 1° del bbox, el parseo de Open-Meteo, la caché y el cupo."""
from datetime import datetime, timezone

from backend import windgrid

AHORA = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)


def test_grilla_dentro_del_bbox_continental():
    puntos = windgrid.grid_points()
    w, s, e, n = windgrid.CHILE_BBOX
    assert 300 <= len(puntos) <= 450  # ~380 celdas a 1°
    for lat, lon in puntos:
        assert s <= lat <= n and w <= lon <= e
        # centros de celda: siempre en .5
        assert abs(lat - round(lat)) == 0.5 and abs(lon - round(lon)) == 0.5


def test_build_grid_toma_la_hora_mas_cercana_y_respeta_la_convencion():
    puntos = [(lat, lon) for lat, lon in windgrid.grid_points()[:3]]
    filas = [{"time": ["2026-10-23T10:00", "2026-10-23T12:00", "2026-10-23T14:00"],
              "wind_speed_10m": [10, 25, 40], "wind_direction_10m": [90, 180, 270]} for _ in puntos]
    grid = windgrid.build_grid(puntos, filas, AHORA)
    assert grid["computed_at"] == "2026-10-23T12:00:00Z"
    assert grid["speed"] == [25.0, 25.0, 25.0]
    assert grid["dir"] == [180, 180, 180]
    assert len(grid["points"]) == 3


def test_build_grid_sin_datos_no_rompe():
    grid = windgrid.build_grid([(-35.5, -71.5)], [{"time": [], "wind_speed_10m": [], "wind_direction_10m": []}], AHORA)
    assert grid["speed"] == [None] and grid["dir"] == [None]


def test_cache_fresca_no_repide():
    assert windgrid.necesita_refresco("2026-10-23T11:00:00Z", AHORA) is False
    assert windgrid.necesita_refresco("2026-10-23T05:00:00Z", AHORA) is True
    assert windgrid.necesita_refresco(None, AHORA) is True


def test_la_grilla_cede_ante_el_cupo():
    n = len(windgrid.grid_points())
    assert windgrid.cabe_en_cupo(n, cap=n + 100, gastado=50) is True
    assert windgrid.cabe_en_cupo(n, cap=n + 100, gastado=150) is False
    assert windgrid.cabe_en_cupo(0, cap=100, gastado=0) is False


def test_hora_mas_cercana_con_tiempos_naive():
    """Open-Meteo devuelve `time` sin offset: se lee como UTC, no da siempre el índice 0."""
    assert windgrid._hora_mas_cercana(
        ["2026-10-23T09:00", "2026-10-23T12:00", "2026-10-23T15:00"], AHORA) == 1


def test_grilla_llega_a_la_columna_oeste():
    lons = [lon for _, lon in windgrid.grid_points()]
    assert min(lons) == -75.5  # floor(-75,8) + 0,5: sin floor se perdía la columna
    assert len(windgrid.grid_points()) == 380


def test_cupo_descuenta_la_reserva():
    """La grilla cede ante el cupo menos la reserva fija (OPEN_METEO_RESERVE = 500)."""
    n = len(windgrid.grid_points())
    assert windgrid.cabe_en_cupo(n, cap=1000, gastado=1000 - 500 - n) is True
    assert windgrid.cabe_en_cupo(n, cap=1000, gastado=1000 - 500 - n + 1) is False

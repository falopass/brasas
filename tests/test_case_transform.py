"""Huella de casos: la conversión plano→grados sigue igual tras pasar a shapely.transform.

`LocalPlane.to_deg` es ahora vectorizada (Nx2) porque `shapely.transform` entrega un arreglo;
`shapely.ops.transform` está en desuso desde shapely 2.1 y emitía DeprecationWarning.
"""
from __future__ import annotations

import math
import warnings
from datetime import datetime, timedelta, timezone

import numpy as np
from shapely import transform
from shapely.geometry import Polygon

from backend.cases import LocalPlane, build_timeline


def test_local_plane_to_deg_converts_back_to_degrees():
    plane = LocalPlane(lat0=-35.0, lon0=-71.0)
    xy = np.array([[10.0, -5.0], [0.0, 0.0]])
    kx, ky = 111.320 * math.cos(math.radians(-35.0)), 110.574
    expected = np.array([[10.0 / kx - 71.0, -5.0 / ky - 35.0], [-71.0, -35.0]])
    np.testing.assert_allclose(plane.to_deg(xy), expected, atol=1e-9)


def test_transform_footprint_to_degrees_emits_no_deprecation_warning():
    plane = LocalPlane(lat0=-35.0, lon0=-71.0)
    square_km = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    with warnings.catch_warnings(record=True) as seen:
        warnings.simplefilter("always")
        geom = transform(square_km, plane.to_deg)
    assert not [w for w in seen if issubclass(w.category, DeprecationWarning)]
    np.testing.assert_allclose(geom.exterior.coords[0], plane.to_deg(np.array([[0.0, 0.0]]))[0], atol=1e-9)


# --- build_timeline: motor de reproducción de casos históricos ----------------

def _case(hours: int = 10) -> dict:
    end = datetime(2024, 1, 1, tzinfo=timezone.utc) + timedelta(hours=hours)
    return {"id": "sintetico", "start_utc": "2024-01-01T00:00:00Z",
            "end_utc": end.strftime("%Y-%m-%dT%H:%M:%SZ"), "bbox": [-71.5, -35.5, -70.5, -34.5]}


def _obs(lat: float, lon: float, hour: int, sensor: str = "VIIRS", frp: float = 12.0,
         confidence: str = "alta") -> dict:
    return {"id": f"{sensor}:{hour}:{lat}:{lon}", "lat": lat, "lon": lon,
            "observed_at": f"2024-01-01T{hour:02d}:30:00Z", "frp_mw": frp, "brightness_k": 330.0,
            "confidence": confidence, "sensor": sensor, "satellite": "NOAA-20" if sensor == "VIIRS" else "GOES-19"}


def test_build_timeline_ignora_observaciones_fuera_del_bbox():
    """Un foco fuera del bbox no suma detecciones ni cambia la huella."""
    dentro = _obs(-35.0, -71.0, 0)
    fuera = _obs(-30.0, -65.0, 0)
    solo_dentro = build_timeline(_case(), [dentro])
    con_fuera = build_timeline(_case(), [dentro, fuera])
    assert sum(h["n"] for h in con_fuera["hours"]) == 1
    assert con_fuera["hours"] == solo_dentro["hours"]
    assert con_fuera["frames"] == solo_dentro["frames"]


def test_build_timeline_longitud_de_horas_y_tope_de_frames():
    """hours cubre end-start en horas y frames nunca supera max_frames."""
    caso = _case(hours=100)
    obs = [_obs(-35.0 + 0.001 * h, -71.0, h % 24, frp=10.0) for h in range(20)]
    out = build_timeline(caso, obs, max_frames=10)
    assert len(out["hours"]) == 100
    assert len(out["frames"]) <= 10


def test_build_timeline_huella_y_crecimiento_no_decrecen():
    """footprint_ha es monótona, growth_ha nunca es negativo y vale 0 sin detecciones."""
    obs = [_obs(-35.0, -71.0, 0), _obs(-35.05, -71.05, 2)]
    out = build_timeline(_case(), obs)
    areas = [h["footprint_ha"] for h in out["hours"]]
    assert areas == sorted(areas)
    assert all(h["growth_ha"] >= 0 for h in out["hours"])
    assert out["hours"][1]["growth_ha"] == 0  # hora sin detecciones


def test_build_timeline_detecta_foco_secundario_solo_si_esta_lejos():
    """Un foco a >2*SECONDARY_KM de la huella previa emite 'secundario'; uno cercano no."""
    lejos = build_timeline(_case(), [_obs(-35.0, -71.0, 0), _obs(-35.0, -70.75, 3)])
    cerca = build_timeline(_case(), [_obs(-35.0, -71.0, 0), _obs(-35.02, -71.0, 3)])
    assert any(e["kind"] == "secundario" for e in lejos["events"])
    assert not any(e["kind"] == "secundario" for e in cerca["events"])


def test_build_timeline_emite_evento_de_mayor_crecimiento():
    """El evento 'crecimiento' lleva el inicio de la hora con mayor expansión y su texto."""
    obs = [_obs(-35.0, -71.0, 0)]
    obs += [_obs(-35.0 + 0.01 * i, -71.0 + 0.01 * i, 2) for i in range(4)]
    out = build_timeline(_case(), obs)
    crecimiento = next(e for e in out["events"] if e["kind"] == "crecimiento")
    assert crecimiento["t"] == "2024-01-01T02:00:00Z"
    assert crecimiento["label"].startswith("Mayor expansión de la huella: +")
    assert crecimiento["label"].endswith(" ha en una hora")


def test_build_timeline_counts_separa_sensores_y_nota_presente():
    """counts reparte GOES (ABI) y polares (VIIRS/MODIS) y footprint_note siempre va."""
    obs = [_obs(-35.0, -71.0, 0, sensor="ABI"), _obs(-35.01, -71.0, 0, sensor="VIIRS"),
           _obs(-35.02, -71.0, 1, sensor="MODIS")]
    out = build_timeline(_case(), obs)
    assert out["counts"] == {"goes": 1, "polar": 2}
    assert out["footprint_note"]


def test_build_timeline_sin_observaciones_devuelve_vacios_sin_error():
    """Sin observaciones: horas completas en cero, sin frames ni eventos, conteos en cero."""
    out = build_timeline(_case(), [])
    assert len(out["hours"]) == 10
    assert all(h["n"] == 0 and h["footprint_ha"] == 0 for h in out["hours"])
    assert out["frames"] == [] and out["events"] == []
    assert out["counts"] == {"goes": 0, "polar": 0}


def test_build_timeline_expansion_en_km_y_energia_en_mj():
    """Dos focos separados: la expansión se mide en km desde la segunda hora con huella,
    la energía se acumula donde hay FRP y la primera hora no inventa expansión."""
    obs = [_obs(-35.0, -71.0, 0, frp=100.0), _obs(-35.0, -70.9, 3, frp=200.0)]
    out = build_timeline(_case(), obs)
    hours = out["hours"]
    assert hours[0]["expansion_km"] is None
    assert hours[3]["expansion_km"] > 0
    assert all(h["expansion_km"] is None or h["expansion_km"] >= 0 for h in hours)
    acum = [h["acum_mj"] for h in hours if h["acum_mj"] is not None]
    assert acum == sorted(acum) and all(v > 0 for v in acum)
    assert out["energia_mj"] == acum[-1]
    assert out["expansion_max_km"] == hours[3]["expansion_km"]
    assert any(e["kind"] == "expansion" for e in out["events"])
    assert out["frp_note"]


def test_build_timeline_sin_frp_deja_energia_en_null():
    """Sin FRP en las detecciones: acum_mj y energia_mj quedan null, nunca 0."""
    obs = [_obs(-35.0, -71.0, 0, frp=None), _obs(-35.05, -71.0, 1, frp=None)]
    out = build_timeline(_case(), obs)
    assert all(h["acum_mj"] is None for h in out["hours"])
    assert out["energia_mj"] is None

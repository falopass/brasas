"""Huella de casos: la conversión plano→grados sigue igual tras pasar a shapely.transform.

`LocalPlane.to_deg` es ahora vectorizada (Nx2) porque `shapely.transform` entrega un arreglo;
`shapely.ops.transform` está en desuso desde shapely 2.1 y emitía DeprecationWarning.
"""
from __future__ import annotations

import math
import warnings

import numpy as np
from shapely import transform
from shapely.geometry import Polygon

from backend.cases import LocalPlane


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

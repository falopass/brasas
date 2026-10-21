"""FUEGO-62: el radio de la huella y la resolución declarada del ABI deben coincidir.

El ABI entrega a 2 km en el nadir, pero en Chile central el píxel efectivo mide ~2-3 km.
La huella usa medio píxel de 3 km (1,5 km de radio) y las detecciones declaran ese tamaño,
no el nominal. Los timelines versionados llevan la misma nota.
"""

from __future__ import annotations

import json

from backend import cases


def test_abi_radius_is_half_of_the_declared_pixel():
    assert cases.ABI_RESOLUTION_M == 3000
    assert cases.HALF_PIXEL_KM["ABI"] == cases.ABI_RESOLUTION_M / 2000


def test_goes_observations_declare_the_effective_pixel():
    observations = cases.load_goes(cases.get_case("vina-del-mar-2024"))
    assert observations
    assert {o["resolution_m"] for o in observations} == {cases.ABI_RESOLUTION_M}


def test_footprint_note_explains_the_effective_pixel():
    case = cases.get_case("vina-del-mar-2024")
    note = cases.build_timeline(case, cases.load_goes(case))["footprint_note"]
    assert "1,5 km" in note
    assert "3 km" in note
    assert "2 km" in note


def test_versioned_timelines_are_current():
    paths = sorted((cases.DATA / "cases").glob("*.timeline.json"))
    assert paths
    for path in paths:
        timeline = json.loads(path.read_text(encoding="utf-8"))
        assert timeline["version"] == cases.TIMELINE_VERSION, path.name
        assert "1,5 km" in timeline["footprint_note"], path.name

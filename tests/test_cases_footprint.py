"""Consistencia entre la huella de los casos y el píxel que declaran (FUEGO-62).

El ABI se dibuja con 1,5 km de radio (medio píxel de ~3 km en Chile), no con medio
píxel de los 2.000 m nominales. `resolution_m` debe declarar el píxel usado y la
nota publicada debe nombrarlo. La huella no cambia: esta guarda fija el número que
ya se publica para que la corrección sea solo de lo que se declara.
"""

from __future__ import annotations

from backend import cases

CASE = {
    "start_utc": "2024-02-02T00:00:00Z",
    "end_utc": "2024-02-02T02:00:00Z",
    "bbox": [-72.0, -34.0, -71.0, -33.0],
}
ABI_OBS = {
    "lat": -33.5,
    "lon": -71.5,
    "observed_at": "2024-02-02T00:10:00Z",
    "confidence": "alta",
    "sensor": "ABI",
    "satellite": "GOES-19",
    "frp_mw": 10.0,
}


def test_las_observaciones_goes_declaran_el_pixel_que_se_dibuja():
    """2.000 m era el nominal del nadir; el radio de 1,5 km implica un píxel de 3 km."""
    assert cases.HALF_PIXEL_KM["ABI"] == 1.5
    obs = cases.load_goes(cases.get_case("vina-del-mar-2024"))
    assert obs and {o["resolution_m"] for o in obs} == {3000}


def test_un_pixel_abi_conserva_la_huella_publicada():
    """Un píxel ABI aporta 675 ha (dodecágono de 1,5 km de radio), no las ~300 ha de 1 km."""
    timeline = cases.build_timeline(CASE, [ABI_OBS])
    assert timeline["hours"][0]["footprint_ha"] == 675
    assert timeline["hours"][0]["growth_ha"] == 675


def test_la_nota_nombra_el_pixel_real_del_abi():
    note = cases.build_timeline(CASE, [ABI_OBS])["footprint_note"]
    assert "medio píxel" in note
    assert "1,5 km" in note
    assert "~3 km en Chile" in note

"""ALR-41: el aviso de foco dice en qué comuna y región está, y pluraliza de verdad."""

from __future__ import annotations

from backend import alerts

PLACE = {"id": "p1", "name": "Casa", "lat": -33.02, "lon": -71.55, "radius_km": 60, "comuna_code": 5109, "older_adult": 0}  # Viña del Mar

OBS = {
    "id": "sat-1",
    "source": "firms",
    "sensor": "VIIRS",
    "satellite": "N20",
    "resolution_m": 375,
    "lat": -35.41,
    "lon": -71.97,  # Pencahue, región del Maule
    "frp_mw": 20.0,
    "confidence": "alta",
    "observed_at": "2026-10-18T11:00:00Z",
}

FIRE = {
    "id": "11",
    "name": "El Belloto",
    "status": "en_combate",
    "status_raw": "En combate",
    "lat": -35.41,
    "lon": -71.97,
    "started_at": "2026-10-18T10:00:00Z",
    "area_ha": 12.5,
    "comuna": "Pencahue",
    "region": "Maule",
}


def test_cuerpo_nombra_comuna_y_region():
    payload = alerts.compose(PLACE, OBS | {"comuna": "Pencahue", "region": "Maule"}, 4.4, 180, False, "aviso", None, 0)
    assert "en la comuna de Pencahue" in payload["body"]
    assert "región del Maule" in payload["body"]


def test_sin_comuna_no_inventa_ni_deja_huecos():
    """Un punto en el mar no resuelve comuna: la frase queda como antes, sin «None»."""
    obs = OBS | {"lat": -33.0, "lon": -73.5}
    payload = alerts.compose(PLACE, obs, 200.0, 270, False, "aviso", None, 0)
    assert "None" not in payload["body"]
    assert "comuna de  " not in payload["body"]
    assert not payload["body"].startswith("Detección satelital en la comuna")
    assert "Detección satelital al " in payload["body"]


def test_la_misma_comuna_del_lugar_no_repite_el_nombre():
    """La detección y «Casa» están en Viña del Mar (5109): «en tu misma comuna»."""
    obs = OBS | {"lat": -33.06, "lon": -71.55}
    payload = alerts.compose(PLACE, obs, 4.4, 180, False, "aviso", None, 0)
    assert "en tu misma comuna" in payload["body"]
    assert "Viña del Mar" not in payload["body"]


def test_comuna_se_resuelve_por_el_punto_cuando_no_viene_el_dato():
    payload = alerts.compose(PLACE, OBS, 4.4, 180, False, "aviso", None, 0)
    assert "en la comuna de Pencahue" in payload["body"]


def test_pluralizacion_real_de_detecciones():
    uno = alerts.compose(PLACE, OBS, 4.4, 180, False, "aviso", None, 1)
    tres = alerts.compose(PLACE, OBS, 4.4, 180, False, "aviso", None, 3)
    assert "Hay 1 detección adicional dentro de tu radio." in uno["body"]
    assert "Hay 3 detecciones adicionales dentro de tu radio." in tres["body"]
    assert "detección(es)" not in uno["body"] + tres["body"]


def test_incendio_conaf_con_comuna():
    payload = alerts.compose_official(PLACE, FIRE, 4.4, 180, "aviso")
    assert "en la comuna de Pencahue" in payload["body"]
    assert "región del Maule" in payload["body"]


def test_incendio_conaf_sin_comuna_no_inventa():
    fire = {k: v for k, v in FIRE.items() if k not in ("comuna", "region")}
    fire["lat"], fire["lon"] = -33.0, -73.5  # en el mar: el punto tampoco resuelve
    payload = alerts.compose_official(PLACE, fire, 200.0, 270, "aviso")
    assert "None" not in payload["body"]
    assert "comuna de" not in payload["body"]

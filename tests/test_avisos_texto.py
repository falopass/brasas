"""QA-59: guarda del texto de los avisos.

Recorre por introspección todas las funciones `compose_*` de `backend.alerts` y exige,
para cada una, lo que hoy da por sentado el código: el descargo de que BRASA no es una
autoridad (OFFICIAL_FOOTER), un nivel dentro de {«aviso», «urgente»}, textos presentes
y sin prometer de más (nada de «alerta oficial» en afirmativo ni de «evacue» imperativo
sin la condición de la autoridad).
"""

from __future__ import annotations

import inspect
import re
from datetime import datetime, timezone

import pytest

from backend import alerts
from backend.geo import territory

NOW = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)

PLACE = {"id": "p1", "name": "Casa", "lat": -33.02, "lon": -71.55, "radius_km": 10, "comuna_code": 5109, "older_adult": 0}

OBS = {
    "id": "sat-1",
    "source": "firms",
    "sensor": "VIIRS",
    "satellite": "N20",
    "resolution_m": 375,
    "lat": -33.06,
    "lon": -71.55,
    "frp_mw": 20.0,
    "confidence": "alta",
    "observed_at": "2026-10-18T11:00:00Z",
}

FIRE = {
    "id": "11",
    "name": "El Belloto",
    "status": "en_combate",
    "status_raw": "En combate",
    "lat": -33.06,
    "lon": -71.55,
    "started_at": "2026-10-18T10:00:00Z",
    "area_ha": 12.5,
}

REPORT = {"id": "r1", "kind": "humo", "lat": -33.055, "lon": -71.552, "created_at": "2026-10-18T11:00:00Z"}

FIRE_CONTROLADO = {**FIRE, "status": "controlado", "controlled_at": "2026-10-18T11:30:00Z"}

DMC_ALERT = {
    "id": "urn:oid:2.49.0.0.152.0.2026.10.18.1",
    "kind": "viento",
    "event": "Viento Normal a Moderado",
    "headline": "Viento Normal a Moderado en litoral de la región de Valparaíso",
    "severity": "Moderate",
    "urgency": "Expected",
    "onset": "2026-10-18T11:00:00+00:00",
    "expires": "2026-10-18T18:00:00+00:00",
    "web": "https://example.test/aviso.html",
}

DAILY = {"date": "2026-10-18", "stamp": "2026-10-18T12:00:00Z", "comuna": "Quilpué", "boton_rojo_hours": 6, "level": "alto"}

SMOKE = {"date": "2026-10-18", "stamp": "2026-10-18T12:00:00Z", "comuna": "Quilpué", "pm25": 62.0}

INCIDENT = {"id": "inc-1", "status": "posible", "n_obs": 3, "lat": -33.06, "lon": -71.55,
            "first_seen_at": "2026-10-18T08:00:00Z", "last_seen_at": "2026-10-18T11:30:00Z",
            "sensors": "VIIRS"}

SENAPRED_ALERTA = {"id": "roja1",
                   "title": "Se declara Alerta Roja para la comuna de Angol por incendio forestal",
                   "issued_at": "2026-10-24T11:05:00-03:00",
                   "url": "https://senapred.cl/alertas/roja-angol",
                   "scope": "comuna"}

CASES = {
    "compose": lambda: alerts.compose(PLACE, OBS, 4.4, 180, False, "aviso", None, 0),
    "compose_official": lambda: alerts.compose_official(PLACE, FIRE, 4.4, 180, "aviso"),
    "compose_report": lambda: alerts.compose_report(PLACE, REPORT, 4.4, 180),
    "compose_status_change": lambda: alerts.compose_status_change(PLACE, FIRE, 4.4, 180),
    "compose_dmc": lambda: alerts.compose_dmc(PLACE, DMC_ALERT, NOW),
    "compose_dmc_scar": lambda: alerts.compose_dmc_scar(PLACE, DMC_ALERT, territory().by_code.get(PLACE["comuna_code"]), NOW),
    "compose_daily": lambda: alerts.compose_daily(PLACE, DAILY),
    "compose_smoke": lambda: alerts.compose_smoke(PLACE, SMOKE),
    "compose_approach": lambda: alerts.compose_approach(PLACE, OBS, 4.9, 12.0, 0, False, "aviso", None, INCIDENT),
    "compose_senapred": lambda: alerts.compose_senapred(PLACE, SENAPRED_ALERTA, territory().by_code.get(PLACE["comuna_code"]), NOW),
    # ALR-44: los avisos de «seguir un incendio» se atribuyen al incendio, no a un lugar.
    "compose_follow_confirma": lambda: alerts.compose_follow_confirma(FIRE, INCIDENT),
    "compose_follow_estado": lambda: alerts.compose_follow_estado(FIRE_CONTROLADO, INCIDENT),
    "compose_follow_calor": lambda: alerts.compose_follow_calor(INCIDENT, 2, OBS, "inc:inc-1:calor:sat-1"),
}


def _compose_functions():
    return sorted(name for name, fn in inspect.getmembers(alerts, inspect.isfunction) if name.startswith("compose"))


def test_cada_compose_esta_cubierto_por_la_guarda():
    """Un `compose_*` nuevo sin caso aquí dejaría la guarda ciega: falla hasta tenerlo."""
    assert _compose_functions() == sorted(CASES)


@pytest.mark.parametrize("name", _compose_functions())
def test_footer_descargo_siempre_presente(name):
    """Todo aviso lleva su descargo: «no es una alerta oficial» o «es texto de SENAPRED»."""
    payload = CASES[name]()
    assert payload["footer"] in {alerts.OFFICIAL_FOOTER, alerts.SENAPRED_FOOTER}


@pytest.mark.parametrize("name", _compose_functions())
def test_textos_presentes_y_sin_saltos_dobles(name):
    payload = CASES[name]()
    for key in ("title", "body"):
        assert payload[key].strip(), f"{name}.{key} vacío"
        assert "\n\n" not in payload[key]


@pytest.mark.parametrize("name", _compose_functions())
def test_nivel_dentro_de_los_conocidos(name):
    assert CASES[name]()["level"] in {"aviso", "urgente"}


@pytest.mark.parametrize("name", _compose_functions())
def test_no_promete_de_mas(name):
    """Nada de «alerta oficial» en afirmativo ni «evacue»/«evacúa» sin condición."""
    payload = CASES[name]()
    text = " ".join(str(payload.get(k) or "") for k in ("title", "body", "footer"))
    for m in re.finditer("alerta oficial", text, re.IGNORECASE):
        if re.match(r"\s+de\s+senapred\b", text[m.end():], re.IGNORECASE):
            continue  # «alerta oficial de SENAPRED» atribuye a la autoridad, no es auto-claim
        assert "no" in text[max(0, m.start() - 15) : m.start()].lower(), f"{name}: «alerta oficial» sin negación cerca"
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if re.search(r"\bevacu", sentence, re.IGNORECASE):
            assert re.search(r"\bsi\b", sentence, re.IGNORECASE), f"{name}: evacuación en imperativo sin condición"


@pytest.mark.parametrize("name", _compose_functions())
def test_el_aviso_se_atribuye_al_lugar(name):
    payload = CASES[name]()
    if payload.get("kind") == "seguimiento":
        return  # «seguir un incendio» no cuelga de un lugar: su atribución es el incendio
    assert payload["place"]["id"] == PLACE["id"]

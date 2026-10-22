"""Boletín radial (IDEA-05): plantillas por reglas, tope de palabras y fuentes.

Los fixtures son respuestas fijas de /api/risk, /api/official-fires y /api/incidents:
ninguna prueba toca la red. `build_block` recibe None en la fuente que «no respondió».

La última prueba es de contrato: pega contra la app real (TestClient) y comprueba que
los endpoints sigan publicando, uno por uno, los campos que boletin.py lee. Si la API
renombra un campo, esta prueba falla antes de que el boletín salga al aire vacío.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "local"))
import boletin  # noqa: E402

HORA = "08:30"
FUENTE = "Fuente: CONAF (Botón Rojo e incendios) y Open-Meteo vía BRASA al 08:30."
AHORA = datetime(2026, 10, 19, 12, 0, tzinfo=ZoneInfo("America/Santiago"))

# Región mínima de prueba: «Maule» con dos comunas reales (Curicó 7301, Talca 7101).
REGION = {"code": 7, "name": "Maule", "fold": "maule", "comunas": {7301, 7101}}
REGIONES = [REGION, {"code": 8, "name": "Biobío", "fold": "biobio", "comunas": {8101}}]
COMUNA_REGION = {"curico": 7, "curicó": 7, "talca": 7, "concepcion": 8, "concepción": 8}
COMUNA_NOMBRES = {7301: "Curicó", 7101: "Talca", 8101: "Concepción"}

RISK = {
    "date": "2026-10-19",
    "comunas": {
        "7301": {"level": "alto", "level_combined": "alto"},
        "7101": {"level": "moderado", "level_combined": "alto"},
        "8101": {"level": "bajo", "level_combined": "bajo"},
    },
    "boton_rojo": {},
}
FIRES = [
    {"id": "1", "name": "EL BELLOTO", "status": "confirmado", "area_ha": 35.5, "comuna": "Curicó", "region": "Del Maule"},
    {"id": "2", "name": "VIEJO", "status": "extinguido", "area_ha": 10.0, "comuna": "Talca", "region": "Del Maule"},
    {"id": "3", "name": "OTRO", "status": "confirmado", "area_ha": 5.0, "comuna": "Concepción", "region": "Del Biobío"},
]
INCIDENTS = [
    {"id": "aaaabbbbcccc", "status": "posible", "comuna": "Talca", "region": "Maule"},
    {"id": "dddddddddddd", "status": "confirmado", "comuna": "Curicó", "region": "Maule"},
]

# Comparador semanal por comuna, tal como llega de /api/risk/{comuna}/trend?weeks=1:
# el boletín solo lee `target_date` (la fila del día, RISK["date"]) y `previous`
# (el nivel que se pronosticó hace una semana para ese día).
TRENDS = {
    7301: {"rows": [{"target_date": "2026-10-19", "previous": "moderado"}]},
    7101: {"rows": [{"target_date": "2026-10-19", "previous": "alto"}]},
}

# Un aviso DMC tal como llega en risk["dmc"]: vigente entre las 09:00 y las 18:00 del
# día del fixture (AHORA = 12:00).
AVISO_VIENTO = {
    "kind": "viento",
    "label": "Viento",
    "event": "Viento Normal a Moderado",
    "headline": "Viento en el valle central",
    "severity": "Moderate",
    "urgency": "Expected",
    "onset": "2026-10-19T09:00:00-03:00",
    "expires": "2026-10-19T18:00:00-03:00",
    "web": "https://archivos.meteochile.gob.cl/portaldmc/AAA/doc/evento.html",
}


def build(risk=RISK, fires=FIRES, incidents=INCIDENTS, region=REGION, ahora=AHORA, trends=None):
    return boletin.build_block(
        region, risk, fires, incidents, HORA, COMUNA_REGION, REGIONES, comuna_nombres=COMUNA_NOMBRES, ahora=ahora, trends=trends
    )


def test_region_sin_incendios_activos() -> None:
    b = build(fires=[])
    assert "riesgo" in b["texto"].lower() or "condiciones" in b["texto"].lower()
    assert "alto" in b["texto"] and "2 comunas" in b["texto"]
    assert "CONAF no informa incendios activos" in b["texto"]
    assert "incendio activo:" not in b["texto"]
    assert b["palabras"] <= boletin.MAX_PALABRAS


def test_region_con_boton_rojo() -> None:
    risk = {**RISK, "boton_rojo": {"7301": {"hours": 4, "area_ha": 1500, "proportion": 0.05}}}
    b = build(risk=risk)
    assert "Botón Rojo en 1 comuna" in b["texto"]
    assert b["palabras"] <= boletin.MAX_PALABRAS


def test_incendios_con_comuna_y_hectareas() -> None:
    b = build()
    assert "1 incendio activo" in b["texto"]
    assert "Curicó (35.5 ha)" in b["texto"]
    # El extinguido y el de otra región no entran al bloque.
    assert "VIEJO" not in b["texto"] and "Concepción" not in b["texto"]


def test_fuente_caida_no_rompe_el_bloque() -> None:
    b = build(fires=None)
    assert "sin datos de conaf en este momento" in b["texto"].lower()
    assert "CONAF (incendios)" not in b["fuentes"]  # una fuente caída no se declara como fuente
    assert "alto" in b["texto"]  # el resto del bloque sigue con sus cifras
    assert b["palabras"] <= boletin.MAX_PALABRAS

    b = build(risk=None)
    assert "sin datos de riesgo" in b["texto"].lower()

    b = build(incidents=None)
    assert "sin datos del monitoreo satelital" in b["texto"].lower()


def test_toda_cifra_termina_con_fuente_y_tope_de_palabras() -> None:
    for b in (build(), build(fires=None), build(fires=None, incidents=None)):
        assert b["texto"].endswith(FUENTE)
        assert b["fuentes"], "el bloque debe declarar de dónde salen sus cifras"
        assert b["palabras"] == len(b["texto"].split())
        assert b["palabras"] <= boletin.MAX_PALABRAS


def test_focos_satelitales_sin_confirmar_se_mencionan() -> None:
    b = build()
    assert "1 foco de calor sin confirmar" in b["texto"]
    # El incidente «confirmado» lo cubre CONAF, no se repite como foco satelital.
    assert "2 focos" not in b["texto"]


def test_region_desconocida_en_datos_no_se_atribuye() -> None:
    fires = [
        {"id": "9", "name": "LEJOS", "status": "confirmado", "area_ha": 90.0, "comuna": "Comuna Inexistente", "region": "Región Inventada"}
    ]
    b = build(fires=fires)
    assert "LEJOS" not in b["texto"]


def test_aviso_dmc_vigente_en_la_region_se_menciona() -> None:
    # El mismo aviso cubre dos comunas de la región: se nombra una sola vez.
    risk = {**RISK, "dmc": {"7301": [AVISO_VIENTO], "7101": [AVISO_VIENTO]}}
    b = build(risk=risk)
    assert "aviso oficial de viento" in b["texto"]
    assert "Curicó y Talca" in b["texto"]
    assert "hasta las 18:00" in b["texto"]
    assert "DMC (avisos oficiales)" in b["fuentes"]
    assert b["palabras"] <= boletin.MAX_PALABRAS


@pytest.mark.parametrize(
    "dmc",
    [
        {"8101": [AVISO_VIENTO]},                                              # Concepción, Biobío
        {"7301": [{**AVISO_VIENTO, "expires": "2026-10-19T10:00:00-03:00"}]},  # venció a las 10:00
    ],
)
def test_aviso_dmc_que_no_rige_en_la_region_no_se_menciona(dmc) -> None:
    b = build(risk={**RISK, "dmc": dmc})
    assert "aviso oficial" not in b["texto"]
    assert "DMC (avisos oficiales)" not in b["fuentes"]


def test_aviso_dmc_tiene_prioridad_sobre_focos_al_recortar(monkeypatch) -> None:
    # Con un tope más bajo, el detalle satelital sale primero y el aviso DMC queda.
    monkeypatch.setattr(boletin, "MAX_PALABRAS", 60)
    risk = {**RISK, "dmc": {"7301": [AVISO_VIENTO]}}
    b = build(risk=risk)
    assert "aviso oficial de viento" in b["texto"]
    assert "foco" not in b["texto"]
    assert b["palabras"] <= 60


def test_tendencia_disponible_compara_con_la_semana_pasada() -> None:
    b = build(trends=TRENDS, fires=[], incidents=[])
    assert "El pronóstico de la semana pasada para hoy llegaba a alto en 1 comuna." in b["texto"]
    assert "Sin comparación" not in b["texto"]
    assert b["comparacion"]["texto"].startswith("El pronóstico de la semana pasada")
    assert b["comparacion"]["fuente"]
    assert "Open-Meteo vía BRASA (semana pasada)" in b["fuentes"]
    assert b["palabras"] <= boletin.MAX_PALABRAS


def test_tendencia_ausente_dice_sin_comparacion() -> None:
    for trends in (None, {7301: None, 7101: None}, {7301: {"rows": []}, 7101: {"rows": [{"target_date": "2026-10-19", "previous": None}]}}):
        b = build(trends=trends, fires=[], incidents=[])
        assert "Sin comparación esta semana." in b["texto"]
        assert b["comparacion"]["texto"] == "Sin comparación esta semana."
        assert b["comparacion"]["fuente"] is None
        assert "Open-Meteo vía BRASA (semana pasada)" not in b["fuentes"]
        assert b["palabras"] <= boletin.MAX_PALABRAS


def test_region_sin_comunas_no_rompe_la_comparacion() -> None:
    region = {**REGION, "comunas": set()}
    b = build(region=region, trends={})
    assert "Sin comparación esta semana." in b["texto"]
    assert b["preparate"] is None  # sin nivel regional no hay consejo que justificar
    assert b["palabras"] <= boletin.MAX_PALABRAS


def test_recorte_no_expulsa_el_boton_rojo(monkeypatch) -> None:
    # Apretando el tope salen primero «prepárate» y la comparación; el Botón Rojo aguanta.
    monkeypatch.setattr(boletin, "MAX_PALABRAS", 50)
    risk = {**RISK, "boton_rojo": {"7301": {"hours": 4, "area_ha": 1500, "proportion": 0.05}}}
    b = build(risk=risk, trends=TRENDS)
    assert "Botón Rojo" in b["texto"]
    assert "semana pasada" not in b["texto"]
    assert "Prepárate" not in b["texto"]
    assert b["palabras"] <= 50
    # El campo JSON conserva la comparación aunque el texto al aire la haya recortado.
    assert b["comparacion"]["texto"].startswith("El pronóstico de la semana pasada")


def test_preparate_solo_cuando_el_nivel_lo_justifica() -> None:
    b = build(fires=[], incidents=[])  # nivel máximo «alto»
    assert "Prepárate hoy" in b["texto"]
    assert b["preparate"]["texto"].startswith("Prepárate hoy")
    assert b["preparate"]["fuente"]

    moderado = {**RISK, "comunas": {"7301": {"level": "moderado", "level_combined": "moderado"}}}
    b = build(risk=moderado, fires=[], incidents=[])
    assert "Prepárate" not in b["texto"]
    assert b["preparate"] is None


def test_contrato_campos_que_boletin_lee(make_client) -> None:
    """La API pública debe seguir publicando cada campo que boletin.py lee.

    Se siembran datos mínimos (riesgo, Botón Rojo, incendio CONAF e incidente
    satelital) y se recorre la respuesta real con la misma estructura que usa el
    script: comunas de /api/risk por código, incendios e incidentes por región.
    Cada campo exigido se declara con el motivo por el que el boletín lo necesita.
    Si una lista viniera vacía se anota y no se falla por eso; solo se salta la
    prueba si las tres fuentes llegan sin datos.
    """
    from backend import incidents
    from tests.test_incidents import obs

    now = datetime.now(timezone.utc).replace(microsecond=0)
    stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    hoy = now.astimezone(ZoneInfo("America/Santiago")).date().isoformat()

    with make_client(GOES_ENABLED="0") as client:
        db = client.app.state.services.db
        db.execute(
            "INSERT INTO risk_daily(comuna_code, date, level, score, hours_3of3, hours_2of3, tmax, rhmin, "
            "windmax, gustmax, level_combined, fwi, fwi_level, reasons, computed_at) "
            "VALUES (7301, ?, 'alto', 60, 3, 5, 33.0, 20.0, 35.0, 50.0, 'alto', NULL, NULL, '[]', ?)",
            (hoy, stamp),
        )
        db.execute(
            "INSERT INTO boton_rojo(comuna_code, date, hours, area_ha, proportion, fetched_at) VALUES (7301, ?, 4, 1500.0, 0.05, ?)",
            (hoy, stamp),
        )
        db.execute(
            "INSERT INTO official_fires(id, name, status, status_raw, started_at, controlled_at, "
            "extinguished_at, area_ha, lat, lon, comuna, region, ambito, fuel, first_fetched_at, fetched_at) "
            "VALUES ('t-1', 'EL BELLOTO', 'confirmado', 'En combate', ?, NULL, NULL, 35.5, -34.98, -71.23, "
            "'Curicó', 'Del Maule', 'CONAF', 'Pastizal', ?, ?)",
            (stamp, stamp, stamp),
        )
        incidents.update(db, [obs(db, "t-i1", -33.5, -70.8, when=now)], now)

        risk = client.get("/api/risk").json()
        fires = client.get("/api/official-fires").json()
        incidents_payload = client.get("/api/incidents").json()
        trend = client.get("/api/risk/7301/trend?weeks=1").json()

    vacias = []
    if not risk.get("comunas"):
        vacias.append("/api/risk: comunas")
    if not fires.get("fires"):
        vacias.append("/api/official-fires: fires")
    if not incidents_payload.get("incidents"):
        vacias.append("/api/incidents: incidents")
    if len(vacias) == 3:
        pytest.skip("Las tres fuentes respondieron sin datos; no hay contrato que comprobar")
    if vacias:
        print("Listas vacías (se anota, no se falla): " + ", ".join(vacias))

    # /api/risk — el script hace int(code) para cruzar cada comuna con su región,
    # y elige row["level_combined"] o row["level"] para el nivel que se lee al aire.
    for code, row in (risk.get("comunas") or {}).items():
        int(code)
        assert "level_combined" in row, "sin level_combined el bloque no puede elegir el nivel combinado"
        assert "level" in row, "sin level no hay respaldo 30-30-30 cuando falta el FWI"
    # /api/risk — build_block cuenta las claves de boton_rojo cuyo código cae en la región.
    for code in risk.get("boton_rojo") or {}:
        assert str(code).isdigit(), "las claves de boton_rojo deben ser códigos de comuna enteros"
    # /api/risk — de cada aviso DMC el script lee su tipo (label, con kind de respaldo)
    # y sus instantes onset/expires para filtrar los vigentes y leer el vencimiento.
    for code, avisos in (risk.get("dmc") or {}).items():
        int(code)
        for a in avisos or []:
            assert "label" in a or "kind" in a, "sin label ni kind el aviso no puede nombrar su tipo"
            assert "onset" in a, "onset marca desde cuándo rige el aviso"
            assert "expires" in a, "expires es el vencimiento que se lee al aire"

    # /api/official-fires — por cada incendio el script lee, en este orden:
    for f in fires.get("fires") or []:
        assert "status" in f, "status filtra los activos (== 'confirmado')"
        assert "comuna" in f, "comuna atribuye el incendio a una región antes que el texto de región"
        assert "region" in f, "region es el respaldo de _region_de cuando la comuna no se reconoce"
        assert "area_ha" in f, "area_ha ordena el detalle y arma '(N ha)'"
        assert "name" in f, "name es el nombre del lugar cuando falta la comuna"

    # /api/incidents — por cada incidente el script lee:
    for i in incidents_payload.get("incidents") or []:
        assert "status" in i, "status filtra los focos sin confirmar (anomalia/posible/reportado)"
        assert "comuna" in i, "comuna atribuye el foco a una región"
        assert "region" in i, "region es el respaldo de _region_de"

    # /api/risk/{comuna}/trend — de cada fila el script lee `target_date` para
    # encontrar la del día del boletín y `previous` para el nivel de hace una semana.
    assert "rows" in trend, "sin rows no hay filas que comparar"
    for r in trend.get("rows") or []:
        assert "target_date" in r, "target_date ubica la fila del día del boletín"
        assert "previous" in r, "previous es el nivel pronosticado hace una semana"

    # Además del contrato de campos: el bloque se arma con los datos reales sin romperse.
    regiones, comuna_region, comuna_nombres = boletin.load_territory()
    maule = next(r for r in regiones if r["code"] == 7)
    b = boletin.build_block(
        maule,
        risk,
        fires.get("fires"),
        incidents_payload.get("incidents"),
        HORA,
        comuna_region,
        regiones,
        comuna_nombres=comuna_nombres,
        trends={7301: trend},
    )
    assert b["palabras"] <= boletin.MAX_PALABRAS

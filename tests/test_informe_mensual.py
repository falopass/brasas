"""Informe mensual (IDEA-04): agregación por región, cobertura de la API y fuentes.

Los fixtures son respuestas fijas de /api/official-fires, /api/incidents,
/api/opendata/boton-rojo.json, del campo `dmc` de /api/risk y de
/api/risk/<comuna>/trend?weeks=1: ninguna prueba toca la red. `build_block`
recibe None en la fuente que «no respondió».
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "local"))
import informe_mensual as informe  # noqa: E402

HOY = date(2026, 10, 19)
MES = informe.month_info("2026-10", HOY)  # mes en curso: la API cubre desde el 5
MES_PASADO = informe.month_info("2026-08", HOY)  # mes ya cerrado y fuera de la ventana
CORTE = "19 de octubre a las 18:30"

REGION = {"code": 7, "name": "Maule", "fold": "maule", "comunas": {7301, 7101}}
REGIONES = [REGION, {"code": 8, "name": "Biobío", "fold": "biobio", "comunas": {8101}}]
COMUNA_REGION = {"curico": 7, "curicó": 7, "talca": 7, "concepcion": 8, "concepción": 8}

FIRES = [
    {
        "id": "1",
        "name": "EL BELLOTO",
        "status": "confirmado",
        "area_ha": 35.5,
        "started_at": "2026-10-08T15:00:00Z",
        "comuna": "Curicó",
        "region": "Del Maule",
    },
    {
        "id": "2",
        "name": "VIEJO",
        "status": "extinguido",
        "area_ha": 10.0,
        "started_at": "2026-10-10T15:00:00Z",
        "extinguished_at": "2026-10-12T15:00:00Z",
        "comuna": "Talca",
        "region": "Del Maule",
    },
    {
        "id": "3",
        "name": "OTRA REGION",
        "status": "confirmado",
        "area_ha": 5.0,
        "started_at": "2026-10-09T15:00:00Z",
        "comuna": "Concepción",
        "region": "Del Biobío",
    },
    {
        "id": "4",
        "name": "DEL MES ANTERIOR",
        "status": "extinguido",
        "area_ha": 99.0,
        "started_at": "2026-09-20T15:00:00Z",
        "comuna": "Curicó",
        "region": "Del Maule",
    },
]
INCIDENTS = [
    {
        "id": "aaaabbbbcccc",
        "status": "confirmado",
        "first_seen_at": "2026-10-06T10:00:00Z",
        "last_seen_at": "2026-10-07T10:00:00Z",
        "comuna_code": 7301,
        "comuna": "Curicó",
        "region": "Maule",
        "sensors": ["ABI", "VIIRS"],
    },
    {
        "id": "bbbbccccdddd",
        "status": "posible",
        "first_seen_at": "2026-10-18T10:00:00Z",
        "last_seen_at": "2026-10-19T10:00:00Z",
        "comuna_code": 7101,
        "comuna": "Talca",
        "region": "Maule",
        "sensors": ["ABI"],
    },
    {
        "id": "ccccddddeeee",
        "status": "controlado",
        "first_seen_at": "2026-10-15T10:00:00Z",
        "last_seen_at": "2026-10-16T10:00:00Z",
        "comuna_code": 7301,
        "comuna": "Curicó",
        "region": "Maule",
        "sensors": ["VIIRS"],
    },
    {
        "id": "ddddeeeeffff",
        "status": "posible",
        "first_seen_at": "2026-10-17T10:00:00Z",
        "last_seen_at": "2026-10-17T10:00:00Z",
        "comuna_code": 8101,
        "comuna": "Concepción",
        "region": "Biobío",
        "sensors": ["ABI"],
    },
]
BR = [
    {"comuna_code": 7301, "comuna": "Curicó", "region": "Maule", "date": "2026-10-08", "hours": 4},
    {"comuna_code": 7101, "comuna": "Talca", "region": "Maule", "date": "2026-10-08", "hours": 2},
    {"comuna_code": 7301, "comuna": "Curicó", "region": "Maule", "date": "2026-10-12", "hours": 6},
    {"comuna_code": 8101, "comuna": "Concepción", "region": "Biobío", "date": "2026-10-09", "hours": 4},
    {"comuna_code": 7301, "comuna": "Curicó", "region": "Maule", "date": "2026-10-20", "hours": 4},
    {"comuna_code": 7301, "comuna": "Curicó", "region": "Maule", "date": "2026-09-30", "hours": 4},
]
DMC = {
    "7301": [
        {
            "kind": "viento",
            "label": "Viento",
            "headline": "Aviso de viento",
            "onset": "2026-10-15T09:00:00-03:00",
            "expires": "2026-10-20T21:00:00-03:00",
            "web": "https://archivos.meteochile.gob.cl/av1",
        }
    ],
    "7101": [
        {
            "kind": "viento",
            "label": "Viento",
            "headline": "Aviso de viento",
            "onset": "2026-10-15T09:00:00-03:00",
            "expires": "2026-10-20T21:00:00-03:00",
            "web": "https://archivos.meteochile.gob.cl/av1",
        },
        {
            "kind": "calor",
            "label": "Calor extremo",
            "headline": "Aviso de calor extremo",
            "onset": "2026-10-17T09:00:00-03:00",
            "expires": "2026-10-19T21:00:00-03:00",
            "web": "https://archivos.meteochile.gob.cl/av2",
        },
    ],
}


# Respuestas de /api/risk/<comuna>/trend?weeks=1: el pronóstico vigente de cada día
# contra el emitido siete días antes para ese mismo día.
TREND = {
    7301: {  # Curicó: el nivel más alto de la semana sube (moderado → alto)
        "weeks": 1,
        "rows": [
            {
                "target_date": "2026-10-19",
                "current": "alto",
                "previous": "moderado",
                "change": "sube",
                "missing": None,
                "previous_at": "2026-10-12",
            },
            {
                "target_date": "2026-10-20",
                "current": "alto",
                "previous": "moderado",
                "change": "sube",
                "missing": None,
                "previous_at": "2026-10-13",
            },
        ],
        "summary": {"sube": 2, "baja": 0, "igual": 0, "sin_anterior": 0, "sin_hoy": 0},
        "snapshots_from": "2026-10-12",
    },
    7101: {  # Talca: baja (alto → moderado)
        "weeks": 1,
        "rows": [
            {
                "target_date": "2026-10-19",
                "current": "moderado",
                "previous": "alto",
                "change": "baja",
                "missing": None,
                "previous_at": "2026-10-12",
            }
        ],
        "summary": {"sube": 0, "baja": 1, "igual": 0, "sin_anterior": 0, "sin_hoy": 0},
        "snapshots_from": "2026-10-12",
    },
}
# Hay pronóstico vigente pero ninguna foto de hace siete días: la ventana no alcanza.
TREND_SIN_PREVIO = {
    code: {
        "weeks": 1,
        "rows": [
            {
                "target_date": "2026-10-19",
                "current": "alto",
                "previous": None,
                "change": "sin_anterior",
                "missing": "semana_pasada",
                "previous_at": None,
            }
        ],
        "summary": {"sube": 0, "baja": 0, "igual": 0, "sin_anterior": 1, "sin_hoy": 0},
        "snapshots_from": None,
    }
    for code in REGION["comunas"]
}


def build(fires=FIRES, incidents=INCIDENTS, br=BR, dmc=DMC, region=REGION, mes=MES, trend=None):
    return informe.build_block(region, mes, fires, incidents, br, dmc, CORTE, COMUNA_REGION, REGIONES, trend=trend)


def test_agregacion_por_region() -> None:
    t = build()["texto"]
    # Solo los dos incendios del Maule iniciados en el mes: ni el de otra región ni el de septiembre.
    assert "al menos 2 incendios y 45.5 hectáreas" in t
    # Solo los tres incidentes del Maule con primera detección en el mes.
    assert "al menos 3 focos de calor" in t
    assert "1 confirmado por CONAF" in t and "1 controlado o extinguido" in t and "1 sin confirmar" in t
    assert "ABI" in t and "VIIRS" in t  # la fuente de cada incidente: sus sensores


def test_mes_vacio() -> None:
    t = build(fires=[], incidents=[], br=[], dmc={})["texto"]
    assert "CONAF no informa incendios iniciados en octubre de 2026" in t
    assert "Sin datos del Botón Rojo" in t
    assert "no tiene avisos de viento ni calor vigentes" in t
    assert "BRASA no agrupó focos de calor nuevos" in t


def test_fuente_caida_lo_dice_y_no_rompe() -> None:
    b = build(fires=None)
    assert "sin datos de incendios conaf en este momento" in b["texto"].lower()
    assert "CONAF (incendios)" not in b["fuentes"]
    assert "3 focos de calor" in b["texto"]  # el resto del bloque sigue con sus cifras

    b = build(br=None)
    assert "sin datos del botón rojo" in b["texto"].lower()
    b = build(dmc=None)
    assert "sin datos de la dmc" in b["texto"].lower()
    b = build(incidents=None)
    assert "sin datos del monitoreo satelital" in b["texto"].lower()


def test_dias_boton_rojo_dedup_y_mes() -> None:
    t = build()["texto"]
    # Dos comunas el día 8 cuentan un solo día; el 9 es Biobío, el 30/9 es otro mes, el 20 es futuro.
    assert "Botón Rojo en 2 días del mes" in t
    assert "los días 8 y 12" in t
    # El día pronosticado (20) no suma al conteo: va al cierre de «esta semana».
    assert "pronostica Botón Rojo" in t and "los días 20" in t


def test_cierre_sin_pronostico_boton_rojo() -> None:
    t = build(br=[p for p in BR if p["date"] != "2026-10-20"])["texto"]
    assert "pronostica Botón Rojo" not in t
    assert "132" in t


def test_mes_pasado_fuera_de_la_ventana() -> None:
    t = build(mes=MES_PASADO)["texto"]
    assert "Sin datos de incendios CONAF para agosto de 2026" in t
    assert "Sin datos de incidentes BRASA para agosto de 2026" in t
    assert "el registro público conserva desde el 30 de septiembre" in t
    assert "sin datos de la DMC para agosto de 2026" in t
    # Ningún número del mes en curso se cuela en un mes sin cobertura.
    assert "hectáreas" not in t and "focos de calor" not in t


def test_fuentes_y_corte_al_pie() -> None:
    b = build()
    assert b["texto"].endswith(f"al corte del {CORTE}.")
    assert b["fuentes"] == ["CONAF (incendios)", "CONAF (Botón Rojo)", "DMC (avisos CAP)", "BRASA (NASA FIRMS y NOAA GOES)"]


def test_avisos_dmc_dedup_entre_comunas() -> None:
    t = build()["texto"]
    # El mismo aviso de viento en dos comunas cuenta una sola vez.
    assert "La DMC emitió 2 avisos" in t
    assert "1 de calor extremo y 1 de viento" in t


def test_comparacion_semanal() -> None:
    b = build(trend=TREND)
    t = b["texto"]
    assert "Cómo viene la semana" in t
    assert "el nivel más alto pronosticado es alto" in t
    assert "sube de nivel en 1 comuna" in t and "baja en 1 comuna" in t
    c = b["comparacion"]
    assert c["fuente"] == "BRASA (comparador de pronósticos)" and c["corte"] == CORTE
    assert (c["suben"], c["bajan"], c["se_mantienen"]) == (1, 1, 0)
    assert b["sin_comparacion"] is None
    assert "BRASA (comparador de pronósticos)" in b["fuentes"]


def test_sin_comparacion_cuando_la_ventana_no_alcanza() -> None:
    b = build(trend=TREND_SIN_PREVIO)
    assert b["comparacion"] is None
    assert "semana pasada" in b["sin_comparacion"]
    # Lo que sí hay se dice igual: el nivel más alto vigente y por qué no se compara.
    assert "el nivel más alto pronosticado es alto" in b["texto"]
    assert "no hay pronóstico de la semana pasada guardado" in b["texto"]


def test_tendencia_ausente_o_sin_comunas() -> None:
    b = build(trend=None)
    assert b["comparacion"] is None and b["sin_comparacion"]
    assert "sin datos del comparador semanal" in b["texto"].lower()
    assert "BRASA (comparador de pronósticos)" not in b["fuentes"]

    b = build(region={"code": 99, "name": "Sin comunas", "fold": "sin comunas", "comunas": set()}, trend=TREND)
    assert b["comparacion"] is None
    assert "comunas" in b["sin_comparacion"]


def test_mes_parcial_compara_la_semana_no_el_mes() -> None:
    # El mes informado está fuera de la ventana de 14 días, pero «Cómo viene la
    # semana» habla de la semana en curso: la comparación sigue siendo honesta.
    b = build(mes=MES_PASADO, trend=TREND)
    assert b["comparacion"] is not None
    assert "Cómo viene la semana" in b["texto"]
    assert b["comparacion"]["nivel_mas_alto"] == "alto"

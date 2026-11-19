"""Vialidad: parseo de emergencias viales y filtro por distancia para la ficha del incendio."""

from __future__ import annotations

import pytest

from backend.providers import vialidad


def feature(attrs, *, x=-70.0, y=-33.0):
    return {"attributes": attrs, "geometry": {"x": x, "y": y}}


def attrs(**over):
    base = {
        "OBJECTID": 1,
        "GlobalID": "{TEST}",
        "CORRELATIVO": 10,
        "NOMBRE_CAMINO": "Ruta 5 Sur",
        "ROL": "5S",
        "KM_INICIO_SEGMENTO": 120,
        "KM_FIN_SEGMENTO": 120.5,
        "RESUMEN_EMERGENCIA": "socavón",
        "DESCRIPCION_DETALLADA": "transito interrumpido",
        "TRANSITO": "No Operativo",
        "RESTRICCION": None,
        "OPERATIVIDAD": "No Operativo",
        "NIVEL_DE_GRAVEDAD": "Moderado",
        "REGION": "08",
        "FECHA_EMERGENCIA": 1786726491000,
        "FECHA_INGRESO": 1786726380000,
        "TIPO": "ACTUALIZACION",
    }
    base.update(over)
    return base


def test_parse_convierte_geo_y_fechas_sin_inventar():
    items = vialidad.parse({"features": [feature(attrs(), x=-70.01, y=-33.02)]})
    assert len(items) == 1
    item = items[0]
    assert item["road"] == "Ruta 5 Sur" and item["rol"] == "5S"
    assert item["km_inicio"] == 120 and item["km_fin"] == pytest.approx(120.5)
    assert item["transito"] == "No Operativo" and item["gravedad"] == "Moderado"
    assert item["fecha_emergencia"] == "2026-08-14T16:54:51Z"
    assert item["lat"] == pytest.approx(-33.02) and item["lon"] == pytest.approx(-70.01)


def test_parse_deduplica_misma_emergencia_con_distinto_globalid():
    items = vialidad.parse({"features": [
        feature(attrs(), x=-70.01, y=-33.02),
        feature(attrs(OBJECTID=2, GlobalID="{DUP}", FECHA_INGRESO=1786726500000), x=-70.01, y=-33.02),
    ]})
    assert len(items) == 1
    assert items[0]["id"] == "{TEST}"
    assert items[0]["fecha_ingreso"] == "2026-08-14T16:55:00Z"


def test_parse_omite_features_sin_geometria_o_con_fecha_ilegible():
    items = vialidad.parse({"features": [
        {"attributes": attrs(), "geometry": {}},
        feature(attrs(FECHA_EMERGENCIA="no-date", FECHA_INGRESO=None), x=-70.0, y=-33.0),
    ]})
    assert len(items) == 1
    assert items[0]["fecha_emergencia"] is None and items[0]["fecha_ingreso"] is None


def test_nearby_filtra_radio_y_afectacion_de_transito():
    items = vialidad.parse({"features": [
        feature(attrs(), x=-70.01, y=-33.0),                    # ~1 km, cortado
        feature(attrs(OBJECTID=2, GlobalID="{B}", TRANSITO="Operativo", RESTRICCION=None, OPERATIVIDAD=None), x=-70.005, y=-33.0),  # ~0,5 km, no afecta
        feature(attrs(OBJECTID=3, GlobalID="{C}", TRANSITO="Parcialmente Operativo", RESTRICCION="Velocidad Restringida"), x=-70.02, y=-33.0),  # ~2 km
        feature(attrs(OBJECTID=4, GlobalID="{D}"), x=-71.0, y=-33.0),  # ~92 km
    ]})
    near = vialidad.nearby(items, -33.0, -70.0, radius_km=30, limit=8)
    assert [item["id"] for item in near] == ["{TEST}", "{C}"]
    assert near[0]["distance_km"] == pytest.approx(1.1, abs=0.2)
    assert near[1]["restriccion"] == "Velocidad Restringida"


def test_nearby_respeta_limite_y_radio():
    items = vialidad.parse({"features": [
        feature(attrs(OBJECTID=i, GlobalID=f"{{{i}}}"), x=-70.001 * i, y=-33.0) for i in range(1, 12)
    ]})
    near = vialidad.nearby(items, -33.0, -70.0, radius_km=5, limit=3)
    assert len(near) == 3
    assert all(item["distance_km"] <= 5 for item in near)

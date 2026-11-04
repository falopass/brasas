"""CALIDAD-OBS y RISK-09: latencias de la última hora y concordancia del índice con CONAF.

La vista `#/calidad` lee `GET /api/observability/routes` y `GET /api/observability/concordancia`.
Este archivo fija los conteos del resumen en vivo y que, con la base vacía, las tasas salen en
None. No inventa un porcentaje ni divide por cero.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from backend.geo import territory

ROOT = Path(__file__).resolve().parents[1]
A = territory().by_code[5101]  # Valparaíso


def _risk(db, code, date, level, combined, fwi):
    db.execute(
        "INSERT INTO risk_daily(comuna_code, date, level, score, hours_3of3, hours_2of3, "
        "level_combined, fwi_level, computed_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (code, date, level, 50, 0, 0, combined, fwi, "2026-01-20T00:00:00Z"),
    )


def _fire(db, fid, comuna, started):
    db.execute(
        "INSERT INTO official_fires(id, name, status, status_raw, started_at, lat, lon, "
        "comuna, region, first_fetched_at, fetched_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (fid, fid, "confirmado", "En combate", started, -33.0, -71.6, comuna, "Valparaíso",
         "2026-01-20T00:00:00Z", "2026-01-20T00:00:00Z"),
    )


def _br(db, code, date, hours):
    db.execute(
        "INSERT INTO boton_rojo(comuna_code, date, hours, area_ha, proportion, fetched_at) VALUES (?,?,?,?,?,?)",
        (code, date, hours, 100.0, 0.5, "2026-01-10T00:00:00Z"),
    )


def _sembrar(db) -> None:
    """Tres días en Valparaíso, dos incendios el mismo día (cuentan una vez) y uno sin pronóstico.

    10 ene: alto / extremo / fwi alto, con incendio y Botón Rojo.
    11 ene: bajo / bajo / bajo, sin incendio. Un Botón Rojo de 0 horas no cuenta.
    12 ene: alto / alto / fwi moderado, sin incendio, con Botón Rojo.
    20 ene: Botón Rojo sin fila de riesgo.
    5 feb: incendio sin fila de riesgo. Una comuna inexistente y una fila sin comuna no entran.
    """
    _risk(db, A.code, "2026-01-10", "alto", "extremo", "alto")
    _risk(db, A.code, "2026-01-11", "bajo", "bajo", "bajo")
    _risk(db, A.code, "2026-01-12", "alto", "alto", "moderado")
    _fire(db, "f1", A.name, "2026-01-10T18:00:00Z")
    _fire(db, "f2", A.name, "2026-01-10T20:00:00Z")
    _fire(db, "f3", A.name, "2026-02-05T15:00:00Z")
    _fire(db, "f4", None, "2026-01-10T15:00:00Z")
    _fire(db, "f5", "Comuna Inexistente", "2026-01-10T15:00:00Z")
    _br(db, A.code, "2026-01-10", 4)
    _br(db, A.code, "2026-01-12", 2)
    _br(db, A.code, "2026-01-20", 3)
    _br(db, A.code, "2026-01-11", 0)


def test_base_vacia_conteos_en_cero_y_tasas_vacias(make_client):
    with make_client() as client:
        response = client.get("/api/observability/concordancia")
    assert response.status_code == 200
    body = response.json()
    assert body["dias_riesgo"] == 0
    assert body["eventos_comuna_dia"] == 0
    assert body["eventos_con_riesgo"] == 0
    assert body["dias_boton_rojo"] == 0
    assert body["boton_rojo_en_alto_extremo"] == 0
    assert body["coincidencia_br_alto_extremo"] is None
    for clase in ("level", "level_combined", "fwi_level"):
        for nivel in ("bajo", "moderado", "alto", "extremo"):
            celda = body["clases"][clase][nivel]
            assert celda == {"dias": 0, "con_incendio": 0, "tasa": None, "lift": None}
        bloque = body["alto_extremo"][clase]
        assert bloque["dias"] == 0 and bloque["con_incendio"] == 0
        assert bloque["tasa"] is None and bloque["lift"] is None
        assert bloque["proporcion_incendios"] is None and bloque["coincidencia_boton_rojo"] is None
    nota = f"{body['method']} {body['note']}".lower()
    assert "pronóstico guardado" in nota
    assert "conaf" in nota and "comuna" in nota and "día" in nota
    assert "umbral" in nota


def test_conteos_exactos_de_la_concordancia(make_client):
    with make_client() as client:
        _sembrar(client.app.state.services.db)
        body = client.get("/api/observability/concordancia").json()
    assert body["dias_riesgo"] == 3
    assert body["eventos_comuna_dia"] == 2  # 10 ene agrupado; 5 feb sin pronóstico
    assert body["eventos_con_riesgo"] == 1
    assert body["dias_boton_rojo"] == 3  # el de 0 horas no entra; el 20 ene sí, aunque no haya riesgo
    assert body["boton_rojo_en_alto_extremo"] == 2
    assert body["coincidencia_br_alto_extremo"] == 0.6667
    assert A.name not in json.dumps(body), "el resumen público no nombra la comuna"
    level = body["clases"]["level"]
    assert level["alto"] == {"dias": 2, "con_incendio": 1, "tasa": 0.5, "lift": 1.5}
    assert level["bajo"] == {"dias": 1, "con_incendio": 0, "tasa": 0.0, "lift": 0.0}
    assert level["moderado"]["tasa"] is None and level["extremo"]["tasa"] is None
    combinado = body["clases"]["level_combined"]
    assert combinado["extremo"] == {"dias": 1, "con_incendio": 1, "tasa": 1.0, "lift": 3.0}
    assert combinado["alto"] == {"dias": 1, "con_incendio": 0, "tasa": 0.0, "lift": 0.0}
    fwi = body["clases"]["fwi_level"]
    assert fwi["alto"]["tasa"] == 1.0 and fwi["alto"]["lift"] == 3.0
    assert fwi["moderado"]["dias"] == 1 and fwi["moderado"]["con_incendio"] == 0
    ae = body["alto_extremo"]["level_combined"]
    assert ae["dias"] == 2 and ae["con_incendio"] == 1
    assert ae["tasa"] == 0.5 and ae["lift"] == 1.5
    assert ae["proporcion_incendios"] == 1.0 and ae["eventos_con_dato"] == 1
    assert ae["dias_con_boton_rojo"] == 2 and ae["coincidencia_boton_rojo"] == 1.0
    fwi_ae = body["alto_extremo"]["fwi_level"]
    assert fwi_ae["dias"] == 1 and fwi_ae["con_incendio"] == 1 and fwi_ae["coincidencia_boton_rojo"] == 1.0


def test_la_cache_de_una_hora_no_recalcula(make_client):
    with make_client() as client:
        db = client.app.state.services.db
        primero = client.get("/api/observability/concordancia").json()
        assert primero["dias_riesgo"] == 0
        row = db.one("SELECT expires_at FROM cache WHERE key = ?", ("obs:concordancia",))
        assert row is not None
        assert row["expires_at"] >= time.time() + 3500
        _risk(db, A.code, "2026-01-10", "extremo", "extremo", "extremo")
        assert client.get("/api/observability/concordancia").json()["dias_riesgo"] == 0


def test_la_vista_exporta_latencias_y_concordancia():
    """El job de pytest no tiene Node: la exportación se lee del fuente, y `node --check` la cubre el job web."""
    text = (ROOT / "web" / "js" / "views" / "calidad.js").read_text(encoding="utf-8")
    assert "export function latenciasRutas" in text
    assert "export function concordanciaRiesgo" in text
    assert "Todavía no hay suficientes días acumulados en este servidor para medir la concordancia." in text
    assert "Tiempos de respuesta del servidor (última hora)" in text
    assert "Concordancia del índice de peligro con CONAF" in text
    assert "/api/observability/routes" in text
    assert "/api/observability/concordancia" in text
    assert "resp: 'tiempos de respuesta de CONAF'" in text
    assert "cal: 'curva de calibración'" in text
    assert "fb: 'opiniones de los avisos'" in text
    # Number(null) === 0: una tasa ausente no puede formatearse como «0 %» ni «0».
    assert "typeof value === 'number' && Number.isFinite(value)" in text
    assert "sin dato" in text
    assert "Number.isFinite(Number(rate))" not in text
    vista = text.split("export function concordanciaRiesgo", 1)[1].split("let autoResult", 1)[0]
    assert "if (!conc || conc.error)" in vista
    assert "Este resumen no está disponible ahora. El resto de la página no se ve afectado." in vista
    assert "conc.dias_riesgo === 0" in vista
    assert "https://www.conaf.cl/incendios-forestales/incendios-forestales-en-chile/estadisticas-historicas/" in vista
    assert "https://deigeprif.com" in vista
    assert "conc.source_url" in vista
    assert "reporte de incendios de CONAF" in vista
    assert "CONAF GEPRIF · Botón Rojo" in vista
    mount = text.split("async mount(container)", 1)[1]
    load = mount.split("const load = async", 1)[1].split("container.addEventListener", 1)[0]
    assert "pedirRutas()" in load
    estado = mount.split("store.on('status'", 1)[1]
    assert "pedirRutas()" in estado

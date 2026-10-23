"""QUEMA-01 · «¿Puedo quemar hoy?»: dos estados y ninguno más, siempre remite a CONAF.

El bloque vive en `web/js/views/preparate.js` (`puedoQuemar` + `QUEMA_REGLAS`) y su dato
en `GET /api/climate/quema/{code}`: solo lectura de `risk_daily` y `boton_rojo` del día.
BRASA nunca dice «puedes quemar»: la autorización es de CONAF o del municipio.
"""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

PREPARATE = Path(__file__).resolve().parents[1] / "web" / "js" / "views" / "preparate.js"


def _src() -> str:
    return PREPARATE.read_text(encoding="utf-8")


def test_el_bloque_tiene_los_dos_estados_y_remite_a_conaf():
    src = _src()
    assert "Hoy no quemes" in src
    assert "No hay condiciones seguras conocidas" in src
    assert "la autorización la da CONAF o el municipio" in src
    # El bloque enlaza las dos fuentes oficiales ya citadas en el repo:
    # el aviso de quema (SAQ) y el Calendario de Quemas.
    assert "usoFuegoConaf" in src and "calendarioQuemas" in src
    assert "conaf.cl/incendios/prevencion-y-mitigacion/uso-del-fuego" in src
    assert "conafprevencionincendios.cl/quemas-controladas/calendario-de-quemas" in src


def test_el_bloque_nunca_dice_que_se_puede_quemar():
    """Un «puedes quemar», un «permitido» o un «autorizado» dejaría expuesta a la
    persona y a la app: la autorización es de CONAF, no de BRASA («autorización» sí
    aparece, es el nombre del trámite)."""
    src = _src().lower()
    assert "puedes quemar" not in src
    assert not re.search(r"permitid[oa]", src), "«permitido/permitida» no puede aparecer"
    assert not re.search(r"autorizad[oa]", src), "«autorizado/autorizada» tampoco"


def test_la_vista_evalua_los_dos_gatillos_oficiales():
    """«Hoy no quemes» solo sale del riesgo alto/extremo del día o del Botón Rojo de
    CONAF: son las reglas que el repo ya cita; no hay otra."""
    src = _src()
    assert "puedoQuemar" in src and "botonRojoHoras" in src
    assert "nivel === 'alto' || nivel === 'extremo'" in src
    assert "/api/climate/quema/" in src


def test_quema_hoy_devuelve_nivel_y_boton_rojo_del_dia(make_client):
    with make_client() as client:
        db = client.app.state.services.db
        today = datetime.now(ZoneInfo("America/Santiago")).date().isoformat()
        db.execute(
            "INSERT INTO risk_daily(comuna_code, date, level, score, hours_3of3, hours_2of3, computed_at) "
            "VALUES (7101, ?, 'alto', 0, 0, 0, '2026-10-20T00:00:00Z')",
            (today,),
        )
        db.execute(
            "INSERT INTO boton_rojo(comuna_code, date, hours, area_ha, proportion, fetched_at) "
            "VALUES (7101, ?, 4, 0, 0, '2026-10-20T00:00:00Z')",
            (today,),
        )
        body = client.get("/api/climate/quema/7101").json()
    assert body["comuna_code"] == 7101 and body["date"] == today
    assert body["level"] == "alto" and body["boton_rojo_hours"] == 4
    assert "CONAF" in body["source"]


def test_quema_hoy_sin_dato_devuelve_nulos_sin_inventar(make_client):
    with make_client() as client:
        body = client.get("/api/climate/quema/7101").json()
    assert body["level"] is None and body["boton_rojo_hours"] is None


def test_quema_hoy_comuna_inexistente_da_404(make_client):
    with make_client() as client:
        assert client.get("/api/climate/quema/99999").status_code == 404

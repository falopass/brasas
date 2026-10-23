"""OPS-01: veredictos del monitoreo programado (.github/scripts/monitoreo.py) con payloads de muestra."""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / ".github" / "scripts" / "monitoreo.py"
spec = importlib.util.spec_from_file_location("monitoreo", SCRIPT)
monitoreo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(monitoreo)


def sano() -> dict:
    """Perfil sano: fresco, respaldos al día y riesgo recalculado hace minutos."""
    return {
        "time_utc": "2026-10-19T00:11:27Z",
        "last_ingest_at": "2026-10-19T00:10:40Z",
        "freshness": {"last_ingest_at": "2026-10-19T00:10:40Z", "age_seconds": 47, "stale_after_s": 1800, "stale": False},
        "last_cycle": {"started_at": "2026-10-19T00:10:39Z", "finished_at": "2026-10-19T00:10:43Z", "backup": True, "work_backup": True},
        "risk_computed_at": "2026-10-19T00:08:00Z",
        "history": {
            "GOES19_FDCF": [{"ok": True}, {"ok": True}, {"ok": True}],
            "CONAF_INCENDIOS": [{"ok": True}, {"ok": False}, {"ok": True}],
        },
        "runs": [],
    }


def test_sano_sin_alerta():
    assert monitoreo.veredictos(sano()) == []


def test_history_incompleto_no_alerta():
    """Producción aún no sirve history (quedó en main sin desplegar): su ausencia
    no alerta, y dos registros fallidos no bastan: hacen falta 3 ejecuciones."""
    p = sano()
    del p["history"]
    assert monitoreo.veredictos(p) == []
    p = sano()
    p["history"]["GOES19_FDCF"] = [{"ok": False}, {"ok": False}]
    assert monitoreo.veredictos(p) == []


def test_datos_estancados_alerta():
    p = sano()
    p["freshness"] = {"last_ingest_at": "2026-10-18T20:00:00Z", "age_seconds": 2000, "stale_after_s": 1800, "stale": True}
    assert [corta for corta, _ in monitoreo.veredictos(p)] == ["datos estancados"]


def test_tres_fallos_seguidos_alerta():
    p = sano()
    p["history"]["GOES19_FDCF"] = [{"ok": False}, {"ok": False}, {"ok": False}]
    assert [corta for corta, _ in monitoreo.veredictos(p)] == ["3 fallos seguidos: GOES19_FDCF"]


def test_fallo_entre_exitos_no_alerta():
    p = sano()
    p["history"]["GOES19_FDCF"] = [{"ok": False}, {"ok": True}, {"ok": False}]
    assert monitoreo.veredictos(p) == []


def test_riesgo_sano_no_alerta():
    """risk_computed_at dentro del umbral de 6 h: el peligro de hoy está al día."""
    p = sano()
    p["risk_computed_at"] = "2026-10-18T19:12:00Z"  # 4 h 59 min antes de time_utc
    assert monitoreo.veredictos(p) == []


def test_risk_error_alerta():
    p = sano()
    p["last_cycle"]["risk_error"] = True
    assert [corta for corta, _ in monitoreo.veredictos(p)] == ["riesgo sin recalcular"]


def test_riesgo_viejo_alerta():
    """Siete horas sin recalcular: dos ciclos de 3 h perdidos superan el umbral de 6 h."""
    p = sano()
    p["risk_computed_at"] = "2026-10-18T17:11:27Z"
    razones = monitoreo.veredictos(p)
    assert [corta for corta, _ in razones] == ["riesgo viejo"]
    assert "7.0 h" in razones[0][1] and "umbral 6 h" in razones[0][1]


def test_riesgo_ausente_o_ilegible_no_alerta():
    p = sano()
    del p["risk_computed_at"]
    assert monitoreo.veredictos(p) == []
    p["risk_computed_at"] = "ayer"
    assert monitoreo.veredictos(p) == []


def test_respaldo_fallido_alerta():
    p = sano()
    p["last_cycle"]["backup"] = False
    assert [corta for corta, _ in monitoreo.veredictos(p)] == ["respaldo falló"]


def test_respaldos_ausentes_o_nulos_no_alertan():
    """backup solo se evalúa si el campo existe; work_backup solo alerta con false
    explícito. Sin last_cycle tampoco hay veredicto."""
    p = sano()
    del p["last_cycle"]["backup"]
    assert monitoreo.veredictos(p) == []
    p["last_cycle"] = None
    assert monitoreo.veredictos(p) == []
    p = sano()
    del p["last_cycle"]["work_backup"]
    assert monitoreo.veredictos(p) == []
    p["last_cycle"]["work_backup"] = None
    assert monitoreo.veredictos(p) == []


def test_work_backup_fallido_alerta():
    p = sano()
    p["last_cycle"]["work_backup"] = False
    p["last_cycle"]["backup_error"] = "work: No se pudo subir el respaldo (error 500 del almacenamiento)."
    assert [corta for corta, _ in monitoreo.veredictos(p)] == ["respaldo de work.db falló"]


def test_work_backup_por_hora_no_alerta_y_un_respaldo_viejo_si():
    """work.db sube cada hora: false sin error es «aún no tocaba» (#433, #671, #673 fueron falsas
    alarmas). Lo que sí alerta es que la última subida tenga más de 2,5 h."""
    p = sano()
    p["last_cycle"]["work_backup"] = False
    p["backup"] = {"work_updated_at": "2026-10-18T23:30:00Z"}
    assert monitoreo.veredictos(p) == []
    p["backup"]["work_updated_at"] = "2026-10-18T21:00:00Z"
    assert [corta for corta, _ in monitoreo.veredictos(p)] == ["respaldo de work.db falló"]


def test_cuerpo_issue_lleva_condiciones_y_valores():
    p = sano()
    p["freshness"]["stale"] = True
    p["history"]["GOES19_FDCF"] = [{"ok": False, "started_at": "2026-10-19T00:10:00Z"}] * 3
    p["last_cycle"]["risk_error"] = True
    p["last_cycle"]["work_backup"] = False
    p["last_cycle"]["backup_error"] = "work: error 500"
    p["risk_computed_at"] = "2026-10-18T17:11:27Z"
    cuerpo = monitoreo.cuerpo_issue(p, monitoreo.veredictos(p), "2026-10-19T00:15:00Z")
    for texto in (
        "datos estancados",
        "3 fallos seguidos: GOES19_FDCF",
        "2026-10-19T00:10:40Z",
        "2026-10-19T00:15:00Z",
        "/api/status?history=3",
        "riesgo sin recalcular",
        "riesgo viejo",
        "respaldo de work.db falló",
        "`last_cycle.risk_error`: True",
        "`last_cycle.work_backup`: False",
        "2026-10-18T17:11:27Z",
        "7.0 h",
        "umbral 6 h",
    ):
        assert texto in cuerpo


def pagina(ruta="/web/index.html", status=200, content_type="text/html; charset=utf-8", ms=120, error=None):
    return {"ruta": ruta, "status": status, "content_type": content_type, "ms": ms, "error": error}


def test_rutas_publicas_son_siete_absolutas_bajo_la_base():
    rutas = monitoreo.rutas_publicas("https://ejemplo.cl")
    assert len(rutas) == 7
    assert all(r.startswith("https://ejemplo.cl/web/") for r in rutas)
    assert rutas[-2].endswith("/manifest.webmanifest") and rutas[-1].endswith("/sw.js")


def test_paginas_sanas_no_alertan():
    resultados = [
        pagina(),
        pagina("/web/datos.html"),
        pagina("/web/manifest.webmanifest", content_type="application/manifest+json"),
        pagina("/web/sw.js", content_type="text/javascript"),
    ]
    assert monitoreo.evaluar_paginas(resultados) == []


@pytest.mark.parametrize(
    ("resultado", "detalle"),
    [
        (pagina("/web/datos.html", status=404, content_type="text/html"), "HTTP 404"),
        (pagina("/web/lista.html", content_type="text/plain"), "text/plain"),
        (pagina(status=None, error="URLError: sin ruta"), "URLError"),
    ],
)
def test_pagina_caida_alerta_con_el_detalle(resultado, detalle):
    razones = monitoreo.evaluar_paginas([resultado])
    assert [corta for corta, _ in razones] == [f"pagina_caida:{resultado['ruta']}"]
    assert detalle in razones[0][1]


def test_pagina_lenta_alerta_y_rapida_no():
    assert [corta for corta, _ in monitoreo.evaluar_paginas([pagina(ms=3000)])] == ["pagina_lenta:/web/index.html"]
    assert monitoreo.evaluar_paginas([pagina(ms=900)]) == []


def test_sin_resultados_de_paginas_no_hay_veredictos():
    assert monitoreo.evaluar_paginas([]) == []
    assert monitoreo.evaluar_paginas(None) == []


def test_cuerpo_issue_lista_cada_pagina_con_status_y_ms():
    p = sano()
    resultados = [pagina("/web/datos.html", status=404, ms=340), pagina("/web/index.html", ms=3000)]
    cuerpo = monitoreo.cuerpo_issue(p, monitoreo.evaluar_paginas(resultados), "2026-10-19T00:15:00Z", resultados)
    for texto in ("**Páginas públicas**", "/web/datos.html", "HTTP 404", "340 ms", "3000 ms"):
        assert texto in cuerpo


def test_script_con_payload_imprime_las_razones(tmp_path):
    """El script completo, sin red: un payload de prueba deja las razones en pantalla y en alerta.md."""
    p = sano()
    p["risk_computed_at"] = "2026-10-18T17:11:27Z"
    p["last_cycle"]["work_backup"] = False
    p["last_cycle"]["backup_error"] = "work: error 500"
    origen = tmp_path / "payload.json"
    origen.write_text(json.dumps(p), encoding="utf-8")
    entorno = {k: v for k, v in os.environ.items() if k != "GITHUB_OUTPUT"}
    entorno["PYTHONIOENCODING"] = "utf-8"
    corrida = subprocess.run(
        [sys.executable, str(SCRIPT), str(origen)], cwd=tmp_path, capture_output=True, text=True, encoding="utf-8", env=entorno
    )
    assert corrida.returncode == 0, corrida.stderr
    assert "riesgo viejo" in corrida.stdout and "respaldo de work.db falló" in corrida.stdout
    assert "riesgo viejo" in (tmp_path / "alerta.md").read_text(encoding="utf-8")

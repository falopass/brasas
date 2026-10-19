"""OPS-01: veredictos del monitoreo programado (.github/scripts/monitoreo.py) con payloads de muestra."""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "monitoreo", Path(__file__).resolve().parents[1] / ".github" / "scripts" / "monitoreo.py")
monitoreo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(monitoreo)


def sano() -> dict:
    """El mismo perfil de la sonda real de producción: fresco, respaldo al día, work_backup false."""
    return {"time_utc": "2026-10-19T00:11:27Z", "last_ingest_at": "2026-10-19T00:10:40Z",
            "freshness": {"last_ingest_at": "2026-10-19T00:10:40Z", "age_seconds": 47,
                          "stale_after_s": 1800, "stale": False},
            "last_cycle": {"started_at": "2026-10-19T00:10:39Z", "finished_at": "2026-10-19T00:10:43Z",
                           "backup": True, "work_backup": False},
            "history": {"GOES19_FDCF": [{"ok": True}, {"ok": True}, {"ok": True}],
                        "CONAF_INCENDIOS": [{"ok": True}, {"ok": False}, {"ok": True}]},
            "runs": []}


def test_sano_sin_alerta():
    assert monitoreo.veredictos(sano()) == []


def test_sin_history_no_hay_veredicto_por_fallos():
    """Producción aún no sirve history (quedó en main sin desplegar): su ausencia no alerta."""
    p = sano()
    del p["history"]
    assert monitoreo.veredictos(p) == []


def test_datos_estancados_alerta():
    p = sano()
    p["freshness"] = {"last_ingest_at": "2026-10-18T20:00:00Z", "age_seconds": 2000,
                      "stale_after_s": 1800, "stale": True}
    assert [corta for corta, _ in monitoreo.veredictos(p)] == ["datos estancados"]


def test_tres_fallos_seguidos_alerta():
    p = sano()
    p["history"]["GOES19_FDCF"] = [{"ok": False}, {"ok": False}, {"ok": False}]
    assert [corta for corta, _ in monitoreo.veredictos(p)] == ["3 fallos seguidos: GOES19_FDCF"]


def test_fallos_sin_tres_registros_no_alertan():
    """Dos registros fallidos no bastan: hacen falta al menos 3 ejecuciones del producto."""
    p = sano()
    p["history"]["GOES19_FDCF"] = [{"ok": False}, {"ok": False}]
    assert monitoreo.veredictos(p) == []


def test_fallo_entre_exitos_no_alerta():
    p = sano()
    p["history"]["GOES19_FDCF"] = [{"ok": False}, {"ok": True}, {"ok": False}]
    assert monitoreo.veredictos(p) == []


def test_respaldo_fallido_alerta():
    p = sano()
    p["last_cycle"]["backup"] = False
    assert [corta for corta, _ in monitoreo.veredictos(p)] == ["respaldo falló"]


def test_respaldo_ausente_no_alerta():
    """backup solo se evalúa si el campo existe; sin last_cycle tampoco hay veredicto."""
    p = sano()
    del p["last_cycle"]["backup"]
    assert monitoreo.veredictos(p) == []
    p["last_cycle"] = None
    assert monitoreo.veredictos(p) == []


def test_work_backup_no_es_senal():
    """work_backup viene false en producción y NO es condición de alerta."""
    p = sano()
    p["last_cycle"] = {"backup": True, "work_backup": False, "finished_at": "2026-10-19T00:10:43Z"}
    assert monitoreo.veredictos(p) == []


def test_cuerpo_issue_lleva_condicion_y_valores():
    p = sano()
    p["freshness"]["stale"] = True
    p["history"]["GOES19_FDCF"] = [{"ok": False, "started_at": "2026-10-19T00:10:00Z"}] * 3
    cuerpo = monitoreo.cuerpo_issue(p, monitoreo.veredictos(p), "2026-10-19T00:15:00Z")
    for texto in ("datos estancados", "3 fallos seguidos: GOES19_FDCF", "2026-10-19T00:10:40Z",
                  "2026-10-19T00:15:00Z", "/api/status?history=3"):
        assert texto in cuerpo

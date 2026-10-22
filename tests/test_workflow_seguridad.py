"""Guardas del workflow de auditoría de dependencias (.github/workflows/seguridad.yml, AUTO-58).

La auditoría semanal debe reportar sus hallazgos como un único issue con etiqueta
«dependencias» — con el listado crudo y el comando de arreglo — y cerrarlo sola cuando
vuelva a salir limpia, dejando el run en rojo mientras haya hallazgos. Estas pruebas
solo leen el YAML; no corren la auditoría.
"""

from __future__ import annotations

from pathlib import Path

import yaml

RUTA = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "seguridad.yml"
TEXTO = RUTA.read_text(encoding="utf-8")
WF = yaml.safe_load(TEXTO)


def _pasos() -> list[dict]:
    return [paso for job in WF["jobs"].values() for paso in job.get("steps", [])]


def _runs() -> list[str]:
    return [paso.get("run", "") for paso in _pasos()]


def _paso_con(clave: str) -> dict:
    pasos = [p for p in _pasos() if clave in p.get("run", "")]
    assert pasos, f"falta el paso que contiene «{clave}»"
    return pasos[0]


def _condicion(clave: str) -> str:
    return " ".join(_paso_con(clave).get("if", "").split())


def test_permisos_leen_contenido_y_escriben_issues():
    assert WF["permissions"]["contents"] == "read"
    assert WF["permissions"]["issues"] == "write"
    assert set(WF["permissions"]) == {"contents", "issues"}, "el token no debe ganar otros permisos"


def test_un_solo_job_y_corridas_en_cola():
    """Dos jobs, o dos corridas solapadas, podrían abrir dos issues por el mismo hallazgo."""
    assert len(WF["jobs"]) == 1
    assert WF["concurrency"]["group"] == "seguridad"
    assert WF["concurrency"]["cancel-in-progress"] is False


def test_condiciones_cierran_limpio_y_abren_con_hallazgos():
    """Con los if invertidos, el issue se cerraría justo cuando hay vulnerabilidades."""
    assert _condicion("gh issue close") == "steps.pip.outcome == 'success' && steps.npm.outcome == 'success'"
    assert _condicion("gh issue create") == "steps.pip.outcome == 'failure' || steps.npm.outcome == 'failure'"


def test_disparadores_sin_pull_request():
    """Solo agenda y manual: un CVE nuevo no debe dejar en rojo PRs ajenos."""
    on = WF.get("on", WF.get(True))  # PyYAML 1.1 lee «on» como booleano
    assert "schedule" in on and "workflow_dispatch" in on
    assert "pull_request" not in on


def test_pip_audit_sigue_sobre_el_lock():
    """El Dockerfile instala requirements.lock con --require-hashes: auditar otro archivo no sirve."""
    auditorias = [r for r in _runs() if "pip-audit -r" in r]
    assert auditorias, "falta el paso que corre pip-audit"
    assert all("requirements.lock" in r for r in auditorias)
    assert all("requirements.txt" not in r for r in auditorias)


def test_npm_audit_en_deploy_cloudflare_nivel_high():
    pasos = [p for p in _pasos() if "npm audit --audit-level" in p.get("run", "")]
    assert pasos, "falta el paso que corre npm audit"
    assert any(p.get("working-directory") == "deploy/cloudflare" and "--audit-level=high" in p["run"] for p in pasos)


def test_auditorias_capturan_salida_y_no_cortan_el_job():
    """Sin continue-on-error ni tee el paso final no tendría ni turno ni listado que reportar."""
    for paso in _pasos():
        run = paso.get("run", "")
        if "pip-audit -r" in run or "npm audit --audit-level" in run:
            assert paso.get("continue-on-error") is True
            assert "tee" in run


def test_hay_paso_que_crea_issue_con_etiqueta_dependencias_y_arreglo():
    creaciones = [r for r in _runs() if "gh issue create" in r]
    assert creaciones, "falta el paso que abre el issue"
    assert any("dependencias" in r for r in creaciones)
    assert any("Dependencias con vulnerabilidad conocida" in r for r in creaciones)
    assert any("uv pip compile" in r and "npm audit fix" in r for r in creaciones)


def test_otro_paso_cierra_el_issue_cuando_queda_limpio():
    idx_crea = [i for i, p in enumerate(_pasos()) if "gh issue create" in p.get("run", "")]
    idx_cierra = [i for i, p in enumerate(_pasos()) if "gh issue close" in p.get("run", "")]
    assert idx_cierra, "falta el paso que cierra el issue"
    assert not set(idx_crea) & set(idx_cierra), "crear y cerrar deben ser pasos distintos"


def test_el_run_queda_en_rojo_cuando_hay_hallazgos():
    assert any(r.strip() == "exit 1" for r in _runs())


def test_sin_secretos_tokens_ni_webhooks():
    assert "secrets." not in TEXTO
    assert "webhook" not in TEXTO.lower()
    assert "http://" not in TEXTO and "https://" not in TEXTO

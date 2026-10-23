"""Pruebas de .github/scripts/salud_repo.py (OPS-28), sin red ni subprocess real."""
from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".github" / "scripts" / "salud_repo.py"
_spec = importlib.util.spec_from_file_location("salud_repo", SCRIPT)
sr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sr)

INFORME = [
    {"etapa": "ruff", "ok": True, "s": 1.0, "log": "clean"},
    {"etapa": "pytest", "ok": False, "s": 30.0, "log": "F test_x"},
]


def test_dry_run_lista_las_cinco_etapas(capsys):
    assert sr.main(["--dry-run"]) == 0
    out = capsys.readouterr().out
    for nombre, _ in sr.ETAPAS:
        assert nombre in out
    assert len([l for l in out.splitlines() if l.startswith("·")]) == 5


def test_fallidas_nombra_las_etapas_en_rojo():
    assert sr.fallidas(INFORME) == ["pytest"]


def test_cuerpo_issue_lleva_sha_etapas_y_cola():
    cuerpo = sr.cuerpo_issue(INFORME, "abc1234", "https://x/run/1")
    for pedazo in ("abc1234", "pytest", "FALLÓ", "F test_x", "https://x/run/1"):
        assert pedazo in cuerpo


def test_decision_crear_comentar_cerrar():
    assert sr.decision(["pytest"], []) == "crear"
    assert sr.decision(["pytest"], [{"number": 7}]) == "comentar"
    assert sr.decision([], [{"number": 7}]) == "cerrar"
    assert sr.decision([], []) == "nada"


def test_correr_usa_el_run_inyectado(monkeypatch):
    def fake_run(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 0, "ok", "")
    informe = sr.correr(run=fake_run)
    assert len(informe) == len(sr.ETAPAS)
    assert all(e["ok"] for e in informe)


def test_workflow_tiene_cron_script_y_permisos():
    yml = (ROOT / ".github" / "workflows" / "salud-repo.yml").read_text(encoding="utf-8")
    assert 'cron: "0 11 * * *"' in yml
    assert ".github/scripts/salud_repo.py" in yml
    assert "issues: write" in yml
    assert "pull_request" not in yml

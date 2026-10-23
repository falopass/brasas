"""Pruebas de .github/scripts/autodiagnostico.py (OPS-27), sin red."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".github" / "scripts" / "autodiagnostico.py"
_spec = importlib.util.spec_from_file_location("autodiagnostico", SCRIPT)
ad = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ad)


def _get(payload):
    return lambda ruta: payload.get(ruta) or {"status": 0, "ms": 0, "body": ""}


def test_pagina_500_produce_hallazgo():
    hallazgos, _ = ad.revisar([], ["/web/datos.html"], _get({"/web/datos.html": {"status": 500, "ms": 200, "body": ""}}))
    assert hallazgos == [{"url": "/web/datos.html", "fallo": "HTTP 500", "ms": 200}]


def test_pagina_lenta_pasa_umbral():
    hallazgos, _ = ad.revisar([], ["/web/lista.html"], _get({"/web/lista.html": {"status": 200, "ms": 4100, "body": ""}}))
    assert hallazgos[0]["fallo"] == "lento"


def test_enlace_roto_aparece_listado():
    body = '<a href="/web/fantasma.html">x</a>'
    get = _get({"/": {"status": 200, "ms": 100, "body": body}, "/web/fantasma.html": {"status": 404, "ms": 50, "body": ""}})
    _, hrefs = ad.revisar([], ["/"], get)
    assert ad.enlaces_rotos(hrefs, get) == [{"url": "/web/fantasma.html", "fallo": "HTTP 404", "ms": 0}]


def test_todo_sano_no_alerta(tmp_path, monkeypatch, capsys):
    body = '<a href="/web/datos.html">x</a>'
    payload = {r: {"status": 200, "ms": 100, "body": body if r == "/" else ""} for r in ad.PAGINAS + ad.APIS}
    payload["/web/sitemap.xml"] = {"status": 200, "ms": 10, "body": "<loc>https://brasa-chile.ddiegosebastianbb.workers.dev/web/sitemap.xml</loc>"}
    p = tmp_path / "p.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    assert ad.main(["--payload", str(p)]) == 0


def test_workflow_tiene_cron_script_y_permisos():
    yml = (ROOT / ".github" / "workflows" / "autodiagnostico.yml").read_text(encoding="utf-8")
    assert 'cron: "17 */6 * * *"' in yml
    assert ".github/scripts/autodiagnostico.py" in yml
    assert "issues: write" in yml
    assert "pull_request" not in yml

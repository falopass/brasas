"""COB-01: la cobertura por comuna se mide y una pérdida hace fallar --check."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "local" / "cobertura_datos.py"

_spec = importlib.util.spec_from_file_location("cobertura_datos", SCRIPT)
cobertura = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = cobertura
_spec.loader.exec_module(cobertura)


def test_check_del_repo_en_verde():
    resultado = subprocess.run(
        [sys.executable, str(SCRIPT), "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr


def _escribir_datos(data: Path, cubiertas: list[int]) -> None:
    payload = {
        "fetched_at": "2026-10-19T00:00:00Z",
        "comunas": [{"code": code} for code in cubiertas],
    }
    (data / "datos.json").write_text(json.dumps(payload), encoding="utf-8")


def _fixture(tmp_path: Path, cubiertas: list[int]) -> tuple[Path, Path]:
    """Índice de tres comunas y un archivo que cubre las indicadas."""
    data = tmp_path / "data"
    data.mkdir(exist_ok=True)
    indice = [
        {"code": 1, "name": "Alfa", "region": "Región A"},
        {"code": 2, "name": "Beta", "region": "Región A"},
        {"code": 3, "name": "Gama", "region": "Región B"},
    ]
    (data / "comunas-index.json").write_text(json.dumps(indice), encoding="utf-8")
    _escribir_datos(data, cubiertas)
    return data, tmp_path / "COBERTURA.md"


def test_parser_detecta_la_comuna_perdida(tmp_path):
    data, doc = _fixture(tmp_path, [1, 2])
    assert cobertura.main([], data_dir=data, doc=doc) == 0
    assert "| `datos.json` | 2/3 | 1 |" in doc.read_text(encoding="utf-8")

    indice = json.loads((data / "comunas-index.json").read_text(encoding="utf-8"))
    documentado, total = cobertura.leer_documentado(doc, indice)
    assert documentado["datos.json"] == {3}
    assert total == 3

    # Gama (3) entra y Beta (2) sale: el total no cambia, pero Beta estaba cubierta.
    _escribir_datos(data, [1, 3])
    problemas = cobertura.comprobar(data, doc)
    assert any("datos.json" in problema and "Beta" in problema for problema in problemas)
    assert cobertura.main(["--check"], data_dir=data, doc=doc) == 1


def test_recuperar_cobertura_no_falla(tmp_path):
    data, doc = _fixture(tmp_path, [1, 2])
    assert cobertura.main([], data_dir=data, doc=doc) == 0

    _escribir_datos(data, [1, 2, 3])
    assert cobertura.comprobar(data, doc) == []

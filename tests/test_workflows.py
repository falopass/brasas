"""CI-26: guarda de los workflows de GitHub Actions (cadena de suministro del CI).

Lee .github/workflows/*.yml como texto (sin PyYAML, como test_manifest.py) y
exige tres reglas:
a) todo workflow declara `permissions:` (en el nivel que sea): sin ella, el
   GITHUB_TOKEN hereda el permiso por defecto del repositorio, que puede ser
   de lectura y escritura;
b) ningún `uses:` queda sin versión (`@`), para que no se cuele una acción de
   `main`;
c) ningún workflow combina `pull_request_target` con secretos.

Cada regla corre sobre el repositorio real y se demuestra mordiendo un archivo
roto escrito en tmp_path.
"""

import re

import pytest

from backend.settings import ROOT

WORKFLOWS = ROOT / ".github" / "workflows"
RE_PERMISSIONS = re.compile(r"(?m)^[ \t]*permissions\s*:")
RE_USES = re.compile(r"(?m)^[ \t-]*uses:\s*(\S+)")

ARCHIVOS = sorted(p.name for p in WORKFLOWS.glob("*.yml"))


def _sin_permissions(directorio):
    return [p.name for p in sorted(directorio.glob("*.yml")) if not RE_PERMISSIONS.search(p.read_text(encoding="utf-8"))]


def _uses_sin_version(directorio):
    return [
        f"{p.name}: {m.group(1)}"
        for p in sorted(directorio.glob("*.yml"))
        for m in RE_USES.finditer(p.read_text(encoding="utf-8"))
        if "@" not in m.group(1)
    ]


def _pull_request_target_con_secretos(directorio):
    malos = []
    for p in sorted(directorio.glob("*.yml")):
        texto = p.read_text(encoding="utf-8")
        if "pull_request_target" in texto and "secrets." in texto:
            malos.append(p.name)
    return malos


def test_hay_workflows_que_vigilar():
    assert len(ARCHIVOS) >= 5


@pytest.mark.parametrize("nombre", ARCHIVOS)
def test_workflow_declara_permissions(nombre):
    assert nombre not in _sin_permissions(WORKFLOWS), f"{nombre} no declara permissions:"


def test_uses_siempre_con_version():
    assert _uses_sin_version(WORKFLOWS) == []


def test_pull_request_target_no_toca_secretos():
    assert _pull_request_target_con_secretos(WORKFLOWS) == []


def test_la_guarda_de_permissions_muerde(tmp_path):
    (tmp_path / "roto.yml").write_text(
        "name: roto\non: push\njobs:\n  a:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo ok\n",
        encoding="utf-8",
    )
    (tmp_path / "bien.yml").write_text(
        "name: bien\non: push\npermissions:\n  contents: read\njobs:\n  a:\n    runs-on: ubuntu-latest\n",
        encoding="utf-8",
    )
    assert _sin_permissions(tmp_path) == ["roto.yml"]


def test_la_guarda_de_uses_muerde(tmp_path):
    (tmp_path / "roto.yml").write_text(
        "name: roto\non: push\njobs:\n  a:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: org/accion\n",
        encoding="utf-8",
    )
    (tmp_path / "bien.yml").write_text(
        "name: bien\non: push\njobs:\n  a:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: org/accion@v7\n",
        encoding="utf-8",
    )
    assert _uses_sin_version(tmp_path) == ["roto.yml: org/accion"]


def test_la_guarda_de_pull_request_target_muerde(tmp_path):
    (tmp_path / "roto.yml").write_text(
        "name: roto\non:\n  pull_request_target:\njobs:\n  a:\n    runs-on: ubuntu-latest\n    steps:\n"
        "      - run: echo ${{ secrets.MI_SECRETO }}\n",
        encoding="utf-8",
    )
    # pull_request_target sin secretos no es el problema que vigila la regla.
    (tmp_path / "bien.yml").write_text(
        "name: bien\non:\n  pull_request_target:\njobs:\n  a:\n    runs-on: ubuntu-latest\n    steps:\n      - run: echo ok\n",
        encoding="utf-8",
    )
    assert _pull_request_target_con_secretos(tmp_path) == ["roto.yml"]

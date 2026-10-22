"""DEPS-02: el lint no puede apuntar a una versión de Python distinta de la que corre producción.

El contenedor se construye con `FROM python:X.Y-...` (Dockerfile) y ruff decide qué
sintaxis acepta según `tool.ruff.target-version` (pyproject.toml). Si ambos valores se
separan, el lint puede dar por buena una construcción que el contenedor no entiende —o
al revés— sin que nadie lo note hasta que falla en producción.
"""

from __future__ import annotations

import re
import tomllib

from backend.settings import ROOT

IMAGEN = re.compile(r"^FROM python:(\d+\.\d+)", re.MULTILINE)


def _python_del_dockerfile() -> str:
    encontrado = IMAGEN.search((ROOT / "Dockerfile").read_text(encoding="utf-8"))
    assert encontrado, "Dockerfile no declara una línea «FROM python:X.Y-...»"
    return encontrado.group(1)


def _target_del_lint() -> str:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    target = config.get("tool", {}).get("ruff", {}).get("target-version")
    assert target, "pyproject.toml no declara tool.ruff.target-version"
    return target


def test_el_lint_apunta_al_python_del_contenedor():
    en_dockerfile = _python_del_dockerfile()
    esperado = "py" + en_dockerfile.replace(".", "")
    assert _target_del_lint() == esperado, (
        f"Dockerfile corre Python {en_dockerfile} pero pyproject.toml declara "
        f"target-version={_target_del_lint()!r}: cambia tool.ruff.target-version a {esperado!r}"
    )

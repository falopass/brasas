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

# Valores que acepta ruff desde py39; el contenedor corre 3.12, así que el proyecto
# nunca debiera apuntar a una versión anterior.
SOPORTADAS = frozenset({"py39", "py310", "py311", "py312", "py313", "py314"})


def _python_del_dockerfile() -> str:
    encontrado = IMAGEN.search((ROOT / "Dockerfile").read_text(encoding="utf-8"))
    assert encontrado, "Dockerfile no declara una línea «FROM python:X.Y-...»"
    return encontrado.group(1)


def _target_del_lint() -> str:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    target = config.get("tool", {}).get("ruff", {}).get("target-version")
    assert target, "pyproject.toml no declara tool.ruff.target-version"
    return target


def test_target_version_es_una_version_soportada_por_ruff():
    target = _target_del_lint()
    assert target in SOPORTADAS, f"pyproject.toml declara target-version={target!r}, que ruff no soporta: usa una de {sorted(SOPORTADAS)}"


def test_el_lint_apunta_al_python_del_contenedor():
    en_dockerfile = _python_del_dockerfile()
    en_lint = _target_del_lint()
    esperado = "py" + en_dockerfile.replace(".", "")
    assert en_lint == esperado, (
        f"Dockerfile corre Python {en_dockerfile} pero pyproject.toml declara "
        f"target-version={en_lint!r}: cambia tool.ruff.target-version a {esperado!r}"
    )

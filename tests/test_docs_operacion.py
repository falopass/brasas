"""`docs/OPERACION.md`: el runbook de incidentes no puede inventar endpoints ni comandos.

La sección se busca por título («Incidente en producción: los primeros 10 minutos») y no por
número, para que sobreviva a renumeraciones. Debe tener al menos cuatro subsecciones (una
por síntoma), todo `/api/...` suyo debe estar en `docs/API.md`, todo comando de sus bloques
debe ser de solo lectura (`python`, `gh` o `curl`) y debe nombrar el diagnóstico (`freshness`,
`history`, `last_cycle`) y la regla de oro: «no vemos calor» no es «no hay fuego».
"""

from __future__ import annotations

import re

from backend import settings

DOC = settings.ROOT / "docs" / "OPERACION.md"
API = settings.ROOT / "docs" / "API.md"
TITLE = re.compile(r"^## (\d+)\. Incidente en producción: los primeros 10 minutos\s*$", re.M)
API_PATH = re.compile(r"/api/[A-Za-z0-9_/{}\.-]+")
COMMAND = re.compile(r"^(python|gh|curl) ")
GOLDEN = "«no vemos calor» no es «no hay fuego»"


def _section() -> tuple[str, int]:
    """Texto de la sección del runbook y su número, hasta el próximo «## N.» o el final."""
    text = DOC.read_text(encoding="utf-8")
    start = TITLE.search(text)
    assert start, "docs/OPERACION.md no tiene la sección «Incidente en producción…»"
    rest = text[start.end() :]
    end = re.search(r"^## \d+\. ", rest, re.M)
    return (text[start.start() : start.end() + end.start()] if end else text[start.start() :]), int(start.group(1))


def _paths(text: str) -> set[str]:
    """Rutas /api/… sin parámetros de consulta ni puntuación de prosa."""
    return {path.split("?")[0].rstrip(".,;:)") for path in API_PATH.findall(text)} - {"/api/"}


def _commands(section: str) -> list[str]:
    """Líneas no vacías dentro de bloques ``` de la sección (se espera una por comando)."""
    inside, lines = False, []
    for line in section.splitlines():
        if line.strip().startswith("```"):
            inside = not inside
        elif inside and line.strip():
            lines.append(line.strip())
    return lines


def test_seccion_del_runbook_completa_y_coherente() -> None:
    section, number = _section()
    problems = []
    if len(re.findall(rf"^### {number}\.\d ", section, re.M)) < 4:
        problems.append(f"necesita al menos cuatro subsecciones (### {number}.1 …), una por síntoma")
    missing = [name for name in ("freshness", "history", "last_cycle") if name not in section]
    if missing:
        problems.append(f"no nombra el diagnóstico: {missing}")
    if GOLDEN not in section:
        problems.append(f"no repite la regla de oro: {GOLDEN}")
    ghost = sorted(_paths(section) - _paths(API.read_text(encoding="utf-8")))
    if ghost:
        problems.append(f"endpoints que no existen en docs/API.md: {ghost}")
    bad = [line for line in _commands(section) if not COMMAND.match(line)]
    if bad:
        problems.append(f"comandos que no son python/gh/curl: {bad}")
    assert not problems, "La sección del runbook: " + "; ".join(problems)

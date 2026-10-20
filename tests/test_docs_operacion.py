"""`docs/OPERACION.md`: el runbook de incidentes no puede inventar endpoints ni comandos.

La sección se busca por título («Incidente en producción: los primeros 10 minutos») y no por
número, para que sobreviva a renumeraciones: hoy es la §12, porque `main` ya tenía la §10 (sonda
de producción) y la §11 (salud por fuente) cuando se escribió.

- La sección existe y tiene al menos cuatro subsecciones, una por síntoma (mapa vacío, fuente
  caída, 5xx o lentitud, sitio que no carga).
- Todo `/api/...` de la sección está documentado en `docs/API.md` (se compara la ruta sin
  parámetros de consulta): un endpoint inventado hace fallar la prueba, y se corrige el texto.
- Todo comando en un bloque de código de la sección es de solo lectura: `python `, `gh ` o `curl `.
- La sección nombra las piezas del diagnóstico (`freshness`, `history`, `last_cycle`) y repite la
  regla de oro de la casa: «no vemos calor» no es «no hay fuego».
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


def test_section_exists_with_four_subsections() -> None:
    section, number = _section()
    subsections = re.findall(rf"^### {number}\.\d ", section, re.M)
    assert len(subsections) >= 4, f"La sección {number} necesita al menos cuatro subsecciones (### {number}.1 …), una por síntoma."


def test_api_paths_are_documented() -> None:
    section, _ = _section()
    documented = _paths(API.read_text(encoding="utf-8"))
    ghost = sorted(_paths(section) - documented)
    assert not ghost, f"Endpoints de la sección del runbook que no existen en docs/API.md: {ghost}"


def test_code_blocks_are_read_only_commands() -> None:
    section, _ = _section()
    bad = [line for line in _commands(section) if not COMMAND.match(line)]
    assert not bad, f"En la sección del runbook solo van comandos python/gh/curl, y estos no lo son: {bad}"


def test_section_names_the_diagnostics() -> None:
    section, _ = _section()
    missing = [name for name in ("freshness", "history", "last_cycle") if name not in section]
    assert not missing, f"La sección del runbook no nombra: {missing}"


def test_section_repeats_the_golden_rule() -> None:
    section, _ = _section()
    assert GOLDEN in section, f"La sección del runbook debe contener la regla de oro: {GOLDEN}"

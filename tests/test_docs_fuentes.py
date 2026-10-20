"""`docs/FUENTES.md` no puede separarse del código: cada fuente declara su recorte.

La sección «Cómo se recorta a Chile» debe tener una fila por cada módulo de
`backend/providers/` (salvo `_retry.py` y `__init__.py`) y cada fila debe citar
`archivo.py:línea` de un archivo que existe. Es una guarda de sincronización,
no de contenido: no valida que la descripción sea correcta.
"""

from __future__ import annotations

import re

from backend import settings

DOC = settings.ROOT / "docs" / "FUENTES.md"
PROVIDERS = settings.ROOT / "backend" / "providers"
SECTION = "## Cómo se recorta a Chile"
CITATION = re.compile(r"([\w./-]+\.py):(\d+)")
SEPARATOR = re.compile(r":?-{3,}:?")


def _section() -> str:
    text = DOC.read_text(encoding="utf-8")
    start = text.find(SECTION)
    assert start != -1, f"docs/FUENTES.md no tiene la sección «{SECTION}»"
    rest = text[start + len(SECTION) :]
    end = rest.find("\n## ")
    return rest if end == -1 else rest[:end]


def _rows() -> list[list[str]]:
    rows = []
    for line in _section().splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if all(SEPARATOR.fullmatch(cell) for cell in cells):
            continue
        rows.append(cells)
    return rows[1:]  # sin el encabezado


def _modules() -> set[str]:
    return {path.stem for path in PROVIDERS.glob("*.py") if path.name not in {"__init__.py", "_retry.py"}}


def test_todas_las_fuentes_tienen_fila() -> None:
    documented = {row[0].strip("`") for row in _rows()}
    assert documented == _modules(), (
        "La tabla «Cómo se recorta a Chile» debe tener una fila por proveedor. "
        f"Faltan: {sorted(_modules() - documented)}. Sobran: {sorted(documented - _modules())}."
    )


def test_cada_fila_cita_un_archivo_que_existe() -> None:
    problems = []
    for row in _rows():
        source = row[0].strip("`")
        assert len(row) == 5, f"La fila de {source} debe tener 5 columnas, tiene {len(row)}."
        citations = CITATION.findall(" | ".join(row))
        if not citations:
            problems.append(f"{source}: no cita ningún archivo:línea")
        for name, line in citations:
            path = settings.ROOT / name
            if not path.is_file():
                problems.append(f"{source}: no existe {name}")
            elif not 1 <= int(line) <= len(path.read_text(encoding="utf-8").splitlines()):
                problems.append(f"{source}: {name}:{line} está fuera del archivo")
    assert not problems, "Citas rotas en la tabla de recorte: " + "; ".join(problems)

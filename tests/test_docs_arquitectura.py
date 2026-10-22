"""`docs/ARQUITECTURA.md` no puede quedarse atrás: todo módulo de `backend/` aparece en el mapa.

Cada archivo `.py` directo de `backend/` y de `backend/providers/` (salvo `__init__.py`)
debe estar nombrado en el documento. Paquetes (directorios como `routes/` o `notify/`)
no se exigen por nombre de archivo: se documentan como conjunto.
"""

from __future__ import annotations

import pytest

from backend import settings

DOC = settings.ROOT / "docs" / "ARQUITECTURA.md"
BACKEND = settings.ROOT / "backend"


def _modules(subdir: str = "") -> list[str]:
    return sorted(path.name for path in (BACKEND / subdir).glob("*.py") if path.name != "__init__.py")


@pytest.mark.parametrize(
    ("subdir", "etiqueta"),
    [("", "Módulos de backend/"), ("providers", "Proveedores de backend/providers/")],
)
def test_modulos_documentados(subdir: str, etiqueta: str) -> None:
    text = DOC.read_text(encoding="utf-8")
    missing = [name for name in _modules(subdir) if name not in text]
    assert not missing, f"{etiqueta} sin mencionar en docs/ARQUITECTURA.md: {', '.join(missing)}. Agrégalos a la tabla «Mapa de módulos»."

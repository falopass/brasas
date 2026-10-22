"""`docs/DICCIONARIO_DATOS.md` es contrato verificable de los JSON publicados en `web/data/`.

- Todo JSON de primer nivel de `web/data/` (sin entrar en `cases/` ni los `.geojson`) tiene
  su sección en el documento: `## ... `nombre.json``.
- Toda clave de primer nivel y, en las listas de objetos, la unión de las claves de sus
  elementos, aparece en esa sección como campo (`nombre` en código inline).
- En los dict «mapa» —identificador → ficha, como `cells` o `comunas`— las claves son datos
  (códigos CUT, slugs) y no se exigen; lo que se exige son las claves de las fichas.
"""

from __future__ import annotations

import json
import re
from typing import Any

from backend import settings

DOC = settings.ROOT / "docs" / "DICCIONARIO_DATOS.md"
DATA = settings.ROOT / "web" / "data"
SECTION = re.compile(r"(?m)^##\s[^\n]*`([\w.-]+\.json)`")
FIELD = re.compile(r"`([^`\n]+)`")


def _fields(node: Any, out: set[str]) -> None:
    """Reúne las claves-campo de un JSON: las del objeto raíz, las de los elementos dict
    de cualquier lista y las de las fichas colgadas de un dict «mapa» (valores todos dict
    o lista). Las claves del mapa son identificadores, no campos, y no se exigen."""
    if isinstance(node, dict):
        out.update(node)
        for value in node.values():
            if isinstance(value, dict) and value and all(isinstance(v, (dict, list)) for v in value.values()):
                for inner in value.values():
                    _fields(inner, out)
            else:
                _fields(value, out)
    elif isinstance(node, list):
        for element in node:
            _fields(element, out)


def _documented() -> dict[str, set[str]]:
    """archivo → nombres en código inline dentro de su sección `## ... `archivo.json``."""
    text = DOC.read_text(encoding="utf-8")
    headings = list(SECTION.finditer(text))
    return {
        m.group(1): set(FIELD.findall(text[m.end() : headings[i + 1].start() if i + 1 < len(headings) else len(text)]))
        for i, m in enumerate(headings)
    }


def test_cada_json_y_sus_campos_estan_documentados() -> None:
    """Todo JSON servido por la app tiene sección y ningún campo queda sin explicar."""
    documented = _documented()
    archivos = sorted(DATA.glob("*.json"))
    missing = [p.name for p in archivos if p.name not in documented]
    assert not missing, f"Archivos de web/data sin sección en docs/DICCIONARIO_DATOS.md: {missing}"

    errors = []
    for path in archivos:
        fields: set[str] = set()
        _fields(json.loads(path.read_text(encoding="utf-8")), fields)
        errors += [f"el campo {f} de {path.name} no está en el diccionario" for f in sorted(fields - documented.get(path.name, set()))]
    assert not errors, " · ".join(errors)

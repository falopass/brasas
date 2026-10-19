"""`docs/API.md` no puede separarse del código: la doc es contrato verificable.

- Toda ruta escrita en el documento (`MÉTODO /api/ruta`, en un solo código inline) existe en la
  app con ese método.
- Toda ruta GET bajo `/api/` del código aparece en el documento.

Las rutas `/api/internal/*` quedan fuera de forma deliberada: son de operación (ciclo y respaldo),
exigen `X-Internal-Token` y en producción el Worker las bloquea; no son parte de la API pública.
"""
from __future__ import annotations

import re

from backend import settings
from backend.main import app

DOC = settings.ROOT / "docs" / "API.md"
INTERNAL_PREFIX = "/api/internal/"
ENTRY = re.compile(r"`(GET|POST|PUT|PATCH|DELETE)\s+(/api/[^`\s]+)`")


def _api_routes() -> dict[str, set[str]]:
    """path → métodos, recorriendo `app.routes` y expandiendo los routers incluidos.

    FastAPI >= 0.140 deja `include_router` como un marcador perezoso (`_IncludedRouter`):
    hay que pedirle `effective_candidates()` para ver las rutas reales. Los Mount (`/web`)
    y las rutas fuera de `/api/` no cuentan.
    """
    routes: dict[str, set[str]] = {}
    stack = list(app.routes)
    while stack:
        route = stack.pop()
        expand = getattr(route, "effective_candidates", None)
        if callable(expand):
            stack.extend(expand())
            continue
        path, methods = getattr(route, "path", None), getattr(route, "methods", None)
        if isinstance(path, str) and methods and path.startswith("/api/"):
            routes.setdefault(path, set()).update(methods)
    return routes


def _documented() -> set[tuple[str, str]]:
    """Pares (método, ruta) que el documento declara en código inline."""
    return set(ENTRY.findall(DOC.read_text(encoding="utf-8")))


def test_documented_routes_exist() -> None:
    """Toda ruta documentada existe en la app con ese método (una ruta inventada debe fallar)."""
    routes = _api_routes()
    ghost = [f"{m} {p}" for m, p in sorted(_documented()) if m not in routes.get(p, set())]
    assert not ghost, f"Rutas documentadas que no existen en la app: {ghost}"


def test_every_get_route_is_documented() -> None:
    """Toda ruta GET bajo /api/ (salvo /api/internal/*) aparece en docs/API.md."""
    documented = _documented()
    missing = [p for p, methods in sorted(_api_routes().items())
               if "GET" in methods and not p.startswith(INTERNAL_PREFIX) and ("GET", p) not in documented]
    assert not missing, f"Rutas GET sin documentar en docs/API.md: {missing}"


def test_internal_routes_are_out_of_scope() -> None:
    """La exclusión de /api/internal/* existe de verdad: hay rutas internas y no se documentan."""
    internal = [p for p in _api_routes() if p.startswith(INTERNAL_PREFIX)]
    assert internal, "No hay rutas /api/internal/*: el prefijo que el test excluye ya no existe"
    leaked = [f"{m} {p}" for m, p in sorted(_documented()) if p.startswith(INTERNAL_PREFIX)]
    assert not leaked, f"Las rutas internas no se documentan en la API pública: {leaked}"

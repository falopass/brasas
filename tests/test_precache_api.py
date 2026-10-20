"""QA-65: la lista CACHEABLE_API de web/sw.js se escribe a mano y nadie la
comparaba con las rutas reales del backend. Si una ruta se renombra o se
retira, el service worker guardaría un 404 con aspecto de dato sin que nadie
se enterara; y si falta una ruta pública de solo lectura, esa vista queda
sin datos sin conexión.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"

# Rutas públicas de solo lectura que la app necesita sin conexión: deben estar
# en CACHEABLE_API sí o sí (FIX-24/QA-51, app offline).
RUTAS_REQUERIDAS = [
    "/api/config",
    "/api/observations",
    "/api/incidents",
    "/api/official-fires",
    "/api/risk",
    "/api/status",
]


def _cacheable_api() -> list[str]:
    """Extrae el arreglo CACHEABLE_API de web/sw.js."""
    fuente = (WEB / "sw.js").read_text(encoding="utf-8")
    match = re.search(r"const\s+CACHEABLE_API\s*=\s*\[(.*?)\]", fuente, re.DOTALL)
    assert match, "no se encontró el arreglo CACHEABLE_API en web/sw.js"
    return re.findall(r"'([^']+)'", match.group(1))


def _rutas_api() -> set[str]:
    """Rutas registradas en la app que empiezan por /api (importa, sin red ni BD)."""
    from backend.main import app

    rutas = set()
    for route in app.routes:
        if getattr(route, "path", None):
            rutas.add(route.path)
        # FastAPI 0.146 envuelve cada include_router en un _IncludedRouter.
        original = getattr(route, "original_router", None)
        if original is not None:
            rutas.update(getattr(r, "path", None) for r in original.routes)
    return {r for r in rutas if r and r.startswith("/api")}


def test_cada_prefijo_de_cacheable_api_existe():
    rutas = _rutas_api()
    for prefijo in _cacheable_api():
        assert any(r == prefijo or r.startswith(prefijo + "/") for r in rutas), (
            f"CACHEABLE_API incluye {prefijo}, pero ninguna ruta registrada "
            "empieza por ahí: el service worker guardaría 404s como si fueran "
            "datos. Quita el prefijo de CACHEABLE_API en web/sw.js o restaura "
            "la ruta en el backend."
        )


def test_rutas_requeridas_estan_en_cacheable_api():
    cacheable = _cacheable_api()
    rutas = _rutas_api()
    for requerida in RUTAS_REQUERIDAS:
        assert any(r == requerida or r.startswith(requerida + "/") for r in rutas), (
            f"{requerida} está en RUTAS_REQUERIDAS pero ya no existe en el backend: actualiza RUTAS_REQUERIDAS en esta prueba."
        )
        assert requerida in cacheable, (
            f"{requerida} existe en el backend pero falta en CACHEABLE_API de "
            "web/sw.js: esa vista quedaría sin datos sin conexión. Agrega el "
            "prefijo a CACHEABLE_API."
        )

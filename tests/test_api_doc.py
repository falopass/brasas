"""`docs/API.md` no puede separarse del código: la doc es contrato verificable.

- Toda ruta escrita en el documento (`MÉTODO /api/ruta`, en un solo código inline) existe en la
  app con ese método.
- Toda ruta GET bajo `/api/` del código aparece en el documento.
- El contrato de `spread` en la ficha del incidente nombra sus claves (`speed_kmh`,
  `direction_deg`) y el documento no pierde el campo.

Las rutas `/api/internal/*` quedan fuera de forma deliberada: son de operación (ciclo y respaldo),
exigen `X-Internal-Token` y en producción el Worker las bloquea; no son parte de la API pública.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from backend import incidents, settings
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
    missing = [
        p
        for p, methods in sorted(_api_routes().items())
        if "GET" in methods and not p.startswith(INTERNAL_PREFIX) and ("GET", p) not in documented
    ]
    assert not missing, f"Rutas GET sin documentar en docs/API.md: {missing}"


def test_internal_routes_are_out_of_scope() -> None:
    """La exclusión de /api/internal/* existe de verdad: hay rutas internas y no se documentan."""
    internal = [p for p in _api_routes() if p.startswith(INTERNAL_PREFIX)]
    assert internal, "No hay rutas /api/internal/*: el prefijo que el test excluye ya no existe"
    leaked = [f"{m} {p}" for m, p in sorted(_documented()) if p.startswith(INTERNAL_PREFIX)]
    assert not leaked, f"Las rutas internas no se documentan en la API pública: {leaked}"


def _incident_detail_section() -> str:
    """Texto de la sección de la ficha del incidente en docs/API.md."""
    text = DOC.read_text(encoding="utf-8")
    heading = "#### `GET /api/incidents/{incident_id}`"
    start = text.index(heading)
    end = text.find("\n#### ", start + len(heading))
    return text[start:] if end == -1 else text[start:end]


def test_incident_spread_contract_is_documented(make_client) -> None:
    """`spread` y sus claves se documentan; se comprueban contra una respuesta real.

    La respuesta de demostración se arma como la de `dev.py seed`: un incidente con viento en
    `risk_hourly` y FFMC en `fwi_daily`. Con esos datos la ficha trae `spread`; el documento
    debe nombrar `speed_kmh` y `direction_deg` sin que el test fije sus valores.
    """
    with make_client() as client:
        db = client.app.state.services.db
        now = datetime.now(timezone.utc).replace(microsecond=0)
        stamp = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        row = {
            "id": "doc:spread",
            "source": "firms",
            "sensor": "VIIRS",
            "satellite": "N20",
            "resolution_m": 375,
            "lat": -33.5,
            "lon": -70.8,
            "observed_at": stamp,
            "frp_mw": 12.0,
            "confidence": "nominal",
            "comuna_code": 13101,
        }
        db.execute(
            "INSERT INTO observations(id, source, sensor, satellite, resolution_m, lat, lon, observed_at, frp_mw, "
            "confidence, comuna_code, run_id, ingested_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL,?)",
            ("doc:spread", "firms", "VIIRS", "N20", 375, -33.5, -70.8, stamp, 12.0, "nominal", 13101, stamp),
        )
        [incident] = incidents.update(db, [row], now)
        today = now.astimezone(ZoneInfo("America/Santiago")).date().isoformat()
        hour = (now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%MZ")
        db.execute(
            "INSERT INTO fwi_daily(comuna_code, date, ffmc, dmc, dc, isi, bui, fwi, level, computed_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (13101, today, 88.0, 20.0, 100.0, 5.0, 50.0, 15.0, "moderado", stamp),
        )
        db.execute(
            "INSERT INTO risk_hourly(comuna_code, computed_at, payload) VALUES (?,?,?)",
            (13101, stamp, json.dumps([{"time": hour, "wind": 25.0, "dir": 250.0}])),
        )
        spread = client.get(f"/api/incidents/{incident['id']}").json()["spread"]
    assert spread is not None, "La respuesta de demostración debe traer spread para comprobar el contrato"
    section = _incident_detail_section()
    assert "`spread`" in section, "La ficha del incidente debe documentar `spread`"
    missing = [key for key in ("speed_kmh", "direction_deg") if f"`{key}`" not in section]
    assert not missing, f"docs/API.md no nombra claves de `spread`: {missing}"

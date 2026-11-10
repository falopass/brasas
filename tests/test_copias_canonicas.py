"""OPS-817: la lista URLS_CANONICAS de deploy/cloudflare/src/copias.ts se
escribe a mano y debe ser exactamente lo que la app pide al cargar. Si api.js
cambia una plantilla, o store.js cambia el valor por defecto de obsHours, la
copia de R2 dejaría de corresponder a una URL real (o faltaría una) sin que
nadie lo notara: el borde seguiría despertando al contenedor.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
COPIAS_TS = ROOT / "deploy" / "cloudflare" / "src" / "copias.ts"


def _urls_canonicas() -> list[str]:
    """Extrae el arreglo URLS_CANONICAS de deploy/cloudflare/src/copias.ts."""
    fuente = COPIAS_TS.read_text(encoding="utf-8")
    match = re.search(r"URLS_CANONICAS[^=]*=\s*\[(.*?)\]", fuente, re.DOTALL)
    assert match, "no se encontró el arreglo URLS_CANONICAS en copias.ts"
    return re.findall(r"'([^']+)'", match.group(1))


def test_lista_canonica_es_lo_que_pide_la_app():
    api = (WEB / "js/api.js").read_text(encoding="utf-8")
    store = (WEB / "js/store.js").read_text(encoding="utf-8")
    data = (WEB / "js/data.js").read_text(encoding="utf-8")

    # El default de observaciones lo fija store.obsHours; data.js lo pide con reliable=false.
    obs_hours = re.search(r"obsHours:\s*(\d+)", store)
    assert obs_hours, "store.js ya no define el valor por defecto de obsHours"
    assert re.search(r"api\.observations\(store\.get\('obsHours'\),\s*false\)", data), (
        "data.js ya no pide las observaciones con obsHours y reliable=false"
    )
    # El default de incidentes lo fija la firma de api.incidents(hours, hulls).
    incidents = re.search(r"incidents:\s*\(hours\s*=\s*(\d+),\s*hulls\s*=\s*false\)", api)
    assert incidents, "api.incidents ya no tiene (hours = 48, hulls = false) por defecto"
    zona = (WEB / "js/views/zona.js").read_text(encoding="utf-8")
    assert re.search(r"api\.incidents\(\)", zona), "la portada ya no pide api.incidents() con el default"

    esperadas = {
        "/api/status",
        "/api/config",
        "/api/official-fires",
        "/api/risk",
        f"/api/incidents?hours={incidents.group(1)}",
        f"/api/observations?hours={obs_hours.group(1)}",
    }

    # Cada URL sale de una plantilla real de api.js: si alguna cambia, la lista deja
    # de coincidir con lo que la app pide.
    plantillas = [
        (r"config:\s*\(\)\s*=>\s*request\('/api/config'\)", "config"),
        (r"status:\s*\(history\)\s*=>\s*request\(`/api/status\$\{history\s*\?", "status"),
        (r"officialFires:\s*\(\)\s*=>\s*request\('/api/official-fires'\)", "officialFires"),
        (r"risk:\s*\(day\)\s*=>\s*request\(`/api/risk\$\{day\s*\?", "risk"),
        (r"observations:\s*\(hours,\s*reliable\)\s*=>\s*request\(`/api/observations\?hours=\$\{hours\}\$\{reliable\s*\?", "observations"),
        (r"incidents:\s*\(hours\s*=\s*\d+,\s*hulls\s*=\s*false\)\s*=>\s*request\(`/api/incidents\?hours=\$\{hours\}\$\{hulls\s*\?", "incidents"),
    ]
    for patron, nombre in plantillas:
        assert re.search(patron, api), (
            f"api.{nombre} ya no produce su URL canónica en web/js/api.js: "
            "revisa la plantilla y actualiza URLS_CANONICAS en copias.ts."
        )

    assert set(_urls_canonicas()) == esperadas, (
        f"URLS_CANONICAS ({_urls_canonicas()}) no coincide con lo que la app pide "
        f"al cargar ({sorted(esperadas)}): actualiza copias.ts o esta prueba."
    )

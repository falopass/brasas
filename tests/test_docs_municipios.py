"""La guía para municipios no puede quedarse atrás del repo.

SEC-14 se resolvió en el PR #143: `LICENSE` es AGPL-3.0 para el código y
`README.md` declara los datos propios bajo CC BY 4.0. Esta guarda fija que
`docs/MUNICIPIOS.md` y `docs/ROADMAP.md` no vuelvan a decir que la licencia
está pendiente ni que los datos propios no se pueden redistribuir.

DOCS-03: además, la guía no puede prometer páginas, parámetros de la pantalla
ni una dirección pública que el producto no tiene, ni enlazar documentos que
no existen. Si una de estas pruebas falla, se corrige la guía, no el producto.
"""

from __future__ import annotations

import json
import re
from urllib.parse import urlparse

from backend import settings

ROOT = settings.ROOT
LICENSE = ROOT / "LICENSE"
README = ROOT / "README.md"
MUNICIPIOS = ROOT / "docs" / "MUNICIPIOS.md"
ROADMAP = ROOT / "docs" / "ROADMAP.md"
BACKLOG = ROOT / "docs" / "BACKLOG_MAESTRO.md"
PANTALLA_JS = ROOT / "web" / "js" / "pantalla.js"
WRANGLER = ROOT / "deploy" / "cloudflare" / "wrangler.jsonc"

# Una línea con «licencia» más una de estas palabras declara la licencia como no decidida.
PENDING_WORDS = ("pendiente", "por decidir", "a decidir", "revisión", "elegir", "sin decidir")
STALE_PHRASES = ("pendiente de decisión", "no se autoriza")


def _stale_lines(doc) -> list[str]:
    problems = []
    for number, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), start=1):
        low = line.lower()
        if any(phrase in low for phrase in STALE_PHRASES):
            problems.append(f"{doc.name}:{number}: {line.strip()}")
        elif "licencia" in low and any(word in low for word in PENDING_WORDS):
            problems.append(f"{doc.name}:{number}: {line.strip()}")
    return problems


def _guia() -> str:
    return MUNICIPIOS.read_text(encoding="utf-8")


def test_licencia_decidida_en_todos_los_documentos() -> None:
    """SEC-14: AGPL-3.0 para el código y CC BY 4.0 para los datos propios."""
    text = LICENSE.read_text(encoding="utf-8")
    assert "AFFERO GENERAL PUBLIC LICENSE" in text and "Version 3" in text, "LICENSE debe seguir siendo GNU AGPL-3.0 (SEC-14)."
    text = README.read_text(encoding="utf-8")
    assert "AGPL-3.0" in text and "CC BY 4.0" in text, "README.md debe declarar AGPL-3.0 para el código y CC BY 4.0 para los datos propios."
    lines = [line for line in BACKLOG.read_text(encoding="utf-8").splitlines() if "SEC-14" in line]
    assert lines and any("AGPL-3.0" in line for line in lines), (
        "BACKLOG_MAESTRO.md debe registrar SEC-14 como decidido (AGPL-3.0 + CC BY 4.0)."
    )
    assert "CC BY 4.0" in _guia(), "docs/MUNICIPIOS.md debe indicar que los datos propios se publican bajo CC BY 4.0."


def test_guia_y_roadmap_no_declaran_licencia_pendiente() -> None:
    problems = _stale_lines(MUNICIPIOS) + _stale_lines(ROADMAP)
    assert not problems, (
        "La licencia ya está decidida (SEC-14): AGPL-3.0 código, CC BY 4.0 datos propios. "
        "Estas líneas la siguen declarando pendiente o prohíben redistribuir los datos:\n" + "\n".join(problems)
    )


def test_guia_cita_solo_parametros_reales_de_pantalla() -> None:
    params = set(re.findall(r"(?<![\w/])(\w+)=", _guia()))
    search_params = "\n".join(line for line in PANTALLA_JS.read_text(encoding="utf-8").splitlines() if "searchParams" in line)
    missing = [p for p in sorted(params) if p not in search_params]
    assert not missing, (
        f"La guía promete parámetros que web/js/pantalla.js no lee con searchParams: {', '.join(missing)}. Corrige docs/MUNICIPIOS.md."
    )


def test_guia_cita_la_direccion_publicada() -> None:
    hosts = set(re.findall(r"https://([\w.-]+)", _guia()))
    assert hosts, "docs/MUNICIPIOS.md no cita ninguna dirección https://."
    jsonc = "\n".join(line for line in WRANGLER.read_text(encoding="utf-8").splitlines() if not line.lstrip().startswith("//"))
    publicado = urlparse(json.loads(jsonc)["vars"]["PUBLIC_BASE_URL"]).netloc
    assert publicado in hosts, (
        f"La guía cita {sorted(hosts)} pero PUBLIC_BASE_URL de deploy/cloudflare/wrangler.jsonc "
        f"es {publicado}. Corrige la guía o anota el desfase en el PR."
    )


def test_guia_enlaza_solo_paginas_y_docs_existentes() -> None:
    guia = _guia()
    # Acepta «/web/pantalla.html», «/lista.html» y «web/datos.html»: todas viven en web/.
    rutas = {m.lstrip("/") for m in re.findall(r"(?<![\w./-])/?(?:web/)?[\w-]+\.html", guia)}
    faltan_html = [r for r in sorted(rutas) if not (ROOT / (r if r.startswith("web/") else f"web/{r}")).is_file()]
    docs = [MUNICIPIOS.parent / href for href in re.findall(r"\]\(([^)]+\.md)\)", guia)]
    docs += [ROOT / m for m in re.findall(r"(?<![\w/-])(docs/[\w./-]+\.md)", guia)]
    faltan_docs = [str(p.relative_to(ROOT)) for p in docs if not p.is_file()]
    assert not faltan_html and not faltan_docs, (
        f"La guía cita páginas que no existen en web/: {', '.join(faltan_html) or '—'}; "
        f"documentos inexistentes: {', '.join(sorted(faltan_docs)) or '—'}."
    )

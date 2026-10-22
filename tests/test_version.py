"""VERSION-01: la versión publicada no puede separarse del CHANGELOG.

La sonda de despliegue lee la versión de la API; si `backend/version.py` se queda atrás
o se adelanta a lo que el CHANGELOG declara publicado, el número miente justo cuando
se necesita para comprobar qué corre en producción (QA-209, OPS-19).
"""

from __future__ import annotations

import re

from backend.settings import ROOT
from backend.version import VERSION

# Una versión desplegada es un encabezado «## X.Y.Z — <fecha>»: sin fecha no se publicó.
DESPLEGADA = re.compile(r"^## (\d+\.\d+\.\d+)\s+—\s+\S", re.MULTILINE)
SIN_DESPLEGAR = re.compile(r"^## Sin desplegar\b", re.MULTILINE)


def _desplegadas() -> list[str]:
    """Encabezados «## X.Y.Z — <fecha>» del CHANGELOG, en orden de aparición."""
    return DESPLEGADA.findall((ROOT / "CHANGELOG.md").read_text(encoding="utf-8"))


def test_version_es_la_mas_alta_desplegada_en_el_changelog():
    desplegadas = _desplegadas()
    assert desplegadas, "CHANGELOG.md no tiene encabezados «## X.Y.Z — <fecha>»"
    mas_alta = max(desplegadas, key=lambda v: tuple(int(p) for p in v.split(".")))
    assert VERSION == mas_alta, (
        f"VERSION = «{VERSION}» pero el CHANGELOG declara desplegada «{mas_alta}»: "
        f"sube VERSION a «{mas_alta}» o estrena la sección «## {VERSION} — <fecha>» del CHANGELOG"
    )


def test_version_no_se_adelanta_a_lo_desplegado():
    if not SIN_DESPLEGAR.search((ROOT / "CHANGELOG.md").read_text(encoding="utf-8")):
        return
    desplegadas = _desplegadas()
    assert desplegadas and VERSION == desplegadas[0], (
        f"hay una sección «Sin desplegar» pero VERSION = «{VERSION}» no es la última "
        f"desplegada («{desplegadas[0] if desplegadas else 'ninguna'}»): VERSION no puede "
        "adelantarse a lo que el CHANGELOG declara publicado"
    )


def test_la_api_publica_la_misma_version(make_client):
    """Las salidas que publican la versión —/api/health, /api/config y /openapi.json— dicen lo mismo."""
    with make_client() as client:
        assert client.get("/api/health").json()["version"] == VERSION
        assert client.get("/api/config").json()["version"] == VERSION
        assert client.get("/openapi.json").json()["info"]["version"] == VERSION

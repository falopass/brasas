"""OPS-19: la versión publicada no puede separarse del CHANGELOG.

La sonda de despliegue lee la versión de la API; si `backend/version.py` se queda atrás,
producción parece una versión anterior a la que hay en `main`.
"""

from __future__ import annotations

import re

from backend.settings import ROOT
from backend.version import VERSION

FORMATO = re.compile(r"\d+\.\d+\.\d+")
ENCABEZADO = re.compile(r"^## (\d+\.\d+\.\d+)\b", re.MULTILINE)


def test_version_tiene_formato_x_y_z():
    assert FORMATO.fullmatch(VERSION), f"«{VERSION}» no es X.Y.Z"


def test_version_coincide_con_el_ultimo_encabezado_del_changelog():
    encabezados = ENCABEZADO.findall((ROOT / "CHANGELOG.md").read_text(encoding="utf-8"))
    assert encabezados, "CHANGELOG.md no tiene encabezados «## X.Y.Z»"
    assert VERSION == encabezados[0]


def test_la_api_publica_la_version(make_client):
    with make_client() as client:
        assert client.get("/api/health").json()["version"] == VERSION
        assert client.get("/api/config").json()["version"] == VERSION

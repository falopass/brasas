"""CONAF-OPS: marcas operativas en la API pública, Pyrocast en la ficha y capa SNASPE.

No toca la red ni la base. Lee el contrato que ya está en el código: los tres
instantes de CONAF salen en OFFICIAL_FIELDS, el control del mapa declara la capa
y la ficha enlaza el meteograma con las coordenadas del incidente.
"""

from __future__ import annotations

import re
from pathlib import Path

from backend.routes.public import OFFICIAL_FIELDS

ROOT = Path(__file__).resolve().parents[1]


def test_official_fields_incluye_marcas_operativas():
    for campo in ("detected_at", "alerted_at", "dispatched_at"):
        assert campo in OFFICIAL_FIELDS


def test_capa_snaspe_en_el_control():
    capas = (ROOT / "web" / "js" / "capas.js").read_text(encoding="utf-8")
    assert "key: 'snaspe'" in capas
    assert "label: 'Áreas protegidas (SNASPE)'" in capas
    assert "'snaspe-fill': 6" in capas


def test_ficha_enlaza_pyrocast_parametrizado():
    js = (ROOT / "web" / "js" / "views" / "incendio.js").read_text(encoding="utf-8")
    enlace = re.search(
        r'<a href="https://meteograma\.deigeprif\.com/\?lat=\$\{inc\.lat\.toFixed\(4\)\}&lon=\$\{inc\.lon\.toFixed\(4\)\}"([^>]*)>',
        js,
    )
    assert enlace, "falta el enlace parametrizado a Pyrocast"
    assert 'target="_blank"' in enlace.group(1) and 'rel="noopener"' in enlace.group(1)
    assert "Ver meteograma Pyrocast (CONAF) en este punto" in js

"""Variantes de nombre de comuna entre las fuentes oficiales y el territorio BCN.

Las fuentes no siempre usan la grafía del índice territorial (`web/data/comunas-index.json`):
el INE escribe «Marchihue» y «Trehuaco» en la capa del Censo 2024, y CONAF escribe
«Paiguano» y «Llay-Llay» en sus reportes. El diccionario único es `VARIANTES_COMUNA` de
`backend/geo.py` (vive en backend porque `scripts/` no se copia al contenedor y SENAPRED lo
usa en producción); este módulo solo lo reexporta para los informes que cruzan el nombre
de la fuente con el territorio (`validar_deteccion`, `calibrar_riesgo`, `build_censo`,
`build_campamentos`). Sin la variante, esos incendios caen en «sin calce».
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.geo import VARIANTES_COMUNA as VARIANTES  # noqa: E402
from backend.geo import normalizar_comuna as normalizar  # noqa: E402

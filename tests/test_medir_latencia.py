"""UX-15: el medidor de latencia (scripts/local/medir_latencia.py) sin red.

Las pruebas cubren lo puro: `percentil` por rango más cercano (con 3
repeticiones el p95 es simplemente la peor muestra) y `resumen`, que marca
`lenta` a la ruta cuyo p95 pasa el umbral. Ninguna toca la red: `--dry-run`
ya se prueba a mano con tests/data/latencia_muestra.json.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "local"))
import medir_latencia  # noqa: E402


def test_percentil_por_rango_mas_cercano():
    # Con una muestra el percentil es esa muestra; con dos, el p50 es la menor
    # y el p95 la mayor; con cien, el p95 es la muestra 95.
    assert medir_latencia.percentil([123.4], 95) == 123.4
    assert medir_latencia.percentil([200.0, 100.0], 50) == 100.0
    assert medir_latencia.percentil([100.0, 200.0], 95) == 200.0
    muestras = [float(i) for i in range(1, 101)]
    assert medir_latencia.percentil(muestras, 50) == 50.0
    assert medir_latencia.percentil(muestras, 95) == 95.0
    assert medir_latencia.percentil(muestras, 100) == 100.0


def test_resumen_marca_la_ruta_que_pasa_el_umbral():
    filas = [
        {"ruta": "/", "muestras": [100.0, 110.0, 120.0], "fallos": 0, "error": None},
        {"ruta": "/api/incidents", "muestras": [3000.0, 3100.0, 3200.0], "fallos": 0, "error": None},
    ]
    res = medir_latencia.resumen(filas, 2500)
    assert res[0]["lenta"] is False
    assert res[1]["lenta"] is True
    assert res[1]["p95"] == 3200.0
    codigo, titulo = medir_latencia.veredicto(res, 2500)
    assert codigo == 1
    assert "/api/incidents" in titulo


def test_tabla_sin_filas_no_revienta():
    res = medir_latencia.resumen([], 2500)
    assert res == []
    assert medir_latencia.veredicto(res, 2500) == (0, None)
    tabla = medir_latencia.tabla_markdown(res)
    assert "sin rutas medidas" in tabla

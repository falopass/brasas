"""Historia de incendios CONAF-GEPRIF por comuna (OFI-29): lectura perezosa de dos JSON.

`web/data/historia-comunas.json` (incendios de 50 ha o más, temporadas 2002-2003 a
2023-2024) lo genera `scripts/local/build_historia_comunas.py` y
`web/data/temporada-2526.json` (la temporada en curso) `build_temporada_2526.py`; ambos
se versionan con el repo. El emparejamiento es por el nombre territorial normalizado —
la misma forma `_fold` de `backend/geo.py` que usa el script que arma la historia—
porque el archivo indexa con claves tipo «algarrobo», no por código.

Si un archivo falta o no se puede leer, su bloque sale en None. Si la comuna no figura
en el archivo, los campos de datos salen en None y la nota lo explica: nunca un cero
inventado.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from backend.geo import _fold
from backend.settings import ROOT

HISTORIA_FILE = ROOT / "web" / "data" / "historia-comunas.json"
TEMPORADA_FILE = ROOT / "web" / "data" / "temporada-2526.json"

ULTIMAS_TEMPORADAS = 3

NOTE_HISTORIA = (
    "Incendios de 50 ha o más registrados por CONAF-GEPRIF entre las temporadas 2002-2003 "
    "y 2023-2024: son los incendios grandes que quedaron en la capa, no el total quemado "
    "de la comuna; es historia, no es una predicción."
)
NOTE_TEMPORADA = "Incendios y hectáreas informados por CONAF-GEPRIF en la temporada del archivo: es lo ya reportado, no es una predicción."


def _read(path: Path) -> dict[str, Any] | None:
    """El objeto raíz del archivo, o None si falta, no es JSON válido o no es un objeto."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


@lru_cache(maxsize=1)
def _historia_file() -> dict[str, Any] | None:
    """El archivo de historia completo; None si no se pudo leer."""
    return _read(HISTORIA_FILE)


@lru_cache(maxsize=1)
def _temporada_file() -> dict[str, Any] | None:
    """El archivo de la temporada completo; None si no se pudo leer."""
    return _read(TEMPORADA_FILE)


def _source(data: dict[str, Any]) -> dict[str, Any]:
    """`{name, url, fetched_at}` de la fuente declarada por el archivo.

    En `historia-comunas.json` la fuente es un objeto; en `temporada-2526.json` es solo
    la URL del CSV de GEPRIF y la fecha de descarga va al nivel raíz.
    """
    raw = data.get("source")
    if isinstance(raw, dict):
        return {"name": raw.get("name") or "CONAF-GEPRIF", "url": raw.get("url"), "fetched_at": raw.get("fetched_at")}
    return {"name": "CONAF-GEPRIF", "url": raw if isinstance(raw, str) else None, "fetched_at": data.get("fetched_at")}


def comuna(name: str) -> dict[str, Any] | None:
    """Bloque `historia` de la ficha: totales, los 3 incendios más grandes y las últimas
    3 temporadas. None cuando el archivo no se puede leer; campos en None con nota cuando
    la comuna no figura en él."""
    data = _historia_file()
    if data is None:
        return None
    block = {"source": _source(data)}
    filas = data.get("comunas")
    entry = filas.get(_fold(name)) if isinstance(filas, dict) else None
    if not isinstance(entry, dict):
        return block | {
            "note": f"«{name}» no figura en la historia de incendios de CONAF-GEPRIF; el archivo no la cubre.",
            "total_ha": None,
            "total_incendios": None,
            "top": None,
            "temporadas": None,
        }
    top = entry.get("top") if isinstance(entry.get("top"), list) else []
    temporadas = entry.get("temporadas") if isinstance(entry.get("temporadas"), list) else []
    return block | {
        "note": NOTE_HISTORIA,
        "total_ha": entry.get("total_ha"),
        "total_incendios": entry.get("total_incendios"),
        "top": top[:3],
        "temporadas": temporadas[-ULTIMAS_TEMPORADAS:],
    }


def temporada(name: str) -> dict[str, Any] | None:
    """Bloque `temporada` de la ficha: la fila de la comuna en la temporada del archivo, su
    región y su puesto dentro de la región por hectáreas quemadas (entre las comunas que
    figuran en el archivo; los empates comparten puesto). None cuando el archivo no se
    puede leer; campos en None con nota cuando la comuna no figura en él."""
    data = _temporada_file()
    if data is None:
        return None
    block = {"source": _source(data), "temporada": data.get("temporada")}
    filas = data.get("comunas")
    key = _fold(name)
    row = (
        next(
            (c for c in filas if isinstance(c, dict) and _fold(str(c.get("name") or "")) == key),
            None,
        )
        if isinstance(filas, list)
        else None
    )
    if row is None:
        return block | {
            "note": f"«{name}» no figura en el reporte de la temporada de CONAF-GEPRIF; el archivo no la cubre.",
            "region": None,
            "puesto_en_region": None,
            "incendios": None,
            "hectareas": None,
            "mes_peak": None,
            "max_ha": None,
        }
    puesto = 1 + sum(
        1
        for c in filas
        if isinstance(c, dict) and c.get("region") == row.get("region") and (c.get("hectareas") or 0) > (row.get("hectareas") or 0)
    )
    return block | {
        "note": NOTE_TEMPORADA,
        "region": row.get("region"),
        "puesto_en_region": puesto,
        "incendios": row.get("incendios"),
        "hectareas": row.get("hectareas"),
        "mes_peak": row.get("mes_peak"),
        "max_ha": row.get("max_ha"),
    }

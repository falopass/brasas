"""Exposición del Censo 2024 por comuna (OFI-29): lectura perezosa de web/data/censo_2024.json.

El archivo lo genera scripts/local/build_censo.py desde la capa oficial del INE y se versiona
con el repo. Si falta o no se puede leer, la exposición sale en None: nunca se inventa.
Una fila incompleta se descarta sin tumbar el resto del índice.
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from backend.settings import ROOT

CENSO_FILE = ROOT / "web" / "data" / "censo_2024.json"
CONTEOS = ("poblacion", "viviendas", "hogares")


def _entero(valor: Any, minimo: int) -> int | None:
    """Entero >= `minimo` desde int, float entero o texto numérico; None si no califica."""
    if isinstance(valor, bool):
        return None
    if isinstance(valor, float):
        if not valor.is_integer():
            return None
        valor = int(valor)
    elif isinstance(valor, str):
        try:
            valor = int(valor.strip())
        except ValueError:
            return None
    if not isinstance(valor, int) or valor < minimo:
        return None
    return valor


def _texto(valor: Any) -> bool:
    return isinstance(valor, str) and bool(valor.strip())


def _validar(entrada: dict[str, Any], license_: Any) -> tuple[int, dict[str, Any]] | str:
    """Fila normalizada y su código, o el motivo por el que se descarta."""
    code = _entero(entrada.get("code"), 1)
    if code is None:
        return "'code' no es un entero positivo"
    campos: dict[str, Any] = {}
    for campo in CONTEOS:
        valor = _entero(entrada.get(campo), 0)
        if valor is None:
            return f"comuna {code}: '{campo}' no es un entero mayor o igual a 0"
        campos[campo] = valor
    for campo in ("source", "fetched_at"):
        if not _texto(entrada.get(campo)):
            return f"comuna {code}: '{campo}' vacío o no es texto"
        campos[campo] = entrada[campo]
    campos["license"] = license_
    return code, campos


def _leer() -> tuple[dict[int, dict[str, Any]], list[str]]:
    """Índice y problemas del archivo actual; sin caché, para diagnóstico."""
    try:
        data = json.loads(CENSO_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {}, [f"censo: no se pudo leer el archivo: {exc}"]
    if not isinstance(data, dict):
        return {}, ["censo: la raíz del archivo no es un objeto"]
    filas = data.get("comunas")
    if not isinstance(filas, list):
        return {}, ["censo: 'comunas' no es una lista"]
    index: dict[int, dict[str, Any]] = {}
    problemas: list[str] = []
    for numero, entrada in enumerate(filas, start=1):
        if not isinstance(entrada, dict):
            problemas.append(f"fila {numero}: no es un objeto")
            continue
        resultado = _validar(entrada, data.get("license"))
        if isinstance(resultado, str):
            problemas.append(f"fila {numero}: {resultado}")
        else:
            index[resultado[0]] = resultado[1]
    return index, problemas


@lru_cache(maxsize=1)
def _index() -> dict[int, dict[str, Any]]:
    """Índice por código de comuna; vacío si el archivo falta o está corrupto."""
    return _leer()[0]


def problemas() -> list[str]:
    """Una línea por fila descartada del censo, con su código cuando se pudo leer."""
    return _leer()[1]


def comuna(code: int) -> dict[str, Any] | None:
    """Bloque de exposición de una comuna, o None si el censo no la cubre."""
    return _index().get(code)

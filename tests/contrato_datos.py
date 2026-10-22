"""Contrato de los JSON oficiales de `web/data` que alimentan las vistas.

Cada validador es una función pura: recibe el JSON ya cargado y lanza ValueError
con el nombre del archivo y el elemento culpable si la forma no es la que asumen
las vistas. Las guardas por tema (`test_censo.py`, `test_interfaz.py` y
`test_data_files.py`) los aplican al archivo real y a payloads rotos.
"""

import re
from datetime import datetime


def _fail(context, msg):
    raise ValueError(f"{context}: {msg}")


def _parse_iso_utc(value, context):
    if not isinstance(value, str) or not value:
        _fail(context, f"timestamp vacío o no string: {value!r}")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        _fail(context, f"timestamp no ISO: {value!r}")
    if dt.tzinfo is None:
        _fail(context, f"timestamp sin zona UTC: {value!r}")
    return dt


def _check_meta(data, filename):
    """Cabecera común: objeto con source, license y fetched_at."""
    if not isinstance(data, dict):
        _fail(filename, "debe ser un objeto")
    for field in ("source", "license"):
        if not isinstance(data.get(field), str) or not data[field].strip():
            _fail(filename, f"'{field}' vacío o no string")
    _parse_iso_utc(data.get("fetched_at"), filename)


def _check_code(value, context):
    """CUT de comuna sin el cero inicial: entero de 4 o 5 dígitos (1101 a 16305)."""
    if not isinstance(value, int) or isinstance(value, bool):
        _fail(context, f"code no entero: {value!r}")
    if not 1000 <= value <= 99999:
        _fail(context, f"code fuera del rango CUT: {value!r}")


def _check_nonneg(value, context, field):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        _fail(context, f"'{field}' no numérico: {value!r}")
    if value < 0:
        _fail(context, f"'{field}' negativo: {value!r}")


def validate_censo_2024(data):
    """censo_2024.json: población, viviendas y hogares del INE por comuna."""
    _check_meta(data, "censo_2024.json")
    comunas = data.get("comunas")
    if not isinstance(comunas, list) or len(comunas) < 300:
        _fail("censo_2024.json", f"'comunas' debe ser lista de 300+: {comunas!r:.80}")

    seen = set()
    for comuna in comunas:
        code = comuna.get("code")
        ctx = f"censo_2024.json comuna {code!r}"
        _check_code(code, ctx)
        if code in seen:
            _fail(ctx, "code duplicado")
        seen.add(code)
        if not comuna.get("name"):
            _fail(ctx, "name vacío")
        for field in ("poblacion", "viviendas", "hogares"):
            _check_nonneg(comuna.get(field), ctx, field)
    return data


def validate_interfaz(data, comunas_index=None):
    """interfaz.json: hectáreas y porcentaje en zona urbano-forestal por comuna."""
    _check_meta(data, "interfaz.json")
    comunas = data.get("comunas")
    if not isinstance(comunas, dict) or len(comunas) < 300:
        _fail("interfaz.json", f"'comunas' debe ser objeto de 300+: {comunas!r:.80}")

    for key, zona in comunas.items():
        ctx = f"interfaz.json comuna {key!r}"
        if not isinstance(key, str) or not key.isdigit():
            _fail(ctx, "clave no numérica")
        _check_nonneg(zona.get("ha_interfaz"), ctx, "ha_interfaz")
        pct = zona.get("pct_comuna")
        if not isinstance(pct, (int, float)) or isinstance(pct, bool):
            _fail(ctx, f"'pct_comuna' no numérico: {pct!r}")
        if not 0 <= pct <= 100:
            _fail(ctx, f"'pct_comuna' fuera de [0, 100]: {pct!r}")

    if comunas_index is not None:
        codes = set(comunas_index) if isinstance(comunas_index, dict) else {c["code"] for c in comunas_index}
        unknown = [k for k in comunas if int(k) not in codes]
        if unknown:
            _fail("interfaz.json", f"claves sin comuna en comunas-index: {sorted(unknown)}")
    return data


def validate_temporada_2526(data):
    """temporada-2526.json: incendios y hectáreas de CONAF por comuna y región."""
    _check_meta(data, "temporada-2526.json")
    temporada = data.get("temporada")
    if not isinstance(temporada, str) or not re.fullmatch(r"\d{4}-\d{4}", temporada):
        _fail("temporada-2526.json", f"'temporada' sin forma AAAA-AAAA: {temporada!r}")
    # Son las comunas con incendios de la temporada, no el país completo:
    # basta con que ambas listas existan y no vengan vacías.
    if not isinstance(data.get("regiones"), list) or not data["regiones"]:
        _fail("temporada-2526.json", "'regiones' debe ser lista no vacía")
    comunas = data.get("comunas")
    if not isinstance(comunas, list) or not comunas:
        _fail("temporada-2526.json", "'comunas' debe ser lista no vacía")

    seen = set()
    for comuna in comunas:
        code = comuna.get("code")
        ctx = f"temporada-2526.json comuna {code!r}"
        _check_code(code, ctx)
        if code in seen:
            _fail(ctx, "code duplicado")
        seen.add(code)
        if not comuna.get("name"):
            _fail(ctx, "name vacío")
        for field in ("incendios", "hectareas", "max_ha"):
            _check_nonneg(comuna.get(field), ctx, field)
    return data

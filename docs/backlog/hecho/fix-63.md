---
id: FIX-63
repo: brasas
rama: fix/censo-tolera-campos-faltantes
modelo: swe-2-medium
riesgo: B
archivos: backend/censo.py, tests/test_censo.py, CHANGELOG.md
e2e: no
intento: 0
ronda_review: 0
estado_desde: 2026-10-20T10:10:17
nota: Reencolado: la corrida falló por rate limit del modelo gratis, no por el ítem.
---

# FIX-63 · Un campo raro en `censo_2024.json` no puede tumbar la ficha de la comuna

**Objetivo (una frase):** que un registro incompleto o con otro tipo en `web/data/censo_2024.json` deje esa comuna sin exposición (como hoy cuando falta el archivo) en vez de lanzar una excepción que rompe `/api/comuna/{code}`.

**Ítem:** robustez de la capa de datos de exposición (OFI-07/OFI-29) ✅; no viene del backlog: sale de leer el cargador en `main` `1898e37`.

**Evidencia de que está pendiente (main `1898e37`):**
- `backend/censo.py:21-24` — el `try` cubre solo `read_text` y `json.loads`; el `except (OSError, ValueError)` protege el archivo faltante o corrupto.
- `backend/censo.py:26-36` — fuera del `try`, la comprensión indexa con corchetes `c["code"]`, `c["poblacion"]`, `c["viviendas"]`, `c["hogares"]`, `c["source"]` y `c["fetched_at"]`. Un registro al que le falte uno de esos campos lanza `KeyError`; uno con `poblacion` como texto pasa sin aviso y se sirve como si fuera un número. El resultado no es un `None` silencioso: la excepción viaja por `comuna()` (`:39-41`) hasta quien llama.
- `backend/routes/comuna.py:93` — la ficha de comuna devuelve `"exposicion": censo.comuna(code)`: con el `KeyError`, la ficha entera responde 500 y el mapa de riesgo se queda sin comuna.
- El único guardián hoy es un test de datos (`tests/test_censo.py`) que lee el JSON versionado: si el archivo se regenera mal en un PR, ese test avisa; si se regenera mal en producción (o un `scripts/local/build_censo.py` nuevo cambia el formato), no hay red de seguridad.

**Qué hacer (y nada más que esto):**
1. En `_index()`, leer con `.get()` y validar tipo antes de aceptar una fila: `code` entero, `poblacion`/`viviendas`/`hogares` enteros, `source` y `fetched_at` textos no vacíos. Fila que no cumpla: se descarta y la comuna queda sin exposición. `data.get("comunas") or []` para el archivo sin la lista.
2. Regla de oro: **nunca inventar un valor**. Un campo faltante no se rellena con 0 ni con el total nacional; la comuna simplemente no tiene bloque de exposición, que es el comportamiento que el docstring ya promete (`backend/censo.py:3-5`).
3. Deja el criterio escrito en el docstring de `_index()` en una línea (qué se descarta y por qué), y conserva `license` como está.
4. Pruebas en `tests/test_censo.py`, con `tmp_path` y `monkeypatch` sobre `censo.CENSO_FILE` más `censo._index.cache_clear()` (la función está memorizada con `lru_cache`; sin limpiar, la prueba ve el archivo anterior). Casos: (a) archivo válido → devuelve la fila completa; (b) archivo sin `comunas` → `{}` sin excepción; (c) una fila sin `poblacion` → esa comuna queda fuera y las demás siguen; (d) `poblacion` como texto → descartada; (e) JSON corrupto y archivo inexistente → `{}` como hoy.
5. Las cinco pruebas de datos que ya tiene el archivo se conservan sin cambios.

**No toques nada más.** En particular: `backend/routes/comuna.py`, `web/data/censo_2024.json` (es un dato versionado, no se edita aquí), `scripts/local/build_censo.py`, `backend/settings.py` y `tests/test_paginas_publicas.py`. Archivos: los tres del encabezado.

**Criterio de listo (verificable):** `python dev.py test -k censo` en verde con las pruebas nuevas (al menos la de la fila sin `poblacion` falla contra `main`) y `python dev.py check` en verde.

Verifica con /verificar y entrega con /entregar-pr. No mergees por iniciativa propia.


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.

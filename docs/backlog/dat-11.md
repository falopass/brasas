---
id: DAT-11
repo: brasas
rama: feat/diccionario-datos-abiertos
modelo: swe-2-high
riesgo: B
archivos: backend/routes/opendata.py, tests/test_opendata.py, web/js/datos.js, web/datos.html, docs/API.md, CHANGELOG.md
e2e: si
intento: 0
ronda_review: 0
estado_desde: 2026-10-20T10:10:17
nota: Reencolado: la corrida falló por rate limit del modelo gratis, no por el ítem.
---

**Objetivo.** Que cada conjunto de datos abiertos de BRASA diga, campo por campo, qué significa y en qué unidad viene, tanto en el índice `GET /api/opendata` como en la página `web/datos.html`, para que un municipio, una junta de vecinos o una tesis pueda usar el dato sin leer el código.

**Ítem del backlog.** Prioridad 4 de esta ronda: «datos abiertos bien explicados». Continúa OPS-23 y UX-57 (la página de datos abiertos, `web/datos.html`, PR #338), que hoy describe los conjuntos pero no sus campos.

**Evidencia de que falta.**
- `backend/routes/opendata.py:120`: `"properties": ["id", "source", "sensor", "satellite", "confidence", "frp_mw", "observed_at", "comuna"]`. Es una lista de nombres: no dice que `frp_mw` está en megavatios, que `confidence` toma los valores `alta|nominal|media|baja`, que `observed_at` es ISO 8601 en UTC, ni que `comuna` puede ser `null`.
- Lo mismo en `:128` (`level`, `level_combined`, `score`, `fwi`, `fwi_level`), `:136` (rayos: `age_s`, `energy_j`, `area_km2`), `:144` (humo), `:152` (cicatrices: `ha`, `desde`, `hasta`) y `:170` (lluvia: `hours`, `proportion`).
- `web/datos.html:75-100` imprime esa lista tal cual en la columna «Propiedades»; `web/js/datos.js` la usa para armar la tabla. Quien descarga `observations.geojson` se encuentra con `frp_mw: 12.4` y `comuna: null` sin ninguna explicación.

**Qué hacer.**
1. En `backend/routes/opendata.py`, agregar a cada conjunto una clave `fields` (lista de objetos `{name, type, unit, description}`) al lado de `properties`, que se mantiene por compatibilidad. Descripciones cortas, en español, sin jerga: `frp_mw` → «Potencia radiativa del fuego, en megavatios: cuánto calor emite el píxel»; `comuna` → «Comuna chilena donde cae el punto; null si no cae en ninguna (mar o fuera de Chile)»; `score` → «Puntaje 0-100 del 30-30-30 de BRASA»; `ha` → «Hectáreas»; `age_s` → «Segundos desde la detección».
2. Refactor mínimo: un diccionario de campos por tipo de conjunto reutilizado por los ocho constructores, para no repetir textos; sin cambiar rutas, nombres de archivos ni la forma del GeoJSON.
3. `web/datos.js` + `web/datos.html`: mostrar la descripción y la unidad en la tabla (una línea por campo, con `title` accesible) y una nota de que las fechas son UTC con ejemplo de la hora de Chile.
4. `docs/API.md`: una subsección «Diccionario de campos» con el mismo contenido (el test `tests/test_api_doc.py` exige que las rutas sigan documentadas).

**Archivos a tocar.** `backend/routes/opendata.py`, `tests/test_opendata.py`, `web/js/datos.js`, `web/datos.html`, `docs/API.md` y `CHANGELOG.md`. No toques otros endpoints, ni `backend/routes/public.py`, ni esquemas de base de datos.

**Caso de prueba concreto.** En `tests/test_opendata.py`: (a) cada conjunto del índice declara `fields` no vacío y todo nombre de `properties` aparece en `fields`; (b) `frp_mw` trae `unit == "MW"` y `comuna` explica el `null`; (c) ningún `description` está vacío ni repite el nombre del campo; (d) el índice sigue respondiendo con `properties` como lista de strings (compatibilidad).

**Criterio de listo (verificable).** `python dev.py test -k opendata` en verde con los casos nuevos; `python dev.py check` en verde; la tabla de `web/datos.html` muestra la descripción y la unidad de al menos `frp_mw`, `comuna` y `ha` (revísalo con el servidor de demo o con el e2e).

**Cierre.** Verifica con `/verificar` y entrega con `/entregar-pr`. No mergees por iniciativa propia.


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.

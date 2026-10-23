---
id: VEC-02
repo: brasas
rama: feat/mi-zona-temporada-pasada
modelo: swe-2-high
riesgo: B
archivos: web/js/views/zona.js, tests/test_zona_temporada.py, CHANGELOG.md
e2e: si
intento: 0
ronda_review: 0
---

**Objetivo.** Que en «Mi zona» cada lugar guardado muestre, con su fuente, **cómo le fue a su comuna en la temporada pasada**: cuántos incendios informó CONAF, cuánta superficie, en qué mes y cuál fue el mayor. Es la comparación que hoy no tiene ningún vecino y el dato ya está en el repositorio, sin usar.

**Ítem del backlog.** CONT-06 (más casos y cifras de la temporada) y OFI-30 (la temporada 2025-26 como dato versionado). Refuerza la regla de oro: toda cifra con su fuente y su fecha.

**Qué pasa hoy (verificado en `main` d7f2cf5).**
- `web/data/temporada-2526.json` (60 KB) existe desde OFI-30, con `source` (CSV público de GEPRIF-CONAF), `license`, `fetched_at`, `temporada: "2025-2026"`, `totales` y una lista `comunas` de objetos `{code, name, region, incendios, hectareas, mes_peak, max_ha}`.
- **Ninguna vista lo consume**: un `grep` de `temporada-2526` en `web/` y `backend/` solo devuelve el script que lo genera (`scripts/local/build_temporada_2526.py`) y su prueba (`tests/test_temporada_2526.py`). En la interfaz, la temporada pasada no aparece por ningún lado.
- `web/js/views/zona.js` pinta la tarjeta de cada lugar con las detecciones de las últimas 48 h, el viento y el 30-30-30 de la comuna, pero nada histórico.
- El resumen del lugar ya trae la comuna con su `code` (`backend/routes/personal.py:120-128` agrega `row["comuna"]` desde `comuna_code`), así que el cruce con el JSON es directo.

**Qué hacer.**
1. En `web/js/views/zona.js`, dentro de la tarjeta de cada lugar (después de la línea de riesgo, antes de los botones), un bloque corto y plegable: **«La temporada pasada en tu comuna»**. Texto en dos niveles con `dual()`: «Entre septiembre de 2025 y mayo de 2026 CONAF informó **N incendios** en <comuna>; quemaron **M ha**. El mes con más superficie fue <mes> y el mayor incendio llegó a <X> ha.» Técnico: la temporada, la comuna con su código y la fecha de los datos.
2. Cargar el JSON una sola vez por sesión con `fetch('/web/data/temporada-2526.json')`, guardado en memoria (`let cache` en el módulo), tolerante a fallos: si la petición falla o la comuna no está, **no se pinta el bloque** y la tarjeta sigue igual (nunca un texto con «0» inventado). Si `incendios` es 0, dilo: «CONAF no informó incendios en tu comuna esa temporada».
3. Fuente visible y obligatoria: «Fuente: CONAF, reporte público de incendios (GEPRIF)» con enlace a `source`, más «datos al <fetched_at>». Sin enlace, no se muestra la cifra.
4. Formato con `fmtNum` de `web/js/util.js` (miles con punto, coma decimal) y el mes en palabras (`2026-02` → «febrero»), no `2026-02`.
5. `tests/test_zona_temporada.py` (nuevo, sin navegador): guarda estática de la vista — que `zona.js` pide `/web/data/temporada-2526.json`, que usa `dual(` en el bloque, que imprime la fuente y que no escribe números literales de incendios/hectáreas (los lee del JSON). Además valida el contrato del JSON con los campos que la vista usa (`code`, `incendios`, `hectareas`, `mes_peak`, `max_ha`).

**Archivos a tocar.** `web/js/views/zona.js`, `tests/test_zona_temporada.py`, `CHANGELOG.md`. **No toques nada más**: ni `web/data/temporada-2526.json` (no lo regeneres), ni `web/css/` ni `tests/js/` (los ocupa MAPA-01), ni `backend/` (el resumen ya trae la comuna), ni el service worker.

**Criterio de listo.** `python dev.py test -k zona_temporada` en verde; `python dev.py check` en «Todo en orden»; `python dev.py e2e` en verde en 320, 390 y 1280 px (el bloque no puede cortar texto ni romper la tarjeta); con `python dev.py run --demo` y un lugar guardado en una comuna del Maule, el bloque muestra las cifras correctas del JSON y su fuente (déjalo escrito en el PR con la comuna y los números). El peso del arranque no sube: `python scripts/local/peso_arranque.py` sigue en verde.

Verifica con `/verificar` y entrega con `/entregar-pr`. No mergees por iniciativa propia.


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.

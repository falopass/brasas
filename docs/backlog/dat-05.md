---
id: DAT-05
repo: brasas
rama: feat/datos-abiertos-desde-el-indice
modelo: swe-2-high
riesgo: B
archivos: web/datos.html, web/js/datos.js, tests/test_pagina_datos.py, CHANGELOG.md, tests/test_datos_abiertos.py, tests/test_datos_ejemplos.py
e2e: si
intento: 0
ronda_review: 0
estado_desde: 2026-10-20T10:10:17
nota: Reencolado: la corrida falló por rate limit del modelo gratis, no por el ítem.
---

# Objetivo

Que la página de **Datos abiertos** explique cada conjunto en palabras simples y arme su lista de accesos **desde el índice de la API**, no a mano. Hoy la lista está escrita a mano y ya quedó incompleta, y la tabla solo repite nombres de campos.

# Ítem del backlog

Prioridad de producto de esta ronda: features que acerquen a la gente a entender los datos («datos abiertos bien explicados»). El producto publica nueve conjuntos y la página que los presenta no los explica ni los lista completos.

# Evidencia de que está pendiente

- `web/datos.html:87-96` — `<ul id="directo-lista">` lista **ocho** URLs escritas a mano y **omite `/api/opendata/scars.geojson`**, que el índice ya publica desde AGUA-01: comparar con `backend/routes/opendata.py:148-150`. Un periodista que entra por esa lista no encuentra las cicatrices de la temporada.
- `web/js/datos.js:61-79` (`fila`) pinta la fila con `id`, `url`, `params`, `geometry`, `properties` y `source`: nombres de columna crudos, sin una frase que diga qué es el conjunto ni qué no es.
- `web/js/datos.js:81-93` (`paint`) no toca `#directo-lista`: la lista queda congelada en el HTML.
- La página sí declara la regla de oro («un punto de calor no es un incendio», `datos.html:64-67`), así que el tono y el marco correcto ya existen; falta el detalle por conjunto.

# Qué hacer

1. En `web/js/datos.js`, pintar `#directo-lista` desde `idx.datasets` (un `<li><a href=…>` por conjunto, en el orden del índice). Nunca más una lista a mano.
2. Un diccionario local `PLANO` por `id` con dos frases cortas: **qué es** y **qué no es**. Cubre los ids reales del índice (`incidents`, `observations`, `risk`, `lightning`, `smoke`, `scars`, `response`, `boton-rojo`); si aparece un id desconocido, cae al `description` del índice sin romperse.
3. En `web/datos.html`: quitar los `<li>` fijos, dejar el contenedor con un texto de respaldo para cuando falle el índice, y agregar a la tabla una columna «En palabras simples» (con su `<th>`), manteniendo `lang`, `<title>`, description y el resto de la estructura como están.
4. Sin backend nuevo y sin cambiar el contrato de `/api/opendata`.

# Archivos a tocar

`web/datos.html`, `web/js/datos.js`, `tests/test_pagina_datos.py` (nuevo), `CHANGELOG.md`. **No toques nada más**: no cambies `backend/routes/opendata.py`, ni `docs/API.md` (en curso), ni `web/index.html`, ni `web/js/app.js`, ni `web/sw.js`.

# Criterio de listo (verificable)

`tests/test_pagina_datos.py` (nuevo, sin red):

- `web/datos.html` **no** contiene ninguna URL de conjunto (`/api/opendata/<algo>`) en el HTML: la lista ya no se mantiene a mano;
- el diccionario `PLANO` de `web/js/datos.js` cubre **todos** los ids que publica el índice: el test obtiene los ids del propio backend (importando la función del índice de `backend/routes/opendata.py` con el cliente de prueba de `tests/conftest.py`) y compara con las claves leídas del JS;
- si se agrega un conjunto nuevo al índice sin su frase, el test falla con el id que falta.

`python dev.py test -k pagina_datos` en verde, `python dev.py check` en verde y E2E en verde.

Verifica con `/verificar` y entrega con `/entregar-pr`. No mergees por iniciativa propia.


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.

## Unificado el 23-10-2026

Este encargo absorbe otros que pedían lo mismo sobre los mismos archivos. Además de lo de arriba, incluye:

- **DAT-04** ([original](unificados/dat-04.md)): Cada conjunto dice qué es, cada cuánto cambia y qué no se puede concluir de él, sin jerga GIS.
- **DAT-09** ([original](unificados/dat-09.md)): Quitar la lista escrita a mano (`#directo`): un solo camino por conjunto, armado desde `/api/opendata`, con un ejemplo de llamada copiable.
- **DAT-03** ([original](unificados/dat-03.md)): Cuatro recetas listas para copiar (focos de 24 h, incidentes de la semana, riesgo de hoy por comuna, humo y rayos) con botón «Copiar».

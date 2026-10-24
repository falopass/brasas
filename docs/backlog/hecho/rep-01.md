---
id: REP-01
repo: brasas
rama: feat/avisos-vecinos-cerca-al-reportar
modelo: swe-2-high
riesgo: B
archivos: web/js/ui.js, web/js/reportes.js, web/js/api.js, tests/js/reportes.test.mjs, CHANGELOG.md
e2e: si
intento: 0
ronda_review: 0
estado_desde: 2026-10-20T10:10:17
nota: Reencolado: la corrida falló por rate limit del modelo gratis, no por el ítem.
---

## Objetivo

Que quien va a reportar humo o fuego vea **antes de enviar** si un vecino ya reportó lo mismo cerca, y entienda que su aviso se sumará como testigo en vez de crear un reporte suelto.

## Problema (qué ve hoy el usuario)

El formulario «Reportar humo o fuego» (`web/js/ui.js:449`) abre con el aviso de llamar al 130/132 y nada más: no muestra si en los últimos días hubo avisos en el mismo punto. El servidor ya resuelve la duplicación —`backend/reports.py:31-32` define `DUPLICATE_HOURS = 3` y `DUPLICATE_KM = 1.5`, y el PR #352 agregó la corroboración «N vecinos lo vieron»—, pero esa información **solo aparece después**, cuando el vecino cree que su reporte se perdió: dos personas que ven la misma columna de humo mandan dos formularios completos y ninguna sabe de la otra. En una emergencia real eso es tiempo y desconfianza.

Hay material para hacerlo bien y sin backend nuevo: `GET /api/reports` (`backend/routes/community.py:232`) ya devuelve los reportes verificados de las últimas 72 h con `lat`, `lon`, `kind_label`, `status_label`, `comuna` y `corroboraciones` (`_public`, `community.py:213-230`). El cliente no tiene método para pedirlo (`web/js/api.js:120` solo tiene `createReport`), y `web/js/reportes.js` ya sabe formatear la fila (`line`, línea 28) y el contador de testigos (`testigos`, línea 21).

## Qué hacer

1. **`api.js`**: agrega `reports: (hours = 72) => request('/api/reports?hours=' + hours)`. Nada más en ese archivo.
2. **`reportes.js`** (funciones puras, sin DOM):
   - `cercanos(reports, lat, lon, km = 2)` → los reportes a menos de `km`, ordenados del más nuevo al más viejo y con la distancia incluida (reusa `haversineKm` de `web/js/util.js:62`).
   - `resumenCercanos(reports, lat, lon)` → texto corto en español de vecino: «Un vecino reportó humo a 700 m hace 40 min (en revisión)»; con dos o más, «2 vecinos reportaron…»; si hay verificados, dilo con la palabra «verificado».
3. **`ui.js`** (`reportForm`, línea 449): al abrir con punto conocido o cuando el usuario elige ubicación, pide los reportes en segundo plano; si hay cercanos, inserta un bloque **antes** del botón «Enviar reporte» con hasta 3 filas y esta frase: «Si es el mismo hecho, tu aviso se suma como testigo; no hace falta otro formulario». Sin conexión o si la consulta falla, el bloque simplemente no aparece (nada de errores que asusten).
4. **`tests/js/reportes.test.mjs`**: casos de `cercanos` (dentro/fuera del radio, orden, lista vacía o `null`, coordenadas inválidas) y de `resumenCercanos` (singular/plural, con y sin verificado, antigüedad).

## Archivos

`web/js/ui.js`, `web/js/reportes.js`, `web/js/api.js`, `tests/js/reportes.test.mjs`, `CHANGELOG.md`. No toques nada más: no cambies el backend, no cambies el envío del reporte ni la cola sin conexión (`outbox`), y no toques las vistas.

## Criterio de listo

- `node --test tests/js/reportes.test.mjs` en verde (con los casos nuevos).
- `python dev.py check` en verde y `python dev.py e2e` en verde.
- En `dev.py run --demo`, con al menos un reporte verificado sembrado cerca de un punto, el formulario muestra el bloque con la distancia y la antigüedad; con la red cortada, el formulario abre igual y sin bloque.

Verifica con `/verificar` y entrega con `/entregar-pr`. No mergees por iniciativa propia.


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.

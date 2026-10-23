---
id: RISK-22
repo: brasas
rama: feat/mi-zona-semana-pasada
modelo: swe-2-high
riesgo: B
archivos: web/js/views/zona.js, tests/js/zona.test.mjs, CHANGELOG.md
e2e: si
intento: 0
ronda_review: 0
estado_desde: 2026-10-20T10:10:17
nota: Reencolado: la corrida falló por rate limit del modelo gratis, no por el ítem.
---

# Objetivo

Que en **Mi zona** —la pantalla que un vecino abre todos los días— cada lugar guardado muestre si el pronóstico de su comuna **empeoró o mejoró respecto de hace una semana**, en una frase, con el detalle plegado. Hoy esa comparación solo existe en la vista Riesgo, a la que hay que ir comuna por comuna.

# Ítem del backlog

Prioridad de producto de esta ronda: «lo que acerque a un vecino a entender su riesgo hoy (… comparación con la semana pasada)». El endpoint ya existe y está probado; falta llevarlo a la pantalla principal.

# Evidencia de que está pendiente

- `web/js/views/riesgo.js:328-332` — la vista Riesgo ya muestra «¿Y la semana pasada?» con `/api/risk/{code}/trend`, `trendHeadline` y `trendLine`.
- `web/js/views/zona.js:206-238` (`placeCard`) y `:162-184` (`placeBody`) muestran radar, viento, aviso DMC, clima de hoy y la tira de 7 días: **nada de la semana pasada**.
- `web/js/views/zona.js:317-326` (`render`) pide `api.placeSummary` y `api.placeHistory` por lugar; nunca `api.riskTrend`.
- `web/js/api.js:97` ya expone `riskTrend(code, weeks)`.
- `backend/trend.py:1-8` y `backend/routes/public.py:541-566` documentan el matiz que hay que respetar: compara **dos pronósticos para el mismo día** emitidos con siete días de diferencia («mide cómo cambió la expectativa, no lo que pasó en el cerro»). El texto no puede decir que «hubo» ni que «habrá» fuego.

# Qué hacer

1. En `render` (`zona.js:317-326`), por cada lugar **con comuna**, sumar `api.riskTrend(place.comuna.code).catch(() => null)` al `Promise.all` y guardar el resultado en un `Map` paralelo (mismo patrón que `summaries` y `histories`).
2. Una **función pura exportada** `weekLine(trend)` en `zona.js` que devuelva:
   - `''` si no hay `rows` o si **todas** las filas son `sin_anterior` (no se inventa comparación);
   - una frase corta con los conteos de `trend.summary` («El pronóstico de tu comuna para los próximos días subió en 2 días y bajó en 1 respecto de hace una semana»), usando palabras de pronóstico, nunca de hecho;
   - el `method` como nota al pie en el detalle plegado.
3. Insertarla en `placeCard` (después de `dayStrip`), como `<details class="fold">` con un `<summary>` legible, y **no** mostrarla cuando el lugar no tiene comuna (fuera de una comuna conocida).
4. Si la consulta del trend falla, la tarjeta sigue igual: es un extra, nunca un error visible.

# Archivos a tocar

`web/js/views/zona.js`, `tests/js/zona.test.mjs`, `CHANGELOG.md`. **No toques nada más**: no cambies `web/js/views/riesgo.js` (en curso), ni `backend/routes/public.py`, ni `backend/trend.py`, ni `web/js/trendview.js`, ni agregues suites nuevas a `tests/js/` (el índice está en curso: extiende `zona.test.mjs`, que ya existe).

# Criterio de listo (verificable)

Extiende `tests/js/zona.test.mjs`:

- `weekLine(null)` → `''`, y `weekLine({rows: []})` → `''`;
- todas las filas `sin_anterior` → `''`;
- `summary: {sube: 2, baja: 1, igual: 2, sin_anterior: 0}` → la frase menciona 2 y 1 y **no** contiene «hubo» ni «habrá»;
- sin `summary` pero con filas mixtas no revienta;
- el texto pasa por `html`/escape como el resto de la vista.

`node --test tests/js/` en verde, `python dev.py check` en verde y E2E en verde.

Verifica con `/verificar` y entrega con `/entregar-pr`. No mergees por iniciativa propia.


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.

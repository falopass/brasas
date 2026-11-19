---
id: PERF-15
repo: brasas
rama: perf/mapa-pinta-primero
modelo: agente-alto
riesgo: A
archivos: web/js/app.js, web/js/views/riesgo.js, web/js/views/casos.js, CHANGELOG.md
e2e: si
---

# PERF-15 · Riesgo e Historia pintan antes de que llegue el motor del mapa

## Objetivo

Que `#/riesgo` y `#/casos` dejen de esperar la descarga e interpretación de
maplibre-gl.js (~1 MB) para pintar su panel. Auditoría del BRASA Lead (19-11-2026):
ambas vistas sacaban Lighthouse móvil 0,41–0,42 con TBT ~5,8 s porque `route()`
hacía `await ensureMap()` antes del `mount`.

## Contexto

- `route()` (web/js/app.js) esperaba el motor para todas las `MAP_VIEWS`; en
  `#/riesgo?comuna=X` y `#/casos/<id>` (enlaces directos) el primer pintado quedaba
  detrás de ~10 s de arranque del motor bajo throttling de Lighthouse.
- `map.js` ya está preparado para motor diferido: `setData`/`show` guardan estado y
  lo repiten al cargar el estilo, y `onReady(fn)` encola callbacks hasta que el estilo
  está listo (o dispara al instante si ya cargó).
- `riesgo.js` llamaba `getMap().on('click', …)` sin protección (rompía sin motor) y
  `casos.js` hacía `fitBbox` de una sola vez (se perdía si el motor no estaba).

## Cambio

- `web/js/app.js`: `MAP_PINTA_PRIMERO = {'riesgo', 'casos'}`; para esas vistas
  `route()` pide `ensureMap()` sin esperarla (en el arranque en frío ya corre en
  paralelo desde `main()`) y monta el panel de inmediato. `#/mapa`, `#/incendio` y
  `#/v` siguen esperando el motor como antes.
- `web/js/views/riesgo.js`: encuadre inicial y clics sobre `risk-fill` pasan por
  `onReady` con guardas `mounted`/`mountSeq` (un remontaje rápido no duplica
  listeners); `unmount` limpia el handler solo si existe y con `getMap()?.`.
- `web/js/views/casos.js`: el encuadre del catálogo y el del caso abierto pasan por
  `onReady` (con `mounted`/`openSeq` en el caso); el resto (setData/show, globo,
  reproducción) sigue igual.
- Compensación de peso (pedido del BRASA Lead, 19-11-2026): el cambio sumaba ~737 B
  gzip sobre `main` tras el rebase (incluye #932), así que el mismo PR recorta
  comentarios que repetían el código en `app.js` y `casos.js` (mismo sentido, menos
  palabras). Neto final medido: +219 B gzip total y −308 B bloqueante sobre `main`
  (355 848 vs 355 629 B; tope total 348 KB); los topes no se mueven.

## Criterio de listo

- `#/riesgo` y `#/casos` pintan título y contenido sin esperar el motor; el mapa
  aparece cuando el motor está listo, con el encuadre correcto (comuna pedida,
  catálogo o caso).
- Clics en el mapa de Riesgo y encuadre de caso funcionan igual que antes cuando el
  motor está listo; sin motor (fallo de carga) la vista sigue usable en panel.
- Lighthouse móvil antes/después en producción: LCP y TTI mejoran en ambas rutas;
  TBT no empeora (el motor se parsea igual, solo que ya no bloquea el primer pintado).
- CI en verde (e2e de Riesgo/Historia); presupuestos de peso dentro de los topes
  vigentes, sin mover umbrales.

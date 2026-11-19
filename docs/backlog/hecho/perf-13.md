---
id: PERF-13
repo: brasas
rama: perf/zona-una-pintada
modelo: agente-alto
riesgo: A
archivos: web/js/store.js, web/js/app.js, web/js/views/zona.js, CHANGELOG.md
e2e: si
---

# PERF-13 · «Mi zona» pinta una sola vez en el arranque

## Objetivo

Que la portada pinte una sola vez al abrir la app: hoy pinta primero con `places` vacío
(estado «Agregar mi casa», aunque la persona tenga lugares guardados) y después otra vez
con los lugares reales, y cada pintada vuelve a pedir `me`, `alerts` y un resumen por
lugar. En la red de Lighthouse móvil se ven `/api/me` y `/api/alerts` duplicados en cada
arranque.

## Contexto

- Auditoría del BRASA Lead (19-11-2026): Lighthouse móvil de producción después de
  PERF-12. `#/mi-zona` seguía con LCP ~3,2–4,4 s y el 85 % del tiempo era «render delay»:
  el titular no pinta hasta que `render()` resuelve `me` + `alerts` + resúmenes.
- `mount()` llama `await render(container)` sin saber si los lugares ya llegaron:
  `refreshPlaces()` (en `app.js`) corre en paralelo al montaje y `store.set` avisa siempre,
  así que el evento `places` dispara un segundo `render()` completo.
- Los repintados por `status`, `observations` y `visibilitychange` tenían la misma carrera:
  podían pintar el estado vacío antes de que llegaran los lugares.

## Cambio

- `web/js/store.js`: estado `placesReady` (false al arrancar).
- `web/js/app.js`: `refreshPlaces()` marca `placesReady` al terminar, en éxito y en error
  (el `catch` deja `places` en `[]`, así el evento siempre llega).
- `web/js/views/zona.js`: en el primer arranque `mount()` no llama `render()`; el primer
  pintado real lo dispara el evento `places`. Los repintados por `status`, `observations`
  y `visibilitychange` esperan a `placesReady`. Al volver a la vista con los lugares ya
  listos se pinta al montar, igual que antes.

## Criterio de listo

- Una sola llamada a `/api/me` y `/api/alerts` por arranque en «Mi zona» (antes dos).
- Quien tiene lugares guardados no ve el estado vacío «Agregar mi casa» en el primer
  pintado; quien no tiene lugares ve el estado vacío una sola vez, como antes.
- Sin conexión (el `catch` de `refreshPlaces`) la vista pinta igual.
- CI en verde, incluido el e2e de «Mi zona»; presupuestos de peso intactos
  (`PRESUPUESTO_ARRANQUE_KB` 175 KB; total dentro de 346 KB).

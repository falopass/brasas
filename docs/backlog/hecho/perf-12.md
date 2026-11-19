---
id: PERF-12
repo: brasas
rama: perf/mapa-arranque-movil
modelo: agente-alto
riesgo: A
archivos: web/js/app.js, scripts/local/peso_arranque.py, CHANGELOG.md
e2e: si
---

# PERF-12 · En teléfonos, el motor del mapa espera la primera interacción

## Objetivo

Que en un teléfono el motor del mapa (MapLibre, ~1 MB de JS + WebGL) no se descargue ni se
parsee mientras la persona lee «Mi zona», «Avisos» o cualquier vista que no es el mapa: el
calentamiento en reposo le robaba el hilo principal a la primera pantalla (Lighthouse móvil
en producción medía 3,3–16,9 s de bloqueo total y TTI de hasta 28,6 s). En escritorio no
cambia nada.

## Contexto

- Auditoría pedida por el BRASA Lead (19-11-2026): Lighthouse móvil de las vistas que no son
  el mapa contra producción. `bootup-time` mostraba `maplibre-gl.js` dominando el hilo
  principal en todas las rutas de la app.
- `app.js` ya tenía dos políticas: `ensureMapIdle()` (calentar en `requestIdleCallback` en
  todas las vistas) y `ensureMapTrasPintar()` (MOV-01: en «Mi zona» con ahorro de datos o red
  2G/3G espera el toque o ~8 s). Ninguna cubría el teléfono con buena red.
- La portada «Mi zona» sí tiene mapa (`zona.js` usa `getMap`/`onReady`), así que el motor se
  sigue pidiendo siempre: solo cambia cuándo.

## Qué se hizo

- `web/js/app.js`: `calentarMapa(forzar)` decide el momento del calentamiento. En puntero
  táctil (`pointer: coarse` o `maxTouchPoints > 0`) o cuando `forzar` está activo (MOV-01,
  red lenta), el motor espera la primera interacción (`pointerdown`/`keydown` en `document`)
  o ~8 s, lo que llegue primero. En escritorio y sin red lenta sigue `ensureMapIdle()`.
- `ensureMapTrasPintar()` (Mi zona) delega en `calentarMapa(lenta)`: la espera por red lenta
  se conserva igual en escritorio.
- Las demás vistas que no son de mapa (`alertas`, `preparate`, `temporada`, `calidad`,
  `privacidad`, `quehago`, `mas`) pasan por el mismo `calentarMapa()`.
- `scripts/local/peso_arranque.py`: el bloqueante queda en 162,6 KB (tope 175 intacto); el
  total queda en 345,7 KB, dentro del tope 346 vigente (MAPA-193), sin mover presupuestos.
- Corrección de Devin Review: `comunas-index.json` (11 KB gzip) dejó de pedirse dentro del
  `onload` del motor y ahora viaja solo, en un momento libre del arranque
  (`cargarIndiceComunas`), porque en teléfonos el motor se difiere y el formulario de
  lugares (`ui.js placeForm`) lo leía vacío al abrirse antes que el mapa; además
  `placeForm` lee el índice al usarlo (`comunas()`), no al abrir el formulario.
- Ajuste del e2e (`scripts/local/browser_checks.py`): «toque y ficha» en «Mi zona»
  (@390 táctil) reintenta proyectar el punto hasta ~30 s, porque el motor diferido puede
  llegar después del instante fijo en que antes se exigía (comportamiento previsto).
- Corrección de Devin Review (selección de comuna sin ajuste de pin): `pickOnMap` (`ui.js`)
  ahora pide y espera el motor (`ensureMap`, exportado desde `app.js` e importado de forma
  dinámica para no crear ciclo) antes de abrir el pin; el handler de comuna en `placeForm`
  espera al motor para `fitBbox(c.bbox)` antes de llamar a `pickOnMap`. Cubre también
  «Marcarlo en el mapa», el reporte de «lo que viste» y «Cerca».

## Criterio de listo

- `scripts/local/peso_arranque.py` en verde; `node --check web/js/app.js` sin errores.
- CI del PR en verde con revisión de navegador.
- Tras el deploy, Lighthouse móvil de `#/mi-zona` y `#/alertas` en producción muestra menos
  tiempo de hilo bloqueado por `maplibre-gl.js` que la línea base (mi-zona 43 / alertas 46
  de rendimiento, TBT 3,3 s / 16,9 s).

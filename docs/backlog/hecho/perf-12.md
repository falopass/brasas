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
- `scripts/local/peso_arranque.py`: el bloqueante queda en 162,1 KB (tope 175 intacto); el
  total sube 0,2 KB por el cambio en `app.js` y `PRESUPUESTO_TOTAL_KB` pasa de 345 a 346
  con la justificación fechada (convención del script).

## Criterio de listo

- `scripts/local/peso_arranque.py` en verde; `node --check web/js/app.js` sin errores.
- CI del PR en verde con revisión de navegador.
- Tras el deploy, Lighthouse móvil de `#/mi-zona` y `#/alertas` en producción muestra menos
  tiempo de hilo bloqueado por `maplibre-gl.js` que la línea base (mi-zona 43 / alertas 46
  de rendimiento, TBT 3,3 s / 16,9 s).

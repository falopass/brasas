---
id: MAPA-192
repo: brasas
rama: perf/mapa-debug-medicion
modelo: agente-alto
riesgo: A
archivos: web/js/map.js, tests/js/map.test.mjs, docs/backlog/README.md, CHANGELOG.md
e2e: no
---

# MAPA-192 · Medición de depuración del mapa apagada por defecto

## Objetivo

Que la medida de «focos dibujados» de `refreshDetections()` (`map.queryRenderedFeatures` + `console.debug` en cada `idle`) solo corra con depuración activa, para no pagar un readback de GPU por pan/zoom en producción (avance de PERF-10, que sigue abierto).

## Contexto

- `web/js/map.js` registraba `map.once('idle', …)` en cada recarga de focos solo para escribir en consola la medida de MAPA-01. `queryRenderedFeatures` fuerza a MapLibre a leer píxeles renderizados: costo real en teléfonos modestos, sin beneficio para las personas.
- Depuración explícita: `?debug=1` en la URL o `localStorage` «brasa:debug-mapa» = 1, vía `debugMapa()` exportada y probada en `tests/js/map.test.mjs`.
- Aprovecha el mismo PR para indexar en `docs/backlog/README.md` el encargo MAPA-191, que quedó en `hecho/` sin entrada.

## Archivos

- `web/js/map.js` (`debugMapa()` + guarda en `refreshDetections()`)
- `tests/js/map.test.mjs` (pruebas del flag)
- `docs/backlog/README.md` (entradas tachadas de MAPA-191 y MAPA-192)
- `CHANGELOG.md`

## Criterio de listo

Sin `?debug=1` ni la clave en `localStorage`, `refreshDetections()` no registra el listener de `idle` ni llama a `queryRenderedFeatures`; con depuración activa el mensaje de consola sigue saliendo igual. CI en verde (pytest, revisión JS y e2e).

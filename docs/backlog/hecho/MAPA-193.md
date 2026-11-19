---
id: MAPA-193
repo: brasas
rama: perf/mapa-latido-tactil
modelo: agente-alto
riesgo: A
archivos: web/js/map.js, tests/js/mapa-latido.test.mjs, docs/backlog/README.md, CHANGELOG.md
e2e: no
---

# MAPA-193 · Latido del mapa a cadencia reducida en pantallas táctiles

## Objetivo
Bajar de forma medible el TBT del mapa en gama media sin cambiar lo que se ve: en dispositivos con puntero táctil el latido de los focos recientes repinta el mapa a ~10 fps en vez de ~30 fps.

## Contexto
- El frente Android midió en `#/mapa` (Lighthouse móvil, gama media con throttling): score 0,38 y TBT ~80 s, con las tareas largas dentro de `maplibre-gl.js` (dado del Lead, 19-nov-2026).
- `pulse()` (web/js/map.js) repinta las capas `detections-pulse`/`detections-pulse2` cada 33 ms mientras el latido está vigente (datos de hace <20 s o interacción reciente): cada repintado es un re-render completo del estilo (~40 capas + teselas vectoriales), la principal fuente de tareas largas bajo throttling de CPU.
- El latido es ambiente (período de 2,2 s, se abre y se apaga): a 10 fps se sigue viendo igual de vivo; con ratón (escritorio) se mantiene a ~30 fps.

## Archivos
- `web/js/map.js`: `cadenciaLatidoMs(coarse)` (100 ms táctil / 33 ms ratón) usada por `pulse()`.
- `tests/js/mapa-latido.test.mjs`: prueba de la cadencia.

## Criterio de listo
- CI en verde; medición TBT antes/después en prod con el mismo método (Playwright, viewport 390×844, CPU 4x) documentada en el PR.

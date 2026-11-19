---
id: MAPA-194
repo: brasas
rama: perf/mapa-pixelratio-tactil
modelo: agente-alto
riesgo: A
archivos: web/js/map.js, tests/js/map.test.mjs, docs/backlog/README.md, CHANGELOG.md
e2e: no
---

# MAPA-194 · Lienzo del mapa a pixelRatio 2 en pantallas táctiles

## Objetivo
Bajar de forma medible el TBT residual del mapa en gama media sin cambiar lo que se ve de forma perceptible: en dispositivos con puntero táctil el lienzo de MapLibre se pinta a pixelRatio 2 aunque el teléfono reporte 3.

## Contexto
- Línea base Android tras #920 y #922 (dado del Lead, 19-nov-2026): gama media score 0,39, TBT 76,9 s, TTI 92,0 s, LCP 6,5 s, 20 long tasks que suman 17,9 s (la más larga 2,5 s), main thread «other» 82,4 s; gama baja (CPU 6x, 3G lenta): score 0,38, TBT 14,0 s. El TBT residual lo domina el render de teselas/estilo de MapLibre.
- `initMap()` (web/js/map.js) crea el mapa sin `pixelRatio`: MapLibre usa el `devicePixelRatio` completo del equipo; en gama media con dpr≈3 cada repintado del estilo pinta ~2,25 veces más píxeles que a dpr 2.
- El latido ya bajó su cadencia (MAPA-193) y DEM/GIBS/comunas ya cargan en diferido; el costo que queda es el render en sí.

## Archivos
- `web/js/map.js`: `pixelRatioMapa(coarse, dpr)` usada por `initMap()`.
- `tests/js/map.test.mjs`: prueba del pixelRatio.

## Criterio de listo
- CI en verde; medición TBT antes/después en prod con el mismo método (Playwright, viewport 390×844 con dpr 3, CPU 4x) documentada en el PR y en la línea base Android del Lead.

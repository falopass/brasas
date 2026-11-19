---
id: MAPA-195
repo: brasas
rama: perf/mapa-estilo-zoom6
modelo: agente-alto
riesgo: A
archivos: web/js/map.js, docs/backlog/README.md, CHANGELOG.md
e2e: no
---

# MAPA-195 · Los tintes de suelo del basemap no se evalúan a escala país

## Objetivo
Bajar el costo de repintado del estilo en `#/mapa` a zoom de país: los rellenos de landcover (bosque, pradera) y landuse urbano de OpenFreeMap no aportan de forma perceptible a zoom 4-5 y se evalúan en cada repintada del arranque.

## Contexto
- Auditoría MAPA-195 (prod, Playwright móvil 390×844 dpr 3, CPU 4×): la carga de red es pequeña (6 teselas OMT, 3 glifos, regiones.geojson, sin DEM/GIBS al inicio); los long tasks se concentran en los primeros ~30 s (carga + repintadas por teselas entrantes).
- Línea base TBT propio tras MAPA-194: 12.031 ms/60 s; ventana de 45 s con auditoría: 10.047 ms. Línea base Android del Lead: TBT 76,9 s, «other» 82,4 s.
- `baseStyle()` pinta `landcover-wood`, `landcover-grass` y `landuse-urban` sin `minzoom`: a escala país (zoom 4,6 inicial) son tintes de opacidad 0,5-0,8 sobre todo Chile, evaluados en cada repintada.

## Archivos
- `web/js/map.js`: `minzoom: 6` en las tres capas de tinte de suelo (aparecen al acercarse, donde sí se distinguen).

## Criterio de listo
- CI en verde; medición TBT antes/después en prod con el mismo método (Playwright, 45 s) documentada en el PR.

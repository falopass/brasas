---
id: MAPA-198
titulo: El latido de los focos duerme a los 10 s para bajar la ráfaga del sondeo
estado: hecho
riesgo: A
archivos: web/js/map.js, docs/backlog/README.md, CHANGELOG.md
e2e: no
---

# El latido de los focos duerme antes

## Encargo
Ronda del mapa (Lead, 22-nov): la ráfaga de ~10-20 s al 99 % del hilo cada sondeo de
observaciones (120 s) en gama media tiene evidencia y vale la ronda; ciclo completo con
medición antes y después en prod.

## Qué se midió (prod, Playwright 390×844 dpr 3, CPU 4×, TaskDuration CDP)
- La serie temporal en `#/mapa` no muestra ráfaga en cada sondeo: solo cuando el poll
  trae datos nuevos (GOES/VIIRS). En esas actualizaciones el latido despierta y repinta
  el mapa entero a ~10 fps (cadencia táctil de MAPA-193) durante toda la ventana de
  reposo (`LATIDO_REPOSO_MS` = 20 s): ~99,5 % del hilo.
- Sonda determinista (`/tmp/latido_toque.py`): un toque en el lienzo despierta el mismo
  ciclo; antes del cambio, busy ~99,5 % durante ~20 s y caída a ~0-5 % después.

## Qué se hizo
`web/js/map.js`: `LATIDO_REPOSO_MS` baja de 20 s a 10 s. El latido sigue latiendo ~4,5
ciclos (período 2,2 s) tras cada dato nuevo o toque —se percibe igual de vivo— y cada
sondeo con datos nuevos lo vuelve a despertar; el modo ahorro y
`prefers-reduced-motion` no cambian.

## Verificación
- Las pruebas del latido (`tests/js/mapa-latido.test.mjs`) usan la constante de forma
  simbólica; el CI las corre.
- Antes/después en prod con `/tmp/latido_toque.py` tras el deploy.

## Riesgo
A: misma animación, cambia solo cuánto dura despierta tras la última actividad; con
datos nuevos frecuentes (temporada) se rearma solo.

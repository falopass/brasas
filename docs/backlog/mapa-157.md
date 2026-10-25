---
id: MAPA-157
repo: brasas
rama: feat/toque-y-ficha
modelo: swe-2-max
riesgo: M
archivos: web/js/map.js, web/js/capas.js, web/js/popup.js, web/js/views/mapa.js, web/js/views/zona.js (solo el registro del toque), tests/js/toque.test.mjs, scripts/local/browser_checks.py, CHANGELOG.md
e2e: si
intento: 0
depende: PR #739 mergeado (crea web/js/popup.js)
---

# MAPA-157 · Un toque, un solo resultado (con margen para el dedo)

**Qué pasa hoy y por qué está mal.**
1. `bindMap()` de `web/js/views/mapa.js` registra 11 `map.on('click', capa, fn)` independientes. MapLibre los dispara **todos** cuando el toque cae sobre varias capas; cada uno cierra el popup anterior y abre el suyo, así que gana el último registrado:
   - Con «Peligro», «Lluvia», «SENAPRED» o «Cicatrices» encendidas, tocar un foco o un aviso de vecino abre la ficha **de la comuna**.
   - Un punto VIIRS dentro de un cuadro GOES abre la ficha del cuadro GOES.
   - El anillo de un incidente navega a su ficha y, a la vez, la celda debajo hace zoom.
2. Un foco suelto mide 2,6–5 px de radio, más la escala por FRP (`frpSize`/`detRadius` en `web/js/map.js`): entre 8 y 16 px de diámetro en pantalla. El clic se resuelve en el punto exacto, así que con el dedo cuesta acertarle. La guía es 44 px (iOS) y 24 px como mínimo (WCAG 2.5.8).

**Qué hacer.**
1. **Un solo listener en `map.js`**, registrado una vez en `initMap()`: `map.on('click', resolverToque)`.
   - Si `document.body.classList.contains('picking')`, no hace nada (el flujo de MAPA-161 maneja ese toque).
   - Radio de tolerancia: 12 px con `matchMedia('(pointer: coarse)')` y 4 px con mouse.
   - `map.queryRenderedFeatures([[x-r, y-r], [x+r, y+r]], { layers })`, donde `layers` son solo las capas registradas que existen en el estilo (las ocultas no se dibujan y no aparecen).
   - Cada candidato es `{ capa, feature, distPx }`. En geometrías `Point`, `distPx` es la distancia en píxeles entre `e.point` y `map.project(coords)`; en polígonos vale 0.
   - Gana el que devuelva `elegirObjetivo(candidatos)`, y se llama a su `abrir(feature, e.lngLat, e)`.
   - Si no hay candidatos, emite `document.dispatchEvent(new CustomEvent('brasa:toque-vacio'))`. MAPA-158 lo usa para cerrar la ficha.
2. **Función pura `elegirObjetivo(candidatos)` en `web/js/capas.js`**, que ya es «lógica pura, sin DOM».
   - Exporta también `PRIORIDAD_TOQUE`, de menor a mayor número:
     - 0: `official`, `reports`
     - 1: `detections` (foco suelto), `lightning`, `services`, `places`
     - 2: `celda` (una feature de `detections` con `count > 1`), `incident-rings`
     - 3: `goes-pixels`
     - 4: `scars-fill`, `incident-hulls-fill`
     - 5: `risk-fill`, `rain-fill`, `senapred-fill`
     - Cualquier otra capa: 9.
   - Orden: prioridad y después `distPx`. Sin candidatos devuelve `null`.
3. **API para las vistas**, en `map.js`: `export function registrarToque(capa, abrir)`, que devuelve la función `soltar()`.
   - El cursor de puntero (escritorio) aparece solo sobre capas registradas. Reemplaza la lista fija de `mouseenter`/`mouseleave` de `initMap()`, que hoy pone la mano sobre capas que no abren nada (`places`, `case-points`, `explore`).
4. **Migrar las vistas.**
   - `views/mapa.js`: `bindMap()` usa `registrarToque` para cada capa y `unmount()` llama a todos los `soltar()`.
   - `views/zona.js`: **solo** las líneas del toque. El listener de PR #739 sobre `['detections','goes-pixels']` pasa a dos `registrarToque`, y se sueltan en `unmount()`.
   - `views/riesgo.js` queda igual: maneja `risk-fill` por su cuenta, y en esa vista no hay nada registrado.
5. Se mantiene lo que ya hace cada capa: la celda acerca el mapa, el anillo abre `#/incendio/<id>`, y cada popup muestra su contenido.

**Prueba (Node).** En `tests/js/toque.test.mjs`, `elegirObjetivo` debe cumplir:
- Una comuna (`risk-fill`) y un foco a 6 px: gana el foco.
- Un cuadro GOES y un punto VIIRS: gana el VIIRS.
- Una celda y un anillo: gana el de menor distancia.
- CONAF y un foco: gana CONAF.
- Lista vacía: `null`.

**Prueba en navegador** (`browser_checks.py`, 390 px, demo sembrada):
- Datos de la demo: el incidente de Quilpué tiene focos en `lat -33.06 - i*0.004, lon -71.42 + i*0.003` y CONAF está en `-33.07, -71.41`.
- Toma el mapa con `await import('/web/js/map.js')` y `getMap()` dentro de `page.evaluate`, sin globales nuevas.
- Proyecta un foco lejos de CONAF y haz clic 8 px al lado: se abre su ficha.
- Con la capa «Peligro» encendida, repite el clic: sigue abriéndose la ficha del foco, no la de la comuna.

**Criterio de listo.** Las dos pruebas pasan en el CI; ninguna capa abre dos fichas con un solo toque; el teclado y las capas del e2e siguen en verde.

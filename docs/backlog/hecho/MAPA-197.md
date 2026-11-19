---
id: MAPA-197
titulo: El globo 3D pinta bajo demanda y no gasta hilo quieto
estado: hecho
riesgo: A
archivos: web/js/globe.js, tests/js/globe.test.mjs, docs/backlog/README.md, CHANGELOG.md
e2e: no
---

# El globo 3D pinta bajo demanda

## Encargo
Ronda del mapa (Lead, continuación de MAPA-196): un globo quieto que ocupa el 100 % del
hilo gasta batería en cualquier teléfono. Modo bajo demanda del render, con la misma
medición antes y después, verificando que focos, huella y vuelo de cámara sigan
actualizando.

## Qué se midió (local estático, Playwright 390×844 dpr 3, CPU 4×, TaskDuration CDP)
- Antes (bucle por defecto de Cesium): globo quieto al 99,8 % del hilo principal; al
  volver del vuelo a zoom cercano el render seguía al ~88–99 % aunque `tilesLoaded`
  quedara en `true` y no hubiera más peticiones de teselas (ni `requestRender` ni
  `_renderRequested` ni cambios de cámara: el `requestRenderMode` de Cesium 1.145 no
  logra dormir esta escena).
- Después (render manual bajo demanda): quieto al 0,7 %; arrastre, vuelo de cámara y
  `updateGlobe` (focos y huella) siguen pintando cuadro a cuadro.

## Qué se hizo
`web/js/globe.js`: el visor se crea con `useDefaultRenderLoop: false` y el módulo
pinta solo cuando hay trabajo (`kickRender`): interacción del gesto (pointer/wheel,
300 ms de cola), vuelo de cámara (2 s) y llegada de teselas (`!globe.tilesLoaded`, con
tope de 120 s). `updateGlobe` pide un cuadro por llamada, así los focos y la huella se
siguen actualizando (incluida la reproducción de la línea de tiempo). Oculto o con la
pestaña en segundo plano no se agenda nada (MAPA-196 se conserva).

## Verificación
- `node --test tests/js/globe.test.mjs`: 20/20.
- Medición local antes/después con `/tmp/globo_demanda.py` y `/tmp/globo_asienta.py`;
  el después en prod se completa tras el deploy con la misma corrida.

## Riesgo
A: mismo contenido, cambia solo cuándo se pinta. Si una actualización de Cesium
llegara sin disparar interacción, vuelo ni carga de teselas, el cuadro esperaría al
próximo gesto; los caminos que usa la app (focos, huella, vuelo, gestos) están cubiertos.

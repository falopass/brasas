---
id: MAPA-164
repo: brasas
rama: feat/controles-mapa-movil
modelo: swe-2-max
riesgo: M
archivos: web/js/views/mapa.js, web/js/map.js (solo BASEMAPS), web/css/app.css (bloque /* MAPA-164 */), web/preguntas.html, docs/FUENTES.md, tests/js/map.test.mjs, scripts/local/browser_checks.py, CHANGELOG.md
e2e: si
intento: 0
depende: Ola 2 mergeada
---

# MAPA-164 · Controles del Mapa pensados para el celular

**Qué pasa hoy y por qué está mal.**
1. Los filtros que cambian el mapa («6 h · Hoy · 2 días · Semana» y «Ocultar los dudosos») viven **en la hoja**. En el celular la vista Mapa abre en `peek` y esos filtros quedan bajo el pliegue.
2. Las 13 capas aparecen **dos veces**: en el control flotante «Capas» y en la lista «Qué mostrar en el mapa» del panel.
3. El control flotante es un `<details>` largo que tapa medio mapa.
4. El buscador de comunas está escondido dentro de «Capas».
5. Hay **dos cosas llamadas «Relieve»**: el fondo OpenTopoMap (`BASEMAPS.topo` en `web/js/map.js`) y la capa de sombreado de Mapterhorn (MAPA-155).

**Qué hacer.**
1. **Fila de chips sobre el mapa** en el celular, bajo la barra superior y sin tapar «Mi ubicación»: «6 h · Hoy · 2 días · Semana» y «Solo los más seguros».
   - Usan el mismo estado que hoy (`obsHours`, `obsFilter.reliable`) y siguen cargando las observaciones y los incidentes como ahora.
   - Con `aria-pressed`, 44 px de alto y desplazamiento horizontal si no caben.
   - En escritorio pueden quedar en el panel como hoy.
2. **«Capas» como hoja agrupada** en el celular:
   - Fuego: focos, CONAF, huellas, rayos.
   - Contexto: peligro, lluvia, SENAPRED, humo, cicatrices, viento, relieve.
   - Tú: mis lugares, avisos de vecinos.
   - Arriba, el fondo (Mapa · Satélite · Topográfico).
   - **Se mantienen** `#map-layers` y los `input[data-capa]` con sus `aria-label`: el chequeo de teclado del e2e los recorre (MAPA-141, sin deshabilitar casillas).
3. **Se quita la lista duplicada** «Qué mostrar en el mapa» del panel. `syncCapaInputs()` deja de buscar `#view [data-layer]`. El selector de fondo pasa a la hoja de capas.
4. **Buscador visible.** «Buscar mi comuna» queda arriba del panel del Mapa, fuera de «Capas», con la misma lógica de `buscarComunas`.
5. **El fondo OpenTopoMap pasa a llamarse «Topográfico»** (decisión del dueño, 25-10). Se mantiene su atribución. Hay que actualizar `docs/FUENTES.md`, `tests/js/map.test.mjs` si mira la etiqueta, y `web/preguntas.html` (texto visible, JSON-LD idéntico y citas a líneas reales).
6. El texto del FAQ que describe el control («El control enciende…») debe quedar fiel a lo nuevo.

**Criterio de listo.**
- El chequeo de teclado y el de capas del e2e siguen en verde.
- A 390 px los chips no se superponen con «Mi ubicación» ni con el chip de leyenda.
- No hay textos cortados a 320 px.
- La guarda del FAQ y las reglas de diseño pasan.

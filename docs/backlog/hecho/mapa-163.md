---
id: MAPA-163
repo: brasas
rama: feat/incendios-con-nombre
modelo: swe-2-high
riesgo: M
archivos: web/js/map.js, web/js/capas.js, web/js/views/mapa.js, web/preguntas.html, scripts/local/browser_checks.py, tests/js, CHANGELOG.md
e2e: si
intento: 0
depende: Ola 1 mergeada (registrarToque y abrirPopup)
---

# MAPA-163 · Incendios con forma y nombre (y datos al día mientras miras)

**Qué pasa hoy y por qué está mal.**
1. Bajo zoom 7, cada incidente tiene su anillo (MAPA-152). **A partir de zoom 7** el fuego se ve como puntos y cuadros sueltos: no hay contorno ni nombre, porque las «Huellas» vienen apagadas.
2. Los incendios de CONAF tampoco llevan nombre en el mapa.
3. Para saber qué es cada cosa hay que tocar punto por punto, y en el celular eso es lento.
4. En la vista Mapa, `loadIncidents()` y `loadOfficial()` corren **solo al montar** (y al cambiar las horas o la capa de huellas). Mientras la vista queda abierta, los focos se actualizan cada 2 min, pero los anillos y los incendios de CONAF no.

**Qué hacer.**
1. **Contorno por defecto.** Desde zoom 7, el contorno (`incident-hulls-line`) de los incidentes abiertos con 3 o más detecciones se dibuja junto con «Focos de calor». Pide `api.incidents(horas, true)`; la huella ya se cachea en el servidor y la ruta en el borde.
   - El **relleno** (`incident-hulls-fill`) sigue dependiendo del interruptor «Huellas de calor».
   - La leyenda y el FAQ lo dicen: «es la zona aproximada donde se vio calor, no el perímetro oficial».
2. **Etiquetas desde zoom 8.** Una capa `symbol` sobre los incidentes (la fuente de `incident-rings`, sin límite de zoom) con estado y comuna, por ejemplo «Posible incendio · Quillón». **Sin «hace X»**, porque una etiqueta no se refresca sola.
   - Los incendios de CONAF también llevan etiqueta: «CONAF: «Nombre» · En curso».
   - Se mantienen `text-font: ['Noto Sans Regular']`, el halo del tema y la colisión de MapLibre (no fuerces superposición).
3. **Tocar** la etiqueta o el contorno abre la ficha del incidente mediante `registrarToque`. La ficha muestra estado, comuna, número de detecciones, última vez visto y «Ver qué ha pasado aquí» (`#/incendio/<id>`).
4. **Datos al día.** En la vista Mapa, cada lote nuevo de observaciones (`store.on('observations')`) vuelve a pedir incidentes y CONAF, con al menos 60 s entre pedidos y solo con la vista visible. Se suelta en `unmount`.
5. **Guardas:**
   - Si cambias el texto de una capa, actualiza `web/preguntas.html`: el texto visible y el JSON-LD tienen que ser idénticos (`test_preguntas_frecuentes.py`), y las citas `<!--archivo:línea-->` deben apuntar a líneas reales.
   - `CAPA_NOMBRE` y `CAPAS_SIN_DATOS` de `browser_checks.py` siguen cubriendo todas las capas del control.

**Prueba en navegador.** Con la demo, en `#/mapa?lat=-33.07&lon=-71.41&z=9` a 1280 px:
- El lienzo cambia al prender «Focos de calor» (contorno incluido).
- Hay una etiqueta del incidente de Quilpué: se puede verificar con `map.queryRenderedFeatures` sobre la capa de etiquetas, obteniendo el mapa con `await import('/web/js/map.js')`.

**Criterio de listo.** Las pruebas pasan; la guarda del FAQ y las capas del e2e quedan en verde; la paleta pasa (`validate_palette.mjs`).

---
id: MAPA-158
repo: brasas
rama: feat/toque-y-ficha
modelo: swe-2-max
riesgo: M
archivos: web/js/popup.js, web/js/map.js, web/js/app.js, web/js/views/mapa.js, web/css/app.css, scripts/local/browser_checks.py, CHANGELOG.md
e2e: si
intento: 0
depende: MAPA-157 (mismo PR)
---

# MAPA-158 · Ficha fija abajo en el celular y un mapa que sabe dónde está la hoja

**Qué pasa hoy y por qué está mal.**
1. El popup de MapLibre se ancla al punto dentro de `#map`, y la hoja inferior (`.panel`, `z-index: 6` en el bloque celular de `web/css/app.css`) lo tapa.
   - En «Mi zona» la hoja va a la mitad: quedan unos 290 px de mapa útil para una ficha de unos 250 px.
   - El popup no se mueve para quedar a la vista.
2. El mapa no sabe que la hoja existe: no hay `map.setPadding`.
   - «Mi ubicación» deja tu punto debajo de la hoja.
   - La atribución y la escala, abajo a la derecha, quedan siempre tapadas en el celular, así que el objetivo de MAPA-105 (crédito siempre visible) no se cumple en móvil.
   - `viewPadding()` de `map.js`, con la hoja completa, centra el punto en todo el contenedor, es decir, detrás de la hoja.

**Qué hacer.**
1. **Ficha que se adapta al ancho.** `abrirPopup(lngLat, contenido, maxWidth)` de `web/js/popup.js` (creado en PR #739) mantiene su nombre y su firma. `cerrarPopup()` y `popupFoco(obs, lngLat)` también.
   - **Desde 900 px:** sigue siendo el popup de MapLibre de hoy.
   - **Bajo 900 px:** el mismo contenido va en una ficha acoplada `#ficha`:
     - La crea `popup.js` la primera vez. **No se edita `index.html`.**
     - Va sobre la barra inferior, mide como máximo 60dvh, tiene desplazamiento propio, `role="dialog"`, `aria-labelledby` y un botón «Cerrar» de 44 px.
     - Se cierra con Esc, con «Cerrar» o con un toque en un lugar vacío (evento `brasa:toque-vacio` de MAPA-157).
     - Al abrir, el foco va a su título; al cerrar, vuelve al elemento que la abrió (si se abrió desde una lista).
   - Con la ficha abierta, la hoja baja a `peek`; al cerrar, vuelve a su estado anterior. `setSheet` guarda el estado en `store.set('sheet', estado)`.
   - **El resto de los popups de `mapa.js`** (reporte, peligro, lluvia, SENAPRED, rayos, cicatrices, servicios) se abren con `abrirPopup`.
   - **`officialPopup`** pasa a `popup.js` como `popupOficial(fire, lngLat)`, para que otras vistas lo reutilicen (MZ-08).
2. **Anillo de selección.**
   - Fuente nueva `seleccion` en `OVERLAY_SOURCES` y una capa de círculo sin relleno, con borde tinta o blanco según el tema, dibujada encima de todo.
   - Se marca al abrir una ficha y se borra al cerrarla.
3. **El mapa respeta la hoja.**
   - `setSheet` de `web/js/app.js` emite la altura en píxeles (evento `brasa:sheet-h` o `store.set('sheetPx', px)`).
   - `map.js` llama a `map.setPadding({ bottom })` bajo 900 px, con la altura de la hoja, o de la ficha si está abierta.
   - Así «Mi ubicación», `fly` y `fitBbox` encuadran en el área visible.
   - Hay que reconciliar `viewPadding()` para no sumar dos veces el margen. Criterio: el punto queda visible sobre la hoja o la ficha.
4. **Atribución y escala visibles en el celular.**
   - `.maplibregl-ctrl-bottom-right` y `.maplibregl-ctrl-bottom-left` suben con `bottom: var(--sheet-h)`, con transición.
   - Se mantiene `compact: false` (MAPA-105).
5. **Contexto en la ficha del foco.** Si hay un lugar guardado a menos de 100 km, una línea «A 4,2 km al noreste de «Casa»». Usa `haversineKm`, `bearingDeg` y `cardinal` de `util.js`, con el orden lat/lon verificado.
6. **CSS.** En un bloque propio comentado `/* MAPA-158 ficha */`. Sombras y bordes con `taste-skill-ignore: <motivo>`, como el resto de los elementos flotantes.

**Prueba en navegador** (`browser_checks.py`, 390×844, demo sembrada):
- Tocar un foco abre `#ficha`.
- Su caja queda entera dentro de la ventana, sobre la barra inferior, y `#panel` no la tapa (compara `getBoundingClientRect`).
- El punto proyectado del foco queda por encima del borde superior de la ficha.
- Esc la cierra y la hoja vuelve a su estado.
- A 1280 px se abre un `.maplibregl-popup`, como hoy.

**Criterio de listo.** Las pruebas anteriores pasan en el CI; no hay textos cortados a 320 ni a 390 px; las capturas del PR a 390 px muestran la ficha completa.

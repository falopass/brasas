---
id: MAPA-160
repo: brasas
rama: feat/toque-y-ficha
modelo: swe-2-max
riesgo: B
archivos: web/js/views/zona.js (montar y desmontar la leyenda), web/js/views/mapa.js, web/css/app.css, scripts/local/browser_checks.py, CHANGELOG.md
e2e: si
intento: 0
---

# MAPA-160 · La leyenda también en «Mi zona» del celular

**Qué pasa hoy y por qué está mal.**
- En el celular, la leyenda solo aparece si la vista pone la clase `mobile-show` en `#map-legend`. Mapa, Riesgo, Historia y la ficha del incidente la ponen; **Mi zona no**, y es la portada.
- Quien abre BRASA en el teléfono ve puntos y cuadros de colores sin ninguna explicación de qué significa cada color ni de que se pueden tocar.
- Además, el bloque celular de `web/css/app.css` oculta todas las `.legend-note`, también la advertencia «calor no siempre es incendio».

**Qué hacer.**
1. En `web/js/views/zona.js`, poner `mobile-show` al aplicar las capas de la portada y quitarlo en `unmount()`, igual que `mapa.js`. Así aparece el chip «Leyenda».
2. Una nota **esencial** que sí se vea en el celular: clase `legend-note esencial`.
   - En Mi zona: «Calor no siempre es incendio. Toca un punto para ver su detalle».
   - En Mapa: la nota existente «Calor no siempre es incendio. Los puntos pálidos son dudosos», marcada `esencial`.
   - El resto de las notas sigue oculto en el celular para no tapar el mapa.
3. El CSS va en el bloque celular, con una sola regla para `.legend-note.esencial`.

**Prueba en navegador.** A 390 px, en `#/mi-zona` con la demo, el chip «Leyenda» está visible; al tocarlo se ve la nota esencial.

**Criterio de listo.** La prueba pasa en el CI; no hay textos cortados a 320 px.

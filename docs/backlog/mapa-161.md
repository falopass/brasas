---
id: MAPA-161
repo: brasas
rama: feat/pin-preciso
modelo: swe-2-max
riesgo: M
archivos: web/js/ui.js, web/index.html (solo #pick-hint y el pin), web/css/app.css (bloque /* MAPA-161 */ y las reglas .pick-hint), scripts/local/browser_checks.py, CHANGELOG.md
e2e: si
intento: 0
---

# MAPA-161 · Marcar la casa o el reporte con precisión (pin fijo)

**Qué pasa hoy y por qué está mal.**
1. `pickOnMap()` de `web/js/ui.js` usa `map.once('click')`: el primer toque fija el lugar, **a cualquier zoom** y sin confirmar.
   - A la escala país con que abre Mi zona sin lugares (zoom ~4,6), un píxel son unos 8 km. Un toque puede dejar «Mi casa» a decenas de kilómetros, y los avisos de 10 km quedarían en otro sitio.
   - El dedo además tapa el punto que se está marcando.
2. «…o escribe tu comuna» deja el lugar en el **centro de la comuna**. En una comuna rural grande, ese centro puede quedar a más de 10 km de la casa.
3. En el reporte, «centro del mapa» (`#rf-center`) usa el centro de un mapa que el modal y la hoja tapan: la persona no ve qué punto está mandando.

**Qué hacer.**
1. **`pickOnMap(prompt)` con pin fijo.** Mantiene la firma y devuelve `{lat, lon}` o `null`.
   - Se ve un pin en el centro del área visible del mapa y una barra con el texto «Mueve el mapa hasta dejar el pin sobre el lugar» y los botones **[Confirmar]** y **[Cancelar]**. Reusa y amplía el `#pick-hint` de `web/index.html`.
   - **«Confirmar» queda deshabilitado bajo zoom 12**, con el texto «Acércate más para marcar con precisión». La constante va en `ui.js`.
   - Un toque sobre el mapa **mueve el mapa** hasta dejar ese punto bajo el pin, con `map.panBy([x - pinX, y - pinY])`. No confirma.
   - **Al confirmar se usa `map.unproject([pinX, pinY])`** (el centro del pin en pantalla, relativo al contenedor del mapa), **nunca `map.getCenter()`**. Así funciona con o sin el `setPadding` de MAPA-158.
   - Se mantiene `document.body.classList.add('picking')` mientras se elige: el resolutor de toques de MAPA-157 lo respeta.
   - Se mantienen la cancelación previa (`cancelPick`) y el colapso de la hoja.
2. **Comuna.** Al elegir una comuna en `placeForm`, en vez de guardar su centro, abre el pin sobre la caja de la comuna (`bbox` de `comunas-index.json`) con el texto «Ajusta el pin a tu casa». Si la persona cancela, queda el centro con la advertencia «Ubicación aproximada: el centro de la comuna».
3. **Reporte.** «Usar el centro del mapa» pasa a **«Marcarlo en el mapa»**, con el mismo flujo del pin. «Estoy aquí ahora» (GPS) no cambia.
4. **Texto y accesibilidad.** La barra se lee con lector de pantalla (`role="status"` para el aviso de zoom), los botones miden al menos 44 px y Esc cancela.

**Camino crítico (AGENTS.md).** Toca el formulario de reporte (`ui.js`). El CI del PR tiene que pasar `test_reports_safety`, `test_reportes_publicos`, `test_reports_caducidad`, `test_alert_report` y el e2e.

**Prueba en navegador** (390 px; crea un suscriptor como `scripts/local/emergency_sheet_check.py` y borra el lugar al final):
- Abre «Agregar mi casa» y luego «Marcarlo en el mapa».
- A zoom 5, «Confirmar» está deshabilitado.
- Lleva el mapa a zoom 13 sobre `-33.075, -71.405`, confirma y guarda.
- El lugar queda a menos de 100 m de ese punto.

**Criterio de listo.** La prueba pasa; las pruebas de reportes y el e2e quedan en verde; no hay textos cortados a 320 px.

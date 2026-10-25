---
id: MAPA-165
repo: brasas
rama: feat/incendios-con-nombre
modelo: swe-2-high
riesgo: B
archivos: web/js/popup.js, web/js/capas.js, web/js/views/mapa.js, tests/js, CHANGELOG.md
e2e: si
intento: 0
depende: Ola 1 mergeada
---

# MAPA-165 · Compartir un foco, un incidente o un incendio de CONAF

**Por qué.** En Chile la información de un incendio circula por WhatsApp. Hoy se puede compartir un lugar guardado y los pasos de «¿Qué hago si…?», pero no **lo que estás mirando en el mapa**: un punto de calor, un posible incendio o un incendio que informa CONAF.

**Qué hacer.**
1. **Botón «Compartir»** en la ficha del foco (`popupFoco`), en la de CONAF (`popupOficial`) y en la del incidente (MAPA-163).
   - Usa `navigator.share({ title, text, url })` si existe. Si no, ofrece «Enviar por WhatsApp» (`https://wa.me/?text=`) y «Copiar enlace», con el mismo patrón que `shareModal` de `views/zona.js`.
2. **Texto prudente.** Ejemplo: «Punto de calor visto por satélite hace 20 min en Quillón. Puede ser un incendio, una quema o una industria. Míralo en BRASA: <url>. Si ves fuego, llama al 130 o al 132».
   - Para CONAF: «CONAF informa el incendio «Nombre» (En curso) en <comuna>».
   - Nunca «incendio» para un punto de calor.
3. **Enlaces profundos.** Una función pura `enlaceCompartir(tipo, item, origen)` en `web/js/capas.js` arma:
   - foco: `/#/mapa?lat=<lat>&lon=<lon>&z=12&foco=<id>`
   - incidente: `/#/incendio/<id>`
   - CONAF: `/#/mapa?lat=…&lon=…&z=12&conaf=<id>`
   - Atención al orden: el parámetro `lat` lleva la latitud.
4. **Abrir el enlace.** `mount()` de `views/mapa.js` ya vuela con `lat`, `lon` y `z`. Además:
   - Si viene `foco` y la observación está entre las cargadas, abre su ficha.
   - Si viene `conaf` y el incendio está en `store.get('official')`, abre `popupOficial`.
   - Si no está (salió de la ventana), un aviso: «Ese punto ya no está entre los focos de las últimas horas; el mapa queda en su ubicación».
   - `updateCapasUrl` conserva esos parámetros.

**Prueba (Node).** `enlaceCompartir` arma bien las tres rutas: orden lat/lon y codificación.

**Criterio de listo.** La prueba pasa; abrir `#/mapa?lat=-33.06&lon=-71.42&z=12&foco=<id de la demo>` abre la ficha (agrégalo al e2e si es estable); no hay textos cortados a 390 px.

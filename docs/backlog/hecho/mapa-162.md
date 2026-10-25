---
id: MAPA-162
repo: brasas
rama: feat/toque-y-ficha (vista Mapa) y fix/mi-zona-al-dia (Mi zona)
modelo: swe-2-max / swe-2-high
riesgo: B
archivos: web/js/views/mapa.js (feat/toque-y-ficha), web/js/views/zona.js (fix/mi-zona-al-dia: solo los botones «Ver»), CHANGELOG.md
e2e: si
intento: 0
---

# MAPA-162 · De la lista al mapa sin perder el punto

**Qué pasa hoy y por qué está mal.** Al elegir algo en una lista del panel, el mapa vuela al punto, pero la hoja se queda como estaba.
- Si la hoja está completa, el punto y su popup quedan **debajo**: `viewPadding()` centra en todo el contenedor cuando queda menos de 160 px de mapa visible.
- La persona tiene que adivinar que debe bajar la hoja.

**Qué hacer.**
1. **Vista Mapa** (`feat/toque-y-ficha`). En «Incendios que informa CONAF»:
   - Bajo 900 px, la hoja baja a `peek` (`collapseSheet()` de `ui.js` o el evento `brasa:sheet`).
   - Después, el mapa vuela al punto y se abre su ficha (`popupOficial`).
   - «Posibles incendios» sigue llevando a `#/incendio/<id>`, que ya encuadra el incidente.
2. **Mi zona** (`fix/mi-zona-al-dia`). «Ver en el mapa» de la tarjeta y «Ver» de la lista de avisos bajan la hoja a `peek` antes de volar. La ficha del punto en Mi zona llega con MZ-08.
3. En escritorio no cambia nada.

**Prueba en navegador.** A 390 px, con la demo, expande la hoja del Mapa y elige el incendio CONAF de la lista: el punto proyectado queda sobre el borde superior de la hoja.

**Criterio de listo.** La prueba pasa en el CI. El encargo pasa a `hecho/` con el último de los dos PR.

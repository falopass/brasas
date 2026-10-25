---
id: MAPA-159
repo: brasas
rama: feat/toque-y-ficha
modelo: swe-2-max
riesgo: B
archivos: web/js/map.js, web/css/app.css, tests/js/map.test.mjs, CHANGELOG.md
e2e: si
intento: 0
depende: MAPA-158 (mismo PR, usa el padding)
---

# MAPA-159 · Gestos y controles pensados para dedos

**Qué pasa hoy y por qué está mal.**
- `initMap()` deja la rotación y la inclinación con dos dedos (`dragRotate: true`, `pitchWithRotate: true`, y `touchZoomRotate`/`touchPitch` por defecto), aunque el mapa no tiene 3D. En el celular es muy fácil girarlo o inclinarlo sin querer, y quien no conoce la brújula no sabe volver.
- Los botones +/− sobran con el pellizco y ocupan la esquina superior derecha, junto a «Mi ubicación».
- Los controles miden 38 px.

**Qué hacer.**
1. **Sin rotación ni inclinación táctil:** `touchPitch: false`, `pitchWithRotate: false` y `map.touchZoomRotate.disableRotation()`. Con mouse se puede seguir rotando con el botón derecho; `viento.js` ya compensa el rumbo.
2. **Con `matchMedia('(pointer: coarse)')`**, no se agrega `NavigationControl` (ni +/− ni brújula). En escritorio queda igual.
3. **«Mi ubicación»** (`GeolocateControl`) de 44×44 px en el celular. Gracias al padding de MAPA-158, centra en el área visible.
4. No cambian ni el orden del teclado ni los controles en escritorio. El chequeo `check_mapa_teclado` del e2e corre con puntero fino y tiene que seguir alcanzando los controles de MapLibre.

**Criterio de listo.** En un celular el mapa no gira ni se inclina con dos dedos y no muestra +/−; el e2e (teclado y capas) sigue en verde; el CSS nuevo pasa las reglas de diseño.

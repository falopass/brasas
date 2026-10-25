---
id: MAPA-152
repo: brasas
rama: feat/fuego-visible
modelo: swe-2-high
riesgo: B
archivos: web/js/map.js, web/js/views/mapa.js, web/js/capas.js, CHANGELOG.md
e2e: si
intento: 0
---

# MAPA-152 · Incendios activos a escala país

**Por qué.** A zoom país (bajo 7) se dibujan celdas de focos (`MAPA-01`), pero no se distingue un incendio de verdad de un grupo de calor suelto. Quien abre BRASA de lejos tiene que poder contestar de un vistazo «¿dónde hay incendios ahora?».

**Qué hacer.**
1. Bajo zoom 7, un símbolo por **incidente abierto** (`/api/incidents`, que la vista Mapa ya carga en `web/js/views/mapa.js:217`): un anillo cuyo tamaño crece con la superficie o la cantidad de detecciones y cuyo color sigue el estado, con la misma escala que ya usan las huellas (`hullStatus` en `map.js:188`). Los focos sueltos siguen como hoy.
2. Al tocar el símbolo se abre la ficha (`#/incendio/<id>`), igual que al tocar una huella.
3. Los incidentes en estado `anomalia` no llevan anillo (no son un incendio).
4. Debe convivir con la capa «Incendios de CONAF»: el anillo oficial (`official`) se sigue distinguiendo, con borde grueso.
5. Si hace falta, se agrega a `CAPAS` como parte de «Focos de calor» (no una capa nueva).

**Archivos.** `web/js/map.js`, `web/js/views/mapa.js`, `web/js/capas.js` y `CHANGELOG.md`.

**Criterio de listo.** En la captura del mapa a 390 px con la base demo se ve un anillo por incidente abierto y tocarlo lleva a la ficha; el e2e y la regresión visual pasan en el CI.

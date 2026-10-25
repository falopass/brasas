---
id: MAPA-151
repo: brasas
rama: feat/fuego-visible
modelo: swe-2-high
riesgo: B
archivos: web/js/map.js, scripts/local/validate_palette.mjs, CHANGELOG.md
e2e: si
intento: 0
---

# MAPA-151 · Que los focos y las celdas se vean a escala país

**Qué ve hoy el usuario y por qué está mal.** En las capturas e2e de `main` (run 40114142592, `mapa-capa-focos-despues.png` y `mi-zona-1280.png`) se ven los números «14» y «7» de las celdas flotando sin su punto. El color «Más de 1 día» (`#ffd38f`, `AGE_BINS` en `web/js/map.js:43`) casi no contrasta con el suelo beige del mapa, y las celdas (`detRadius`, `map.js:207`) usan ese mismo color. Un incendio de ayer desaparece justo en la vista que más se abre.

**Qué hacer.**
1. Contraste de al menos 3:1 (WCAG 1.4.11, elementos que no son texto) entre cada color de `AGE_BINS` —o su borde— y el suelo de los dos temas (claro y oscuro) y de la base satelital. La vía preferida es un borde oscuro (`circle-stroke-color`) en los focos de más de 6 h y en las celdas, sin cambiar la lógica «más rojo = más reciente».
2. El número de una celda (`detections-count`) siempre va sobre un punto visible y legible: texto oscuro sobre un relleno claro o al revés, con contraste ≥ 4,5:1.
3. Extiende `scripts/local/validate_palette.mjs` para que mida el contraste de `AGE_BINS` contra el suelo de cada tema.
4. La leyenda (`AGE_BINS[].label`) no cambia de texto.

**Archivos.** Solo `web/js/map.js`, `scripts/local/validate_palette.mjs` y `CHANGELOG.md`.

**Criterio de listo.** En las capturas `capturas-e2e` del PR, cada número de celda tiene un punto visible debajo en 390 y 1280 px; la regresión visual y el e2e pasan en el CI; `validate_palette.mjs` reporta el contraste de las cuatro edades.

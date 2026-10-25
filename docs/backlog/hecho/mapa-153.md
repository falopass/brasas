---
id: MAPA-153
repo: brasas
rama: feat/fuego-visible
modelo: swe-2-high
riesgo: B
archivos: web/js/map.js, web/js/views/mapa.js, CHANGELOG.md
e2e: si
intento: 0
geo: si
---

# MAPA-153 · Distancia y rumbo desde mi lugar, dibujados en el mapa

**Por qué.** Mi zona ya dice en palabras a qué distancia y en qué dirección está el calor (`haversineKm` y `bearingDeg` en `web/js/util.js:56-65`), pero el mapa no lo muestra. En una emergencia, ver una línea de la casa al fuego se entiende más rápido que leer «4,2 km al noreste».

**Qué hacer.**
1. Con la capa «Mis lugares» prendida, una línea punteada desde cada lugar guardado hasta el foco confiable más cercano dentro de su radio de aviso, con una etiqueta «4,2 km · al noreste» en la mitad de la línea. Usa `haversineKm`, `bearingDeg` y la frase de rumbo que ya existen en `util.js`; no dupliques la fórmula.
2. Si no hay foco dentro del radio, no se dibuja nada.
3. Es una ayuda visual, no un aviso: el texto es el mismo que ya usa Mi zona.

**Archivos.** `web/js/map.js`, `web/js/views/mapa.js` y `CHANGELOG.md`.

**Revisión.** Pide `geo-reviewer` (`.devin/agents/geo-reviewer.md`) antes de activar el auto-merge: orden lat/lon y rumbo geográfico.

**Criterio de listo.** Con la base demo y un lugar guardado cerca de un foco, la línea y la etiqueta aparecen; sin foco en el radio, no; el CI pasa.

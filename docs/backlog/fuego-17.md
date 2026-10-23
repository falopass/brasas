---
id: FUEGO-17
repo: brasas
rama: feat/viento-hacia-mis-lugares
modelo: swe-2-high
riesgo: B
archivos: web/js/views/incendio.js, web/js/util.js, tests/js/util.test.mjs, CHANGELOG.md
e2e: si
intento: 0
ronda_review: 0
estado_desde: 2026-10-20T10:10:17
nota: Reencolado: la corrida falló por rate limit del modelo gratis, no por el ítem.
---

# FUEGO-17 · «¿Viene hacia mi casa?»: el viento del escenario contra mis lugares

**Objetivo.** Que la ficha de un incidente, cuando la persona tiene lugares guardados cerca, diga en una frase si el viento de ahora empuja el fuego **hacia ese lugar o lo aleja**, con la etiqueta de escenario estimado siempre visible.

**Qué ve hoy el usuario y por qué está mal.** En `web/js/views/incendio.js:148` la ficha dice la distancia —«A 8 km de «Casa». También a 12 km de «Parcela»»— y en el bloque del escenario (`:151-154`) dice hacia dónde avanza y de dónde viene el viento, pero **nunca cruza las dos cosas**. Un vecino del Maule con la casa guardada tiene que hacer la cuenta mental: «el fuego avanza hacia el sureste y el viento viene del noroeste, ¿eso me toca a mí o no?». Es exactamente la pregunta que se hace alguien mirando la ficha a las 11 de la noche, y hoy la app la deja sin responder aunque tiene los tres datos: la posición del incendio (`inc.lat`/`inc.lon`), la de cada lugar guardado (`store.get('places')`) y el rumbo del viento (`data.spread.wind_deg`).

**Qué hacer.** (1) En `web/js/util.js` agrega una función pura `bearingDeg(lat1, lon1, lat2, lon2)` que devuelva 0-360 (misma matemática que `backend/geo.py:222`, sin `if` raros) y una `relativeToWind(bearingToPlace, windFromDeg)` que devuelva uno de tres estados: `hacia` (el lugar está en el cono de avance, ±45°), `de costado` o `en contra`, más el ángulo. (2) En `incendio.js`, debajo de la línea de los lugares, agrega una frase en castellano simple y dual: «El viento de ahora sopla hacia el suroeste: eso empuja el fuego **hacia** «Casa»» / «…**se aleja** de «Casa»» / «…pasa **de costado** a «Casa»», con `windFrom`/`cardinal` ya existentes y la nota «escenario estimado, no es una predicción» en la misma frase si el estado es `hacia`. (3) Si no hay `spread` o no hay lugares guardados, no agregues nada (cero ruido). (4) Nada de tono alarmista ni de recomendar evacuaciones: la app describe el viento, no ordena nada.

**Archivos.** `web/js/views/incendio.js`, `web/js/util.js`, `tests/js/util.test.mjs`, `CHANGELOG.md`. **No toques nada más**: ni `map.js`, ni `mapa.js`, ni `backend/`.

**Caso de prueba concreto.** En `tests/js/util.test.mjs` (suite existente, sin tocar `index.js`): (a) `bearingDeg(-35.43, -71.66, -35.43, -71.0)` ≈ 90° (el lugar está al este); (b) simetría: `bearingDeg(a,b)` y `bearingDeg(b,a)` difieren en 180° ± 1; (c) `relativeToWind(90, 270)` = «hacia» (viento del oeste empuja al este) y `relativeToWind(90, 90)` = «en contra»; (d) ±45° exactos caen en «hacia»; (e) sin viento devuelve `null`.

**Criterio de listo (verificable).** `node --test tests/js` en verde con los casos nuevos; `python dev.py e2e` sin fallos con una ficha de incidente que tenga `spread` y un lugar guardado (la frase aparece una sola vez y dice el rumbo correcto); `node --check web/js/util.js` y `node --check web/js/views/incendio.js` limpios; `python dev.py check` en verde.

**Peso.** Hoy `python dev.py check` está rojo en `main` por dos presupuestos: `presupuesto_peso.py` mide **200,2 KB gzip de 200,0** y `peso_arranque.py` mide **252,9 KB de 252** (su test es `tests/test_peso_arranque.py:94`). El CI no corre ninguno de los dos. PESO-05 (`perf/textos-legales-fuera-del-js`, ya en `cola/`) libera ~4 KB. Si tu rama sale de un `main` sin ese merge, entrega el PR igual y anota en el PR la medición exacta: una falla **solo** del presupuesto de peso es previa y tiene dueño. **No subas el umbral** y no crees suites nuevas en `tests/js/` (el índice `tests/js/index.js` está tomado por DEBT-05): usa las suites que ya existen.

**Cierre.** Verifica con `/verificar` y entrega con `/entregar-pr`. No mergees por iniciativa propia.


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.

---
id: SAT-01
repo: brasas
rama: feat/visor-satelital-hora-y-calor
modelo: swe-2-high
riesgo: B
archivos: web/js/satelite.js, tests/js/satelite.test.mjs, CHANGELOG.md
e2e: no
intento: 0
ronda_review: 0
estado_desde: 2026-10-20T10:10:17
nota: Reencolado: la corrida falló por rate limit del modelo gratis, no por el ítem.
---

# Objetivo

Que el enlace «verlo en el satélite» que BRASA ofrece en los casos históricos abra la **imagen del día y la hora exactos de la detección con la capa de calor** encima, no solo una foto de color verdadero del día en que empezó el caso.

# Problema (qué ve hoy el usuario y por qué está mal)

`web/js/satelite.js` arma dos URLs externas (NASA Worldview y SLIDER de GOES) y es un módulo puro con pruebas. Su estado actual:

- `web/js/satelite.js:19` — `const LAYERS = { viirs: 'VIIRS_SNPP_CorrectedReflectance_TrueColor', modis: 'MODIS_Aqua_CorrectedReflectance_TrueColor' }`: solo capas de **color verdadero**. Un vecino que abre el visor ve nubes y suelo, pero **no el calor** que el satélite detectó: no puede comprobar con sus ojos de dónde salió el punto.
- `web/js/satelite.js:30-35` — `worldviewUrl({ bbox, start, end })` valida `end` (línea 32) y **nunca lo usa**: el parámetro `t=` sale solo de `start` (línea 34). Es un parámetro muerto que además confunde a quien lea el código.
- `web/js/views/casos.js:56-60` (consumidor del módulo; está tomado por CONT-14, no lo toques) ya anuncia en pantalla «Worldview muestra la capa X del <fecha> <hora> UTC», mientras la capa elegida no muestra calor.
- El resultado es una promesa visual que el visor no cumple: el vecino abre la pestaña, no ve el incendio y desconfía del dato.

# Qué hacer

1. En `web/js/satelite.js`, agrega las capas térmicas documentadas de Worldview para los dos sensores que ya usa el módulo (`VIIRS_SNPP_ThermalAnomalies` y `MODIS_Aqua_ThermalAnomalies`) en un objeto `THERMAL` junto a `LAYERS`, con el mismo comentario de fuente que ya tiene el archivo (la lista de capas viene de `config/wv.json` del repositorio `nasa-gibs/worldview`). Verifica los identificadores contra esa lista; si no puedes comprobarlos, deja el comentario con la referencia y una nota de que se validaron contra la documentación.
2. Nueva función exportada `thermalUrl({ bbox, at })`: devuelve la URL de Worldview sobre ese `bbox` con la capa térmica correspondiente a la fecha de `at` (misma regla que `worldviewLayer`, con su corte 2015-11-24) y `t=` construido desde el instante exacto de la detección. `null` si falta `bbox` válido o `at` legible.
3. Extiende `worldviewUrl({ bbox, start, end, layer })` con un `layer` **opcional** que, si viene, sustituye la capa por defecto; y que `t=` use `end` cuando venga y sea posterior a `start` (así se reutiliza el parámetro que hoy está muerto). Sin `layer` ni `end`, la salida tiene que ser **idéntica** a la de hoy.
4. `sliderUrl({ satellite, sector })`: `sector` opcional con `full_disk` por defecto, para poder apuntar a un sector que incluya Chile sin cambiar la llamada actual.
5. `tests/js/satelite.test.mjs`: agrega casos con URL exacta (mismo estilo que los que ya están) para `thermalUrl` (VIIRS y MODIS), para `worldviewUrl` con `end` posterior y para `worldviewUrl` con `layer`; y un caso que falle si la salida sin opciones cambió respecto de las 6 pruebas actuales.

# Archivos a tocar

`web/js/satelite.js`, `tests/js/satelite.test.mjs`, `CHANGELOG.md`. **No toques nada más**: `web/js/views/casos.js` está en curso (CONT-14) y debe seguir compilando sin cambios; por eso toda la API nueva es retrocompatible.

# Criterio de listo (verificable)

- `python dev.py check` en verde (incluye las suites JS), con al menos 4 pruebas nuevas en `tests/js/satelite.test.mjs` y las 6 anteriores intactas.
- `grep -n "ThermalAnomalies" web/js/satelite.js` muestra los identificadores con su comentario de fuente.
- Ninguna URL generada contiene `undefined` ni `NaN` (el archivo ya tiene una prueba así: extiéndela a las funciones nuevas).

Verifica con `/verificar` y entrega con `/entregar-pr`. No mergees por iniciativa propia.


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.

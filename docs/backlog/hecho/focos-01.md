---
id: FOCOS-01
repo: brasas
rama: feat/lista-de-focos-en-texto
modelo: swe-2-high
riesgo: B
archivos: web/focos.html, web/js/focos.js, web/css/lista.css, web/index.html, backend/main.py, tests/test_focos_pagina.py, CHANGELOG.md
e2e: si
intento: 0
ronda_review: 0
estado_desde: 2026-10-20T10:10:17
nota: Reencolado: la corrida falló por rate limit del modelo gratis, no por el ítem.
---

# FOCOS-01 · Una lista de focos e incendios activos en texto, sin mapa

## Objetivo
Que cualquier vecino pueda saber, leyendo texto, qué focos e incendios hay activos hoy en Chile: sin JavaScript pesado, sin WebGL, sin 4 MB de mapa y con lector de pantalla. Hoy eso no existe.

## Qué pasa hoy (verificado en `main`)
- La única puerta a los focos es el mapa de la aplicación (`web/js/views/mapa.js`, MapLibre) y la SPA de `web/index.html`.
- Si el navegador no ejecuta JavaScript, `web/index.html:103-120` muestra teléfonos y dos enlaces (`/web/lite.html`, `/web/lista.html`). El modo liviano (`web/lite.html`) es **por lugar guardado**, no una lista nacional; y alguien que usa lector de pantalla no tiene ninguna tabla de incidentes que pueda recorrer con el cursor.
- Los datos ya existen y son públicos: `GET /api/incidents?hours=24` devuelve `id, status, comuna, region, last_seen_at, n_obs, n_reliable` (`backend/routes/public.py:239-246`) y `GET /api/official-fires` devuelve nombre, estado y `area_ha` de CONAF (`backend/routes/public.py:286`).
- Efecto para el vecino: en un teléfono de 2G, con datos lentos o con lector de pantalla, BRASA no contesta la pregunta básica («¿qué está ardiendo cerca de mi comuna?»).

## Qué hacer
1. **Página nueva `web/focos.html`** (hermosa pero sobria, en la línea de `web/lista.html` y `web/lite.html`): `lang="es"`, un solo `<h1>` («Focos e incendios activos en Chile»), `<main>`, `<meta name="robots" content="noindex">` como lite, sin estilos ni scripts en línea; los estilos nuevos van al final de `web/css/lista.css` (clase `.tabla-focos`), que ya se sirve para las páginas sueltas. Un párrafo que diga que BRASA no es una alerta oficial y enlace a SENAPRED y a los teléfonos 130/132.
2. **`web/js/focos.js`** (módulo ES, sin dependencias): `fetch` con `AbortController` y tope de 8 s a `/api/incidents?hours=24` y `/api/official-fires`; arma una tabla accesible (`<table>` con `<caption>` y `<th scope="col">`) ordenada por `last_seen_at` descendente con: estado en palabras (dual, sin jerga), comuna y región, última detección en hora de Chile, número de detecciones y, si hay incendio oficial con `area_ha`, la superficie y el enlace a la ficha `/web/index.html#/incendio/<id>`. Escapa todo lo que interpole (hay nombres de comuna y de incendio que vienen de CONAF).
3. **Estados honestos**: si una de las dos consultas falla, se muestra la tabla de la otra y un aviso con la hora del intento y qué fuente falta; nunca «no hay fuego» si no se pudo consultar. Si ambas fallan, un solo bloque con «No pudimos consultar…» y los teléfonos. Agrega un `<time>` con la hora local de la consulta (`Intl.DateTimeFormat('es-CL', { timeZone: 'America/Santiago' })`).
4. **`backend/main.py`**: ruta nueva `@app.get("/focos.html", include_in_schema=False)` con `FileResponse(WEB / "focos.html", headers={"Cache-Control": "no-cache"})`, copiando el patrón de `/lista.html` (`backend/main.py:102-106`).
5. **`web/index.html`**: en el `<noscript>` (línea 118) agrega `/focos.html` a la lista de páginas que funcionan sin JavaScript, con el texto «la lista de focos activos en texto».
6. **`tests/test_focos_pagina.py`** (nuevo, solo stdlib + el cliente de pruebas que ya usan `tests/test_paginas_estaticas.py`): la página se sirve en `/focos.html` con 200; tiene `lang`, un solo `<h1>`, `<main>`, y **no** tiene `<script` en línea ni hosts externos (misma regla que `lista.html`); el módulo `focos.js` no usa `innerHTML` con datos sin escapar, declara el tope de 8 s y formatea en `America/Santiago`; y una prueba de que el escapado convierte `Talca <b>` en texto.
7. `CHANGELOG.md`: una entrada que diga qué página nueva hay y para quién.

## Criterio de listo (verificable)
- `python dev.py test -k focos` en verde.
- `python dev.py check` en «Todo en orden» (si falla **solo** por «Peso del arranque excedido» o «Presupuesto de peso excedido», es el estado de `main` que arregla PERF-06: no subas umbrales, anótalo en el PR).
- Con `python dev.py run --demo`: `/focos.html` muestra los incidentes del seed, con hora de Chile, y la tabla se recorre con teclado; `python dev.py e2e` no reporta errores nuevos.
- La página pesa menos de 6 KB gzip (indicarlo en el PR).

## Archivos a tocar
`web/focos.html`, `web/js/focos.js`, `web/css/lista.css`, `web/index.html`, `backend/main.py`, `tests/test_focos_pagina.py`, `CHANGELOG.md`. **No toques nada más**: no edites `web/js/app.js` (lo toma PERF-06), ni `web/sw.js`, ni `web/js/views/*`, ni `deploy/`.

Verifica con `/verificar` y entrega con `/entregar-pr`. No mergees por iniciativa propia.


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.

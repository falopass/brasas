---
id: MOV-03
repo: brasas
rama: feat/movil-pwa
modelo: swe-2-high
riesgo: M
archivos: web/sw.js, web/manifest.webmanifest, web/js/instalar.js, web/js/views/mas.js, web/js/pildora.js, web/css/app.css, tests/js/sw.test.mjs, tests/js/pildora.test.mjs, tests/test_service_worker.py, tests/test_manifest.py, CHANGELOG.md
e2e: no
intento: 1
ronda_review: 0
estado_desde: 2026-11-10T00:00:00
nota:
---

# MOV-03 · Instalación PWA y sin conexión en el teléfono

## Evidencia medida en producción (Playwright, 360 px, 10-nov-2026)

- Bien: el service worker se registra y activa (`brasa-<hash>`), el manifiesto es
  `standalone` con íconos 192/512/maskable, 5 atajos y `share_target`. Sin conexión,
  recargar `/` muestra la app con los datos guardados; `/web/lite.html` también abre.
- Mal: sin conexión, `/focos.html` (enlazado desde el `<noscript>` y desde el bloque
  de fallo de arranque de `index.html`) daba `net::ERR_FAILED`: la página de error
  del navegador. El `SHELL` de `sw.js` guardaba `/web/focos.html`, pero la ruta
  pública es `/focos.html` (la sirve `backend/main.py`; el Worker la resuelve por
  `PAGINAS` en `deploy/cloudflare/src/rutas.ts`). Tampoco había respaldo para una
  navegación cualquiera que fallara sin conexión.
- No había invitación a instalar dentro de la app (`beforeinstallprompt` no se usaba
  en ningún archivo).
- El atajo «¿Hay fuego cerca de mí?» del manifiesto abría `/#/mi-zona` y obligaba a
  un toque más.

## Qué se hizo

- **Respaldo de navegación sin conexión** en `web/sw.js`: para `request.mode ===
  'navigate'` del mismo origen, red primero (la respuesta buena queda guardada); si
  falla, la copia en caché de esa URL ignorando la búsqueda, luego su gemela bajo
  `/web/` (las páginas se sirven por ambos caminos), luego `/web/lite.html` y al
  final `/`. Nunca la página de error del navegador mientras haya copia.
- `/focos.html` entra al `SHELL` junto a `/web/focos.html` (ambas rutas sirven la
  página). Las cuatro páginas del `<noscript>` y del bloque de fallo (`/web/lite.html`,
  `/web/lista.html`, `/web/preguntas.html`, `/focos.html`) quedan precargadas y hay
  una prueba que lo vigila.
- **Atajo directo**: «¿Hay fuego cerca de mí?» apunta a `/#/mi-zona?cerca=1`. El
  parámetro lo lee `app.js` desde MOV-01 (otra sesión); mientras no llegue, se
  ignora sin romper nada. «Hoja de emergencia» (`/lista.html`) ya resolvía bien:
  `backend/main.py` la sirve y `assetPath` en el Worker la mapea a `/lista`.
- **Instalar desde «Más»**: módulo chico `web/js/instalar.js` guarda el
  `beforeinstallprompt` con `preventDefault()` y `mas.js` muestra la fila «Instalar
  BRASA en el teléfono» solo cuando corresponde: en Android/Chrome lanza
  `prompt()` al tocar (la fila se retira tras la respuesta); en iPhone/iPad, donde
  no existe el evento, la fila es informativa con los pasos «Toca Compartir y
  después «Añadir a pantalla de inicio»»; ya instalada (`display-mode: standalone`
  o `navigator.standalone`) no aparece. Sin ventanas emergentes automáticas.
- **Píldora sin conexión**: `pillState` relee `navigator.onLine` en el momento y
  no solo el `online` que le pasan — un «online» viejo ya no pinta «Actualizado» si
  la app se abrió sin señal; y sin marca del SW la antigüedad sale de
  `last_ingest_at` («Sin conexión · datos de hace N»).

## Pendiente anotado

- `instalar.js` se importa con la vista «Más»; un `beforeinstallprompt` que llega
  antes se pierde y la fila simplemente no aparece. Escuchar el evento desde el
  arranque en `app.js` queda como mejora posterior (este encargo no toca `app.js`).

## Verificación

- `node --check` sobre `web/sw.js`, `web/js/instalar.js`, `web/js/views/mas.js`,
  `web/js/pildora.js` y `tests/js/sw.test.mjs`: verde.
- `node --test tests/js/` (la suite completa, 874 pruebas): verde. Incluye la nueva
  `tests/js/sw.test.mjs`, que ejecuta `web/sw.js` con `self`, `caches`, `fetch` y
  `Request` simulados y comprueba el respaldo de navegación de punta a punta, y los
  casos nuevos de `pildora.test.mjs`.
- `pytest tests/test_service_worker.py tests/test_manifest.py
  tests/test_estaticas_guardas.py tests/test_paginas_livianas.py` (23 pruebas): verde.
- `ruff check` sobre los `.py` tocados: verde.
- Lo que valida el CI además: reglas de diseño, presupuestos de peso y el e2e con
  navegador (MOV-03 no corre e2e por fuera).

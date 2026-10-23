---
id: MAPA-02
repo: brasas
rama: feat/lite-abre-enlace-compartido
modelo: swe-2-high
riesgo: B
archivos: web/lite.html, web/js/lite.js, tests/test_paridad_lite.py, CHANGELOG.md
e2e: si
intento: 0
ronda_review: 0
estado_desde: 2026-10-20T10:10:17
nota: Reencolado: la corrida falló por rate limit del modelo gratis, no por el ítem.
---

**Objetivo:** que el modo liviano (`/web/lite.html`) abra el enlace compartido de un lugar (`/web/lite.html#/v/<token>`) y deje de quedarse colgado en una conexión rural mala, para que un hijo pueda mandarle a su madre el enlace de la casa y ella lo vea en un celular lento sin instalar nada.

**Ítem del backlog:** FIX-06 y UX-03 (modo liviano) y la prioridad 2 de esta ronda (el mapa y sus alternativas para señal mala). Hoy `web/js/lite.js:137` solo lee el token del dispositivo desde `localStorage` (`brasa:token`), así que quien abre un enlace compartido ve el estado vacío de `emptyState()` (`:246`): «Abre BRASA y guarda tu lugar; aquí verás su estado». El enlace compartido existe y su API es pública (`/api/shared/<token>`, la que usa `web/js/views/vecino.js:90`), pero el modo liviano no lo conoce. Además `lite.js:145` hace `fetch` sin tope de tiempo, mientras `web/js/api.js:24` ya resolvió eso con `AbortSignal.timeout` (FIX-45): en una conexión que no responde, el modo liviano se queda en «Cargando…» para siempre.

**Qué hacer:**
1. En `web/lite.html`, añade un `<p id="lite-shared">` vacío bajo el encabezado, para el aviso de vista compartida, con su estilo mínimo en el `<style>` inline (la página es autocontenida).
2. En `web/js/lite.js`, lee el token del enlace desde `location.hash` (`#/v/<token>`) y también desde `?v=<token>`. Si hay token, pide `GET /api/shared/<token>` y pinta una sola tarjeta de solo lectura con el mismo lenguaje que `placeCard()`: nombre del lugar, estado, qué hacer, teléfonos (usa `tel()`), «Datos: hace X» y el aviso de que BRASA no es oficial. Sin botones de suscripción (el modo liviano no crea suscriptores): un enlace visible «Abrir en BRASA» a `/#/v/<token>`.
3. Si el token falla (404 o error), muestra un estado claro: «Este enlace ya no funciona» con el botón «Reintentar», sin dejar la página vacía.
4. Agrega tope de tiempo a `get()` con `AbortSignal.timeout` (12 s, como `api.js`) y traduce `TimeoutError` a «El servidor no respondió a tiempo. Revisa tu conexión e inténtalo de nuevo.».
5. `tests/test_paridad_lite.py` cubre que el modo liviano no invente textos de estado ni teléfonos respecto de la app. Extiéndelo para el nuevo estado «enlace inválido» y para que los textos de estado sigan saliendo de `STATUS` y `GUIDANCE_FIRST`.

**Archivos a tocar:** `web/lite.html`, `web/js/lite.js`, `tests/test_paridad_lite.py`, `CHANGELOG.md`. No toques nada más: `web/sw.js`, `web/js/views/zona.js` y `web/js/api.js` están tomados por otras ramas.

**Criterio de listo:** `python dev.py check` verde. Con `python dev.py run --demo` (o `instabox-verify -E2E`), abrir `/web/lite.html#/v/<token válido>` muestra una tarjeta con el lugar y `/web/lite.html#/v/inventado` muestra «Este enlace ya no funciona». Sin token, la página se comporta igual que antes.

Verifica con /verificar y entrega con /entregar-pr. No mergees por iniciativa propia.


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.

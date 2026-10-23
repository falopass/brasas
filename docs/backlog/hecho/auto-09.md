---
id: AUTO-09
repo: brasas
rama: feat/admin-salud-de-fuentes
modelo: swe-2-high
riesgo: B
archivos: web/admin.html, web/js/admin.js, tests/test_estaticas_guardas.py, CHANGELOG.md
e2e: si
intento: 0
ronda_review: 0
estado_desde: 2026-10-20T10:10:17
nota: Reencolado: la corrida falló por rate limit del modelo gratis, no por el ítem.
---

# AUTO-09 · El panel de administración suma una pestaña «Salud» con qué está fallando y qué hacer

# Objetivo

Que quien opera BRASA vea en una sola pantalla —la pestaña «Salud» del panel de administración— el estado real del producto (datos viejos, fuentes que fallan ahora, errores 5xx de las últimas 24 h, cupos de las APIs y respaldos) y, por cada problema, la acción concreta que corresponde.

# Problema (qué ve hoy el usuario y por qué está mal)

El panel `web/admin.html` sólo sirve para moderar reportes ciudadanos: tiene las pestañas «Reportes», «Bitácora» y «Equipo» (`web/admin.html:37`, `:49`, `:53`) y ni una línea sobre el estado de las fuentes. Para saber si GOES dejó de bajar barridos, si FIRMS está en 429, si el respaldo de R2 no subió o si el riesgo de hoy se quedó con el nivel de ayer, hay que abrir a mano `/api/status` en el navegador y leer doscientos campos JSON. El resultado práctico: la ventana de «el producto se auto-vigila» existe pero está en la vista pública Calidad (que muestra frescura y barridos sin decir qué hacer) y en `backend/diagnostics.py` (que sólo resume errores por proveedor). Nadie cruza eso con una decisión. Un operador nuevo no sabe si un punto rojo de hace seis horas es un incendio de avisos apagado o un incidente ya resuelto; y como todo se mira en JSON crudo, se mira tarde.

# Qué hacer (y nada más que esto)

1. `web/admin.html`: agrega una pestaña «Salud» junto a las existentes, con su `role="tab"`, `aria-selected`, `aria-controls` y su `<section id="salud" hidden>` con un `<h2>` propio, igual que las otras tres secciones. No cambies el login ni el resto de las pestañas.
2. `web/js/admin.js`: al abrir la pestaña, pide `/api/status` con el mismo helper `call()` que ya usa el panel (lleva el token de admin) y pinta tarjetas independientes, cada una con **hechos de la API, sin inventar**:
   - «Datos»: `freshness` (estado y minutos), `last_ingest_at`, `newest_observation`; si el estado no es fresco, la acción «Revisa el cron de ingesta y `/api/run`».
   - «Fuentes»: `runs` por producto (última corrida ok/fallo y su hora) y `goes_missing`/`goes_gap`; acción: «Si un producto falla dos veces seguidas, mira `/api/status?history=1`».
   - «Errores de 24 h»: `failures_24h` y `errors`, los tres primeros con su proveedor y su mensaje recortado.
   - «Cupos»: `firms_quota` y `open_meteo.counts` cuando vengan; si no vienen, la tarjeta dice «sin dato» y no se inventa un número.
   - «Respaldo»: `backup.bytes`, `backup.updated_at` y el de `work.db`; acción: «Si no hay respaldo de hoy, revisa `/api/backup`».
   - Mientras carga: un `role="status"` con «Consultando el estado…»; si la consulta falla, el error con botón «Reintentar» y los teléfonos no hacen falta aquí.
   Cada tarjeta lleva su color de severidad con las clases que ya existen (`callout`, `callout-warn`), no una paleta nueva.
3. `tests/test_estaticas_guardas.py`: una prueba nueva que abra `web/admin.html` y exija la pestaña «Salud» con `role="tab"`, la sección con su `aria-labelledby`, un `<h2>` y que el panel no tenga `<script>` en línea (las guardas CSP que ya usa el repo).
4. `CHANGELOG.md` en «Sin desplegar».

# Archivos a tocar

`web/admin.html`, `web/js/admin.js`, `tests/test_estaticas_guardas.py`, `CHANGELOG.md`. **No toques nada más**: no cambies `backend/routes/public.py` (otra rama lo tiene), ni `web/js/views/calidad.js` (AUTO-07 en curso), ni la CSP.

# Criterio de listo (verificable)

- `python dev.py run --demo` y, en `http://127.0.0.1:8000/web/admin.html`, entrar con el token de demo: la pestaña «Salud» existe, muestra las cinco tarjetas con datos reales del demo y no deja la consola con errores.
- `python dev.py test -k estaticas` en verde (con la guarda nueva).
- `python dev.py check` en verde.

Verifica con `/verificar` y entrega con `/entregar-pr`. No mergees por iniciativa propia.


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.

---
id: MOD-03
repo: brasas
rama: feat/cola-moderacion-con-contexto
modelo: swe-2-high
riesgo: B
archivos: web/js/admin.js, web/admin.html, tests/js/admin.test.mjs, CHANGELOG.md
e2e: no
intento: 0
ronda_review: 0
estado_desde: 2026-10-20T10:10:17
nota: Reencolado: la corrida falló por rate limit del modelo gratis, no por el ítem.
---

# Objetivo

Que quien modera vea, en la misma tarjeta del reporte, a qué distancia está del incendio más cercano conocido, para no publicar como «vecino vio humo» un aviso que está a 40 km de cualquier fuego (o que sí es la corroboración de un incendio real).

# Ítem del backlog

Prioridad de esta ronda (mapa y realismo): un reporte verificado se publica en el mapa para todo Chile. La decisión de verificarlo hoy se toma a ciegas respecto de los incendios, y la calidad de lo publicado es la calidad del mapa.

# Evidencia de que está pendiente

- `web/js/admin.js:76-105` (`render`): cada tarjeta muestra foto, tipo, comuna, hora, corroboraciones, descripción y un enlace crudo a OpenStreetMap con lat/lon. No hay ninguna referencia a los incidentes de BRASA.
- `web/js/admin.js:53-62` (`load`): solo pide `/api/admin/reports`; nunca consulta `/api/incidents`, aunque `web/js/api.js:133` ya expone `incidents(hours, hulls)`.
- `backend/routes/community.py:313-345` (`moderation_queue`) entrega `lat`, `lon` y `comuna_code` sin contexto de incendios: el moderador tiene que abrir OSM en otra pestaña y comparar a ojo con el mapa.
- `web/admin.html` no explica qué hacer con esa información: no hay leyenda ni umbral.

# Qué hacer

1. En `web/js/admin.js`, exporta una función pura `cercaDe(report, incidents)` que devuelva `{km, incident}` del incidente más cercano (haversine, la fórmula cabe en 6 líneas; no importes `map.js`) o `null` si no hay ninguno a menos de 20 km o si al reporte le falta lat/lon.
2. Al cargar la cola, pide una sola vez `/api/incidents?hours=48` con `api.incidents(48)` y guarda el resultado; si la llamada falla, la tarjeta no muestra la línea (la cola nunca se rompe por esto).
3. En cada tarjeta, una línea nueva bajo la comuna: «A 2,3 km del incidente más cercano (posible, 12 focos, última detección hace 20 min)» o, cuando no hay ninguno, «Sin incendios a menos de 20 km: revisa si es una quema». Usa `Intl.NumberFormat('es-CL')` para el km y el `ago()` que ya importa el archivo.
4. En `web/admin.html`, una línea de leyenda en la cabecera de la cola explicando el umbral de 20 km y que la distancia es a la huella del incidente, no a un perímetro oficial.

# Archivos a tocar

`web/js/admin.js`, `web/admin.html`, `tests/js/admin.test.mjs` (nuevo), `CHANGELOG.md`. **No toques nada más**: `backend/routes/community.py` está tomado por FUEGO-06 (misma ronda), y `web/js/views/mapa.js`, `web/js/map.js` y `web/js/api.js` están tomados por PRs abiertos. La página de moderación no se toca en el e2e (`browser_checks.py` no la recorre), por eso este ítem no lleva e2e.

# Criterio de listo (verificable)

`tests/js/admin.test.mjs` (lo corre `node --test tests/js`, que ya usa `dev.py`):

- con dos incidentes a 3 km y 12 km, `cercaDe` devuelve el de 3 km con `km` redondeado a un decimal;
- sin incidentes devuelve `null`; con el más cercano a 25 km devuelve `null` (fuera del umbral);
- un reporte sin `lat`/`lon` devuelve `null` y no lanza;
- un incidente sin coordenadas se ignora sin romper el cálculo;
- el texto formateado dice «2,3 km» (coma decimal chilena).

`node --test tests/js` en verde y `python dev.py check` en verde. En la demo, con `ADMIN_TOKEN` de `seed_demo`, la cola muestra la línea de distancia y una tarjeta sin incendios cercanos muestra la frase de quema.

Verifica con `/verificar` y entrega con `/entregar-pr`. No mergees por iniciativa propia.


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.

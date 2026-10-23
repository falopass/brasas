---
id: AUTO-03
repo: brasas
rama: feat/calidad-diagnostico-accionable
modelo: swe-2-high
riesgo: B
archivos: web/js/views/calidad.js, tests/js/calidad.test.mjs, CHANGELOG.md
e2e: si
intento: 0
ronda_review: 0
estado_desde: 2026-10-20T10:10:17
nota: Reencolado: la corrida falló por rate limit del modelo gratis, no por el ítem.
---

# Objetivo

Que la vista **Calidad** deje de ser una tabla de puntos rojos y verdes y pase a responder, en una frase, «qué está fallando ahora, qué significa para mí y qué se está haciendo». Además, un botón «Copiar diagnóstico» para que cualquiera pueda reportar la falla sin transcribir tablas.

# Ítem del backlog

Prioridad de producto de esta ronda: auto-mejora — «que el propio producto detecte y reporte sus fallas (datos viejos, fuentes caídas, páginas lentas, errores 5xx) y **proponga el arreglo**». La vista existe (QA-05) y muestra los insumos crudos, pero no diagnostica ni propone.

# Evidencia de que está pendiente

- `web/js/views/calidad.js:83-108` (`sourcesTable`) pinta por fuente la última corrida, el último éxito y una tira de 20 puntos, sin traducir nada a lenguaje de usuario.
- `web/js/views/calidad.js:65-81` (`summary`) arma KPIs sueltos (frescura, barridos) pero no los combina en un veredicto.
- `web/js/views/calidad.js:232-246` (`render`) apila secciones: fuentes, cuota FIRMS, respuesta CONAF, barridos, incidentes abiertos, opinión y licencias. Ninguna dice qué hacer cuando algo lleva horas fallando.
- El insumo correcto ya llega a la vista: `/api/status?history=20` trae `freshness`, `history` por producto, `last_cycle` y `ingest_mode`; no hace falta backend nuevo.

# Qué hacer

1. Una **función pura exportada** `diagnostico(status)` en `web/js/views/calidad.js` que devuelva una lista de problemas `{clave, gravedad, titulo, detalle, arreglo}`:
   - `datos_viejos` si `freshness.stale` o `last_ingest_at` tiene más de 30 min (gravedad alta);
   - `fuente_caida:<producto>` si un producto acumula ≥3 corridas seguidas con `ok: false` en `history`;
   - `respaldo` si `last_cycle.backup === false`;
   - `ingesta_apagada` si `ingest_mode === 'apagada'`;
   - lista vacía cuando no hay nada que reportar (y la vista muestra «Todo al día»).
   Cada problema trae su `arreglo` en palabras simples, sin jerga: «Estamos reintentando la consulta a FIRMS; pueden faltar focos de las últimas horas» / «Los datos de los satélites están atrasados: que no veamos calor no significa que no haya fuego».
2. Renderizar ese bloque **arriba** de las tablas, con el tono de color que ya usa la vista (`.status-badge`, `--risk-*`), y mantener las tablas como están.
3. Botón «Copiar diagnóstico»: arma texto plano con fecha, versión si está disponible, los problemas y los conteos por producto; **sin** datos personales, sin tokens y sin URL con claves; `navigator.clipboard.writeText` con `toast` de confirmación y mensaje de error si falla.

# Archivos a tocar

`web/js/views/calidad.js`, `tests/js/calidad.test.mjs`, `CHANGELOG.md`. **No toques nada más**: no cambies `web/index.html`, ni `web/js/app.js`, ni `web/sw.js`, ni `web/css/app.css` (hay PRs abiertos con esos archivos), y no agregues suites nuevas a `tests/js/` (el índice está en curso: extiende `calidad.test.mjs`, que ya existe).

# Criterio de listo (verificable)

Extiende `tests/js/calidad.test.mjs`:

- `diagnostico({})` → `[]`; con `freshness: {stale: true}` → incluye `datos_viejos` con gravedad alta;
- con `history: {FIRMS: [{ok:false},{ok:false},{ok:false}]}` → incluye `fuente_caida:FIRMS`;
- con dos productos sanos y uno caído, solo aparece el caído;
- el texto de «Copiar diagnóstico» no contiene `token`, `MAP_KEY` ni `FIRMS_MAP_KEY`, y mide ≤ 4000 caracteres;
- `node --test tests/js/` en verde, `python dev.py check` en verde y E2E en verde.

Verifica con `/verificar` y entrega con `/entregar-pr`. No mergees por iniciativa propia.


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.

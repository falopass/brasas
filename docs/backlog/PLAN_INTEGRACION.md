# Plan de integración de los 81 encargos (23-oct-2026)

Agrupa los encargos de `docs/backlog/` en **tandas** según los archivos que comparten (campo `archivos:` de cada encargo). Cada tanda es una rama y un PR con auto-merge (`AGENTS.md`). Estado de partida: `_estado-2026-10-23.md`.

## Reglas de ejecución

- **Una tanda = una rama = un PR**, con todos sus IDs en el título. Dentro de la tanda, un commit por encargo.
- **Tandas que comparten archivos van en secuencia**: la siguiente parte de `main` después del merge de la anterior. Las que no comparten archivos pueden ir **de a dos en paralelo**.
- **`CHANGELOG.md`** lo tocan casi todos: una entrada por tanda. Si dos PRs chocan ahí, el segundo se rebasa (`--force-with-lease`) y el auto-merge sigue.
- **Modelo**: todo se trabaja en sesiones Fusion (nota del dueño del 20-10: «lo vistoso va después, con Fusion»). El lead escribe la especificación que falte y revisa el diff; el sidekick implementa. Las tandas de contenido (T1, T2, T4) pueden ir con `swe-2-high` solo si se quiere ahorrar cuota.
- **Revisiones obligatorias**: `geo-reviewer` en las tandas marcadas *geo*; en las marcadas *crítico* (reportes, formulario o service worker), el CI tiene que pasar las pruebas de reportes y el e2e.
- Al mergear, cada encargo pasa a `hecho/` en el mismo PR.

## Fase 0 — Limpieza (antes de programar)

**Hecha el 23-10-2026.**

| Qué | Encargos | Resultado |
|---|---|---|
| Descartados (en `descartados/`) | PESO-03, PESO-04, DIETA-01 | Buscaban «devolver `main` a verde» por un arranque de 252,2 KB contra un tope de 252. Hoy el presupuesto está holgado: bloqueante 134,3 KB de 180 y páginas bajo demanda 62,5 KB de 75 (`dev.py check` del 23-oct, con DEBT-07 #674). |
| Unificados (originales en `unificados/`) | AUTO-10 ← AUTO-01, AUTO-14 · OPS-29 ← AUTO-09 · DAT-05 ← DAT-03, DAT-04, DAT-09 · VEC-01 ← UX-56, UX-63 · FAQ-01 ← CONT-17, UX-55 · AUTO-03 ← AUTO-07 · ALR-26 ← ALR-24 · FUEGO-45 ← FUEGO-22, FUEGO-34 · PESO-05 ← PERF-07 | Pedían lo mismo sobre los mismos archivos. Cada encargo principal lleva al final la sección «Unificado el 23-10-2026» con lo que suma cada uno y `archivos:` con la unión. |
| Falta la especificación (en el `/plan`) | DET-45, MAPA-105, AGUA-07 | Tienen la decisión tomada pero no traen archivos ni pasos. |
| Solo el dueño | OPS-12 (rotar la clave de FIRMS), OFI-04 (pedir acceso oficial a SENAPRED) | No son código. |

Quedan **63 encargos**: 61 de código y los 2 del dueño.

## Fase 1 — Tandas independientes (bajo riesgo; de a dos en paralelo)

| Tanda | Encargos | Archivos que comparten | Notas |
|---|---|---|---|
| T1 · «¿Qué hago si…?» | UX-57, UX-61, UX-72 | `web/js/views/quehago.js` | Contenido con fuente. |
| T2 · Preguntas frecuentes | FAQ-01 (incluye CONT-17 y UX-55) | `web/preguntas.html`, `tests/test_preguntas.py` | También toca `calidad.js` (enlace): va antes que T5. |
| T3 · Datos abiertos (página) | DAT-05 (incluye DAT-03, DAT-04 y DAT-09) | `web/datos.html`, `web/js/datos.js` | |
| T4 · Versión liviana | MAPA-02, UX-70 | `web/lite.html`, `web/js/lite.js` | |
| T5 · Vista Calidad | AUTO-03 (incluye AUTO-07), AUTO-11 | `web/js/views/calidad.js` | Después de T2. |
| T6 · Prepárate | PREP-03, UX-59 | `web/js/views/preparate.js` | |
| T7 · Automatización del repo | AUTO-06, OPS-27, OPS-28 | `.github/scripts/`, `.github/workflows/` | No toca la app. |
| Sueltos (en cualquier hueco) | ALR-28, ALR-30, SAT-01, QA-72, DET-06, DAT-06, RISK-23 | Sin archivos compartidos | QA-72 y RISK-23 son *geo*. |

## Fase 2 — Zonas calientes (en el orden de la tabla)

| Orden | Tanda | Encargos | Archivos que comparten | Notas |
|---|---|---|---|---|
| 1 | T8 · Salud y frescura (backend) | AUTO-10 (incluye AUTO-01 y AUTO-14), AUTO-16, FUEGO-08 | `backend/main.py`, `backend/diagnostics.py`, `backend/routes/diagnostico.py` | Una sola API de diagnóstico; reutilizar el acumulador de `/api/observability/routes`, que ya existe. |
| 2 | T9 · Panel de administración | OPS-29 (incluye AUTO-09), MOD-03 | `web/admin.html`, `web/js/admin.js` | Después de T8 (AUTO-14 también toca el admin). |
| 3 | T10 · Página de focos | FOCOS-01 | `backend/main.py`, `web/index.html` | Después de T8. |
| 4 | T11 · Datos abiertos (API) | DAT-08, DAT-10, DAT-11 | `backend/routes/opendata.py`, `docs/API.md` | Después de T3 (DAT-11 toca la página). |
| 5 | T12 · Avisos | ALR-26 (incluye ALR-24), ALR-20, ALR-19, AGUA-07 | `backend/alerts.py`, `backend/services.py` | **Crítico**: ALR-19 toca `web/js/ui.js`. Lógica de avisos: pruebas obligatorias. |
| 6 | T13 · Calendario | CAL-02, ALR-23 | `backend/routes/calendar.py` | ALR-23 toca `vecino.js`: antes de T15. |
| 7 | T14 · Mi zona (solo interfaz) | MZ-03, MZ-05, RISK-22, UX-64, UX-62, VEC-02 | `web/js/views/zona.js` | `zona.js` es el archivo más compartido (12 encargos). |
| 8 | T15 · Mi zona (backend) | MZ-01, TEMP-03, VEC-01 (incluye UX-56 y UX-63), UX-48 | `backend/routes/personal.py`, `zona.js`, `vecino.js`, `web/js/api.js` | MZ-01 y VEC-01 comparten `trend` en `build_summary`. UX-48 agrega datos de familia (`db.py`): revisar privacidad (SEC-01..05). |
| 9 | T17 · Clima en Mi zona | AGUA-09, QUEMA-01 | `backend/routes/climate.py`, `zona.js`, `preparate.js` | Después de T6 y T14. |
| 10 | T18 · Ficha del incendio | FUEGO-14, FUEGO-17 | `web/js/views/incendio.js` | FUEGO-17 es *geo* (rumbo del viento contra los lugares). |
| 11 | T19 · Reportes | REP-01 | `web/js/ui.js`, `web/js/reportes.js`, `web/js/api.js` | **Crítico**. Después de T12 y T15. |

## Fase 3 — Pesados y geoespaciales (Fusion con especificación previa del lead)

| Tanda | Encargos | Archivos que comparten | Notas |
|---|---|---|---|
| T20 · Mapa | RISK-07 (viento animado), MAPA-105 (capas base) | `web/js/map.js`, `web/js/views/mapa.js` | *geo*. RISK-07 también toca `services.py` y `public.py`. |
| T21 · Pendiente en el escenario | FUEGO-45 (incluye FUEGO-22 y FUEGO-34) | `backend/fwi.py`, `backend/routes/public.py` | *geo*. |
| T22 · Rayos en el incidente | DET-23 | `backend/incidents.py`, `backend/db.py`, `incendio.js` | *geo*, ingesta. Después de T18. |
| T23 · Falsos positivos del norte | DET-45 | ingesta (por especificar) | *geo*. Máscara regional decidida el 21-10. |
| T24 · Páginas por comuna | SEO-05 | `deploy/`, `backend/main.py`, `web/sitemap.xml` | Cambia URLs indexadas y toca `deploy/`. Después de T10. |
| T25 · Peso (opcional) | PESO-05 (incluye PERF-07) | `privacidad.js`, `licencias.json` | Solo si hace falta margen. |

## Bloqueados por algo externo

| Encargo | Qué falta |
|---|---|
| OFI-33 | Clave del portal de la DMC. |
| OFI-10 (SINCA) y OFI-25 (campamentos del MINVU) | Licencia por verificar; se puede dejar el código listo y apagado tras un flag, como OFI-17. |
| OPS-12, OFI-04 | Acción del dueño. |

## Orden sugerido

1. Fase 0 hecha. En el `/plan`: especificar DET-45, MAPA-105 y AGUA-07.
2. Fase 1: T1 + T3, luego T2 + T4, luego T5 + T6, luego T7 y los sueltos.
3. Fase 2 en el orden de la tabla. Si no comparten archivos, T8 puede ir junto a T12, y T14 junto a T11.
4. Fase 3, una tanda a la vez.

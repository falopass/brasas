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

## Resultado (24-10-2026)

Todas las tandas de código quedaron mergeadas en `main` con el CI en verde, y cada merge se desplegó solo. Los encargos están en `hecho/`.

| Tanda | Encargos | PR |
|---|---|---|
| T1 «¿Qué hago si…?» | UX-57, UX-61, UX-72 | #683 |
| T2 Preguntas frecuentes | FAQ-01 (CONT-17, UX-55) | #685 |
| T3 Datos abiertos (página) | DAT-05 (DAT-03, DAT-04, DAT-09) | #684 |
| T4 Versión liviana | MAPA-02, UX-70 | #686 |
| T5 Vista Calidad | AUTO-03 (AUTO-07), AUTO-11 | #691 |
| T6 Prepárate | PREP-03, UX-59 | #687 |
| T7 Automatización del repo | AUTO-06, OPS-27, OPS-28 | #688 |
| Sueltos A | ALR-28, SAT-01, DAT-06 | #689 |
| Sueltos B | ALR-30, QA-72, DET-06, RISK-23 | #690 |
| T8 Salud del sistema | AUTO-10 (AUTO-01, AUTO-14), AUTO-16, FUEGO-08 | #692 |
| T9 Panel de administración | OPS-29 (AUTO-09), MOD-03 | #694 |
| T10 Página de focos | FOCOS-01 | #699 |
| T11 Datos abiertos (API) | DAT-08, DAT-10, DAT-11 | #697 |
| T12 Avisos | ALR-26 (ALR-24), ALR-20, ALR-19 | #693 |
| T13 Calendario | CAL-02, ALR-23 | #695 |
| T14 Mi zona (interfaz) | MZ-03, MZ-05, RISK-22, UX-64, UX-62, VEC-02 | #696 |
| T15 Mi zona (backend) | MZ-01, TEMP-03, VEC-01 (UX-56, UX-63), UX-48 | #704 |
| T17 Clima en Mi zona | AGUA-09, QUEMA-01, AGUA-07 | #708, #710 |
| T18 Ficha del incendio | FUEGO-14, FUEGO-17 | #698 |
| T19 Reportes | REP-01 | #707 |
| T20 Mapa | RISK-07, MAPA-105 | #700, #709 |
| T21 Pendiente en el escenario | FUEGO-45 (FUEGO-22, FUEGO-34) | #701, #710 |
| T22 Rayos en el incidente | DET-23 | #712 |
| T23 Falsos positivos del norte | DET-45 | #703 |
| T24 Páginas por comuna | SEO-05 | #702 |
| T25 Peso | PESO-05 (PERF-07) | #705 |

Arreglos de CI fuera de tanda: #706 (constante del precache) y #713 (espera del e2e para capas que cargan datos).

**Pendiente de decisión del dueño**
- ~~Base «Satélite» del mapa (MAPA-105)~~ — resuelto en #717: vintage 2016 de EOX, CC BY 4.0.
- ~~Textos de consejo DMC de lluvia y tormenta~~ — resuelto en #717 (frases oficiales de SENAPRED).
- Máscara del norte (DET-45): la lista de celdas está vacía hasta medir la temporada con `scripts/local/medir_falsos_positivos.py` (INV-25 §8).

**Seguimientos técnicos chicos**
- ~~Rayos (DET-23): paso GLM en el ciclo~~ — resuelto en #716.
- ~~`/api/diagnostico` y `/api/datos-versionados`: cachear el cálculo~~ — resuelto en #716.
- ~~JSON-LD bajo la CSP sin hash~~ — no aplica: la CSP no rige bloques de datos y `inline_script_hashes()` excluye `ld+json` a propósito.

## Fase 4 — Mejoras del 24-10-2026 (en los hosts)

Aprobadas por el dueño el 24-10: las seis tandas de mejoras para la gente, el móvil y el mapa del fuego. Decisión sobre SENAPRED (ALR-42): Alerta Roja u orden de evacuación → **urgente**; Amarilla y Temprana Preventiva → **aviso**.

Regla: cada PR es **dueño exclusivo** de sus archivos mientras está abierto; un archivo pasa al siguiente PR solo después del merge. `CHANGELOG.md` es la única excepción (el segundo rebasa con `--force-with-lease`).

**Ola 1 (en paralelo)**

| PR / rama | Encargos | Archivos propios | Host · modelo |
|---|---|---|---|
| PR1 `feat/fuego-visible` | MAPA-151, MAPA-152, MAPA-153, MAPA-154 | `web/js/map.js`, `web/js/capas.js`, `web/js/views/mapa.js`, `scripts/local/validate_palette.mjs` | brasa-heavy · swe-2-high · *geo* |
| PR2 `feat/senapred-avisos` | ALR-42, OFI-207 (backend) | `backend/alerts.py`, `backend/services.py`, `backend/providers/senapred.py`, `backend/routes/oficiales.py`, `backend/db.py`, tests nuevos | brasa-heavy-2 · swe-2-max · *geo* |
| PR3 `feat/avance-por-hora` | MAPA-156, UX-77 (ficha), UX-73 (ficha) | `web/js/views/incendio.js` | brasa-heavy-3 · swe-2-high |
| PR4 `fix/panel-movil` | UX-73 (`index.html`), UX-74, UX-77 (Prepárate), UX-78 (plan) | `web/index.html`, `web/css/app.css`, `web/js/views/preparate.js`, `web/js/plan.js` | flex-heavy · swe-2-medium |
| PR5 `feat/insignia-y-ahorro` | UX-75, UX-76 (parte 1) | `web/sw.js`, `web/js/push.js`, `web/js/store.js`, `web/js/viento.js`, `web/js/app.js`, `web/js/ui.js` | verify-heavy · swe-2-high · *crítico* |
| Investigación (docs) | Licencia del DEM para MAPA-155 | `docs/investigacion/INV-29-relieve.md` | devin-vm · swe-2-medium |

**Ola 2**

| PR / rama | Encargos | Archivos propios | Espera a |
|---|---|---|---|
| PR6 `feat/capas-relieve-senapred` | MAPA-155, OFI-207 (capa), UX-76 (latido) | `web/js/map.js`, `web/js/capas.js`, `web/js/views/mapa.js`, `docs/FUENTES.md`, `web/data/licencias.json` | PR1, PR2, PR5 e INV-29 |
| PR7 `feat/compartir-foto-reporte` | UX-79 | `web/manifest.webmanifest`, `web/sw.js`, `web/js/ui.js`, `web/js/reportes.js` | PR5 · *crítico* |
| PR8 `feat/avisos-humo-acercamiento` | AGUA-207 (backend), ALR-43 | `backend/alerts.py`, `backend/services.py`, `backend/routes/personal.py`, `backend/db.py`, tests nuevos | PR2 · *geo* |

**Ola 3**

| PR / rama | Encargos | Archivos propios | Espera a |
|---|---|---|---|
| PR9 `fix/mapa-movil` | UX-73, UX-77 y UX-78 en la vista Mapa | `web/js/views/mapa.js` | PR6 |
| PR10 `feat/opcion-humo-lugar` | AGUA-207 (interruptor) | `web/js/ui.js` | PR7 y PR8 |

Un encargo repartido en varios PR (UX-73, UX-76, UX-77, UX-78, OFI-207, AGUA-207) pasa a `hecho/` con el último de ellos.

### Resultado (25-10-2026)

Los diez PR quedaron mergeados en `main` con el CI en verde y cada merge se desplegó solo; los 17 encargos están en `hecho/`. Todas las sesiones corrieron en los hosts con SWE-2 (`swe-2-medium`, `swe-2-high`, `swe-2-max`).

| PR | Encargos |
|---|---|
| #729 | UX-73 (`index.html`), UX-74, UX-77 (Prepárate), UX-78 (plan) |
| #730 | UX-75, UX-76 (parte 1) |
| #731 | MAPA-151, MAPA-152, MAPA-153, MAPA-154 |
| #732 | MAPA-156, UX-77 (ficha), UX-73 (ficha) |
| #733 | ALR-42, OFI-207 (avisos + endpoint nacional) |
| #734 | UX-79 |
| #735 | MAPA-155, OFI-207 (capa del mapa), UX-76 (latido) |
| #736 | ALR-43, AGUA-207 (backend) |
| #737 | AGUA-207 (interruptor del lugar) |
| #738 | UX-73, UX-77 y UX-78 (vista Mapa) |
| docs | INV-29 (Mapterhorn elegido como fuente DEM del relieve) |

## Fase 5 — Frontend: mapa móvil, Mi zona al día y funciones nuevas (25-10-2026, en los hosts)

Aprobada por el dueño el 25-10. Sale de la auditoría del 25-10:
- un toque abría varias fichas y ganaba la última;
- los focos eran blancos de 8 a 16 px sin tolerancia;
- la ficha quedaba detrás de la hoja;
- marcar la casa aceptaba un toque a cualquier zoom;
- Mi zona no refrescaba el estado de los lugares mientras estaba abierta;
- había 7 pestañas en el celular.

Decisiones del dueño:
- solo frontend (el backend no se toca);
- 5 pestañas con «Más»;
- el fondo OpenTopoMap pasa a llamarse «Topográfico».

Antes de la Ola 1: PR #739 (puntos de Mi zona tocables) con `popup.js` en `SHELL` y un solo listener.

Regla: igual que en la Fase 4, cada PR es **dueño exclusivo** de sus archivos. Dos excepciones:
- `views/zona.js` se reparte **por función** en la Ola 1: PR11 tiene solo el registro del toque y la leyenda (`aplicar` y `unmount`); PR12 tiene `render`, `paint` y las suscripciones.
- `CHANGELOG.md`, `web/css/app.css` y `scripts/local/browser_checks.py` admiten bloques propios por PR; el que llega segundo rebasa.

**Ola 1 (en paralelo; espera a #739)**

| PR / rama | Encargos | Archivos propios | Host · modelo |
|---|---|---|---|
| PR11 `feat/toque-y-ficha` | MAPA-157, MAPA-158, MAPA-159, MAPA-160, MAPA-162 (Mapa) | `web/js/map.js`, `web/js/capas.js`, `web/js/popup.js`, `web/js/views/mapa.js`, `web/js/app.js`, `web/js/views/zona.js` (toque y leyenda), `web/css/app.css` (MapLibre, ficha, controles, leyenda), `scripts/local/browser_checks.py`, `tests/js` | brasa-heavy · swe-2-max |
| PR12 `fix/mi-zona-al-dia` | MZ-06, MZ-07, MAPA-162 (Mi zona) | `web/js/views/zona.js` (`render`, `paint`, suscripciones), `web/js/pildora.js`, `tests/js/pildora.test.mjs`, `tests/js/zona.test.mjs` | brasa-heavy-2 · swe-2-high |
| PR13 `feat/pin-preciso` | MAPA-161 | `web/js/ui.js`, `web/index.html` (`#pick-hint`), `web/css/app.css` (bloque `/* MAPA-161 */`) | brasa-heavy-3 · swe-2-max · *crítico* |

**Ola 2 (espera a la Ola 1)**

| PR / rama | Encargos | Archivos propios | Host · modelo |
|---|---|---|---|
| PR14 `feat/incendios-con-nombre` | MAPA-163, MAPA-165 | `web/js/map.js`, `web/js/capas.js`, `web/js/popup.js`, `web/js/views/mapa.js`, `web/preguntas.html`, `scripts/local/browser_checks.py`, `tests/js` | brasa-heavy · swe-2-high |
| PR15 `feat/mi-zona-contexto` | MZ-08, MZ-09 | `web/js/views/zona.js`, `web/js/views/vecino.js` (si cambia `placeBody`), `web/css/app.css` (bloque `/* MZ-09 */`), `tests/js/zona.test.mjs` | brasa-heavy-2 · swe-2-high |
| PR16 `feat/navegacion-movil` | UX-80, UX-81 | `web/js/app.js`, `web/js/views/mas.js` (nuevo), `web/js/views/incendio.js` (enlaces de volver), `web/sw.js`, `web/css/app.css` (barra inferior), `tests/test_enlaces_internos.py` | brasa-heavy-3 · swe-2-high · *crítico* |

**Ola 3 (espera a la Ola 2)**

| PR / rama | Encargos | Archivos propios | Host · modelo |
|---|---|---|---|
| PR17 `feat/controles-mapa-movil` | MAPA-164 | `web/js/views/mapa.js`, `web/js/map.js` (solo `BASEMAPS`), `web/css/app.css` (bloque `/* MAPA-164 */`), `web/preguntas.html`, `docs/FUENTES.md`, `tests/js/map.test.mjs` | brasa-heavy · swe-2-max |
| PR18 `feat/cerca-de-mi` | MZ-10 | `web/js/cerca.js` (nuevo), `web/sw.js`, `web/js/views/zona.js` (botón), `web/js/map.js` (aviso tras «Mi ubicación»), `tests/js/cerca.test.mjs` | brasa-heavy-2 · swe-2-high · *crítico* |

Un encargo repartido en varios PR (MAPA-162) pasa a `hecho/` con el último de ellos. En espera de decisión: ALR-44, MAPA-166 y MAPA-167.

## Resultado — Fase 5 cerrada (2026-10-26)

Las tres olas quedaron integradas en `main` vía PR con CI en verde:

- **Ola 3:** #747 (MZ-10, `eb98c98`), #748 (MAPA-164, `f0587bb`), #749 (correcciones de la revisión Devin sobre `cerca.js`, `7a4ab70`).
- Correcciones de lead durante la revisión: presupuestos del shell y del arranque re-medidos con nota fechada (`test_presupuestos_peso.py`, `test_peso_arranque.py`), tope del cuerpo de «Capas» sobre la hoja en móvil, y **la causa del fallo flaky de `check_mapa_capas`**: desincronía `layers`↔`visibility` en `mapa.js` — el resumen/leyenda ahora responden al instante (`applyLayers` antes de la carga diferida), las capas que fallan al cargar se apagan de verdad, `viento` se resetea como las demás y `unmount` apaga todas las capas opcionales, incluido el canvas de partículas (`viento.js#apagar`).

**Sondas de producción (GET, `brasa-chile.ddiegosebastianbb.workers.dev`):** `/api/status` 200 (frescura 142 s, no stale) · `web/js/cerca.js` 200 (13,3 KB) · `web/js/views/mapa.js` sirve chips y `GRUPOS_CAPAS` · `web/sw.js` precachea `cerca.js` · `web/js/views/zona.js` sirve el botón «¿Hay fuego cerca de mí?» · `/api/official-fires` 8 incendios CONAF con `source.url` presente.

## Resultado — Ola 4 cerrada (2026-10-26)

Los cuatro encargos quedaron integrados en `main` vía PR con CI en verde:

- **#751** (filtro en `focos.html`, `f881acd`): la lista en texto gana un filtro por comuna, región o nombre — la que se usa con señal lenta y lectores de pantalla.
- **#752** (MAPA-166, `674bff9`): descarga del mapa de un lugar desde Privacidad, por acción explícita, topes OpenFreeMap (≤3.000 recursos, ≤4 en paralelo, ~15 MB propios), teselas preservadas entre versiones del SW.
- **#754** (ALR-44, `9149871`): seguir un incendio concreto sin guardar lugar — `incident_follows` + `follow_alerts`, avisos de confirmación CONAF, cambio de estado y calor nuevo, tope de un aviso cada 3 h, caducidad a los 7 días, topes anti-fatiga, exportación de privacidad incluida.
- **#753** (MAPA-167, `090f8ec`): el buscador del mapa resuelve localidades y sectores además de comunas (índice OSM/ODbL diferido, comunas primero, tope 8).

Correcciones de lead durante la revisión:
- #753: política de frescura para `localidades.json` en `revisar_datos_versionados.py`; ~780 B de recortes para el presupuesto de 300 KB (comentarios, `buscar()` compartido, `data-h`, sin caché localStorage del índice).
- **Bug real encontrado por el e2e**: `elegir()` llamaba `fly()` antes que `onElegir()`; el «peek» de la hoja publicaba `sheetPx` y `setPadding` cancelaba el flyTo recién iniciado — el buscador nunca llegaba al punto (afectaba también a comunas). Ahora la hoja se acomoda primero.
- El chequeo de localidad proyecta el punto a pantalla en vez de medir `getCenter()` (`viewPadding` centra en la franja visible, no en el canvas).
- Presupuestos e2e subidos por el runner congestionado (LCP ~12 s): capas 9→18 s, lienzo 3→6 s.
- #754: el agente corrió `geo-reviewer` (6 hallazgos corregidos) y adelgazó su propio exceso del presupuesto de arranque.

**Sondas de producción (GET):** `web/data/localidades.json` 200 · `web/js/buscador.js` 200 · `/api/me/follows` 401 (ruta viva, exige suscriptor) · `web/sw.js` en `brasa-090f8ec6` (merge de #753).

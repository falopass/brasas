---
id: MOV-02
repo: brasas
rama: feat/movil-tactiles
modelo: swe-2-high
riesgo: B
archivos: web/css/app.css, web/css/lista.css, tests/test_movil_tactiles.py, docs/backlog/hecho/MOV-02.md, CHANGELOG.md
e2e: no
intento: 0
ronda_review: 0
estado_desde: 2026-11-10T00:00:00
nota:
---

# MOV-02 · Objetivos táctiles de 44 px y lectura en 360 px

**Objetivo.** Que en el teléfono ningún control de la app quede por debajo de
44 px de objetivo táctil (salvo enlaces dentro de un párrafo) y ningún texto
baje de 12 px reales, a 360 y 390 px de ancho y sin scroll horizontal.

**Evidencia medida en producción** (Playwright, 360 y 390 px, móvil táctil,
10-nov-2026). Sin scroll horizontal en ninguna vista. Objetivos táctiles por
debajo de 44 px en el teléfono (ancho × alto):

| Elemento | Medida | Vistas |
|---|---|---|
| `#live-pill` (píldora «Hace 5 min») | 137 × 30 | todas |
| `#settings-btn-m` (chip «Aa») | 47 × 30 | todas |
| `#emergency-btn` («130 · 132») | 90 × 30 | todas |
| `#sheet-handle` (asa de la hoja) | 360 × 30 | todas |
| `.btn` («¿Hay fuego cerca de mí?», «Agregar mi casa», «Veo humo o fuego», «Activar avisos») | alto 40 | todas |
| `.btn-sm` (incluye «Cerrar» de los modales, `.modal-x`) | alto 34 | modales |
| `.row-btn` (listas de incidentes, regiones, CONAF) | alto 18–37 | mapa, casos, riesgo |
| `.chip` (filtros por región en Historia) | alto 32 | casos |
| enlace «Ver la ficha» | 34 × 31 | mapa (lista) |
| botones de filtro del mapa sin texto visible (`button.chip «»`, 56–99 × 29) | alto 29 | mapa |
| `.day-cell` (pronóstico 7 días) | 42 × 73 | riesgo |
| casillas `input[type=checkbox]` de los checklists (`#casa-*`, `#mant-*`, `#parcela-*`) | 20 × 20 | prepárate |
| `#casa-reset.reset-link` «Empezar de nuevo» | 98 × 16 | prepárate |

Lectura: el texto `.tiny`, `small`, `.x-plain`, `.status-badge`,
`.layers-group-title` y `.day-cell` medía 10,8–11,7 px en el teléfono (raíz en
15 px, así que `0.75rem` = 11,25 px), con más de 140 nodos así en Riesgo,
Prepárate y Calidad. En 360 px el chip «Aa» tocaba el botón «130 · 132» y una
etiqueta del mapa asomaba entre ambos; y el `h1.view-title` enfocado por
programa al cambiar de vista mostraba el recuadro de foco sin teclado.

**Qué se hizo.** Todo dentro de `@media (max-width: 899px)` en una sección
`/* MOV-02 */` de `web/css/app.css`, más `web/css/lista.css` para la hoja
imprimible y `/focos.html`:

1. `.btn`, `.btn-sm`, `.list .row-btn`, `.chip`, `.input`,
   `details.fold summary`, `.segmented button`, `.search-hit`, `.legend-fold`
   y `.toast-action` suben a `min-height: 44px` visible (`.btn-lg` y
   `.input-lg` conservan sus 50 px).
2. Barra superior: `gap: 8px`, los controles no se encogen (`flex: none`) y
   `#live-pill`, `#settings-btn-m` y `#emergency-btn` ganan 44 px de área
   táctil con `::before` (`inset: -7px 0`) sin cambiar su tamaño visible; la
   etiqueta «Emergencias» sigue solo en escritorio, como antes.
3. `#sheet-handle` y `button.day-cell` amplían su área táctil con `::before`
   (`-7px` vertical y `-4px` horizontal) sin crecer el elemento visible.
4. Checklists de «Prepárate»: la fila y la `label` llegan a 44 px tocables
   (`min-height`, `flex: 1` en la columna de texto) y la casilla a 24 px;
   la `label` se extiende con margen negativo sobre la columna de la casilla,
   así tocar bajo el cuadro también marca (revisión de Devin Review);
   `.reset-link` gana el área con relleno y margen negativo (renglón igual).
5. `.switch` (la `label` del conmutador) ofrece 44 px de alto sin cambiar la
   píldora de 44 × 26 px; `.older-check input` sube a 24 px; los botones de
   MapLibre miden 44 × 44 px con `pointer: coarse`.
6. Texto mínimo 12 px reales (`0.8rem` con la raíz en 15 px) para `small`,
   `.tiny`, `.tag`, `.status-badge`, `.kpi small`/`.kpi span`,
   `.figure-row small`, `.event-time`, `.fold-sm summary`, `.phone span`,
   `.day-cell`, `.br-mark`/`.br-inline`, `.layers-group-title`,
   `.tchart-*`, `.chart-legend`, `.q-n`, `.rd-n`, `.nav-link small` y
   `.case-card .badges .tag`; la barra de pestañas usa `min(0.8rem, 4vw)`.
   Sin cambios en titulares ni en la escala general; `data-text` sigue
   escalando desde la raíz.
7. `h1.view-title:focus { outline: none }`: el encabezado no es un control y
   no debe dibujar el anillo aunque el navegador lo marque `:focus-visible`;
   los controles conservan `:focus-visible`.
8. `web/css/lista.css`: las casillas `.kit`, las etiquetas, los enlaces de
   teléfono, `.size-toggle`, `.score-reset`, los campos `.blank` y los enlaces
   «Ver la ficha» de `/focos.html` quedan a 44 px (solo en `@media screen`;
   la hoja impresa no cambia) y los textos chicos suben a 9 pt (12 px).
9. `tests/test_movil_tactiles.py`: guarda que `.btn`, `.btn-sm` y `.row-btn`
   mantengan `min-height` ≥44 px en móvil o globalmente.

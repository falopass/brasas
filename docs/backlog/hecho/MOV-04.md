---
id: MOV-04
repo: brasas
rama: feat/movil-area-tactil
modelo: swe-2-high
riesgo: B
archivos: web/css/app.css, web/css/lista.css, web/js/views/alertas.js, web/focos.html, web/lite.html, web/js/lite.js, web/lista.html, tests/test_movil_tactiles.py, scripts/local/area_tactil.py, docs/backlog/hecho/MOV-04.md, CHANGELOG.md
e2e: no
intento: 0
ronda_review: 0
estado_desde: 2026-11-11T00:00:00
nota:
---

# MOV-04 · Área táctil real de 44 px en el asa y los teléfonos de emergencia

**Objetivo.** Que el asa de la hoja y los teléfonos de emergencia (130 CONAF,
132 Bomberos) respondan al dedo en un cuadrado de al menos 44 px reales —
medidos por hit-testing (`document.elementFromPoint`), no por la caja
dibujada. Los enlaces «SENAPRED», «DMC» y «CONAF» dentro de una frase quedan
exentos por la excepción de enlace en línea de WCAG 2.5.8.

**Evidencia medida en producción** (`brasa-901fe969`, 360 px, Chromium móvil,
11-nov-2026, `scripts/local/area_tactil.py`):

| Control | Dónde | Área tocable (ancho × alto) |
|---|---|---|
| `#sheet-handle` (asa de la hoja) | todas las vistas | 81 × 33-37 px |
| enlaces `tel:` «130» y «132» | vista Avisos (`#/alertas`) | 20 × 15 px |
| enlaces `tel:` «130» y «132» | `/focos.html` | 28 × 17 px |
| enlaces `tel:` «130» y «132» | `/web/lite.html` | 31 × 20 px |
| teléfonos `.phones li a` | `/web/lista.html` | 81 × 35 px |

**Causas.** El `::before` del asa (`inset: -7px 0`, MOV-02) solo ganaba los 7
px de abajo: `.panel` tiene `overflow: hidden` y recorta lo que sale por
arriba, y el contenido de `.panel-body` tapa parte de la franja inferior. Los
`tel:` eran texto en línea. En `lista.html` los márgenes negativos de MOV-02
(`margin: -6pt -8pt`) se pisaban entre vecinos y achicaban el área real.

**Qué se hizo.**

1. `web/css/app.css`: `.sheet-handle` mide 44 px de alto en móvil (la píldora
   dibujada no cambia) y sale del grupo de objetivos agrandados con
   `::before`: el panel recorta ese truco.
2. `#/alertas` (`web/js/views/alertas.js`): los `tel:` del pie y del estado
   de error pasan a un par de botones `.phone primary` (130 CONAF ·
   incendios forestales, 132 Bomberos) reutilizando `.phones`/`.phone` de
   `index.html`; el texto que los rodea queda igual.
3. `/focos.html`: los tres pasajes con `tel:` en línea (aviso `.official`,
   bloque de error y `<noscript>`) muestran ahora el par
   `<ul class="phones">` de `lista.css`, sin tocar el texto que los rodea.
4. `/web/lite.html` y `web/js/lite.js`: el paso «Llama ya…», la tarjeta
   compartida (`#/v/<token>`) y el aviso de datos atrasados ganan el par de
   botones `.phone primary`; `tel()` ahora construye el botón completo y
   `llamadas()` arma el par.
5. `lista.html` (`web/css/lista.css`): `.phones li a` deja los márgenes
   negativos y gana su área con `padding` y `min-height: 44px` (el `gap` de
   la grilla ya separa a los vecinos); `@media print` no cambia.
6. `tests/test_movil_tactiles.py`: guardas nuevas — el asa ≥44 px en móvil,
   ningún `tel:` fuera de `.phone`/`.phones` en las tres páginas ni en
   `lite.js`, y `.phones li a` sin márgenes negativos y con `min-height` ≥44.
7. `scripts/local/area_tactil.py`: script de medición por hit-testing.
   Uso: `python scripts/local/area_tactil.py <BASE> <salida.json> [ancho]`
   (recorre las once vistas de la app y las tres páginas estáticas; imprime
   por vista los controles con área tocable <44 px).

**Medición en producción después del merge** (la hace el orquestador):

| Control | Dónde | Área tocable |
|---|---|---|
| `#sheet-handle` | todas las vistas | _pendiente_ |
| `tel:` «130» y «132» | `#/alertas` | _pendiente_ |
| `tel:` «130» y «132» | `/focos.html` | _pendiente_ |
| `tel:` «130» y «132» | `/web/lite.html` | _pendiente_ |
| `.phones li a` | `/web/lista.html` | _pendiente_ |

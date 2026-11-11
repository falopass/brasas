---
id: VIS-01
repo: brasas
rama: fix/vista-mapa
riesgo: B
archivos: web/js/map.js, web/js/views/mapa.js, web/css/app.css, tests/test_vista_mapa.py, tests/js/buscador-teclado.test.mjs, docs/backlog/hecho/VIS-01.md, CHANGELOG.md
e2e: no
intento: 1
ronda_review: 0
estado_desde: 2026-11-11T00:00:00
nota:
---

# VIS-01 · Mapa legible y usable en teléfono y escritorio

**Objetivo.** Que el mapa se lea y se maneje en teléfono y escritorio: botón
«Actualizar» visible, controles con nombre en español, textos de al menos
12 px reales y buscador operable con teclado.

## Qué se hizo en cada punto

1. **«Actualizar» apagado** — `.map-refresh button` usaba `color: #333` (tinta
   oscura) sobre el fondo oscuro `--ov-bg` del grupo de MapLibre. Ahora usa
   `var(--ov-ink)`, igual que el resto de los controles (`web/css/app.css`).
2. **Controles en inglés** — `initMap` en `web/js/map.js` pasa `locale` al
   `new maplibregl.Map` con textos en español neutro para todas las claves
   del `defaultLocale` del `web/vendor/maplibre/maplibre-gl.js` servido por
   el repo (NavigationControl, GeolocateControl, ScaleControl,
   AttributionControl, FullscreenControl, TerrainControl, LogoControl,
   Marker, `Map.Title`, `Popup.Close`).
3. **Edad del dato a 9,4 px** — `.map-refresh .refresh-age` sube de `.625rem`
   a `0.8rem` (12 px con la raíz en 15 px) en escritorio; en teléfono sigue
   oculta (lo repite la píldora de arriba).
4. **Títulos de grupo a 11,25 px** — `.layers-group-title` (`.75rem`) se
   escribía después de la lista de lectura de MOV-02 y la ganaba por orden
   de cascada. Nueva regla acotada `.map-layers .layers-group-title,
   .map-filters .layers-group-title { font-size: 0.8rem }` en la sección
   `/* VIS-01: mapa */` tras `.maplibregl-ctrl-scale`.
5. **Buscador sin teclado** — en `bindBuscarComuna` (`web/js/views/mapa.js`):
   Flecha abajo lleva el foco al primer `.search-hit`, las flechas recorren
   la lista, Flecha arriba en el primero devuelve el foco al campo, Enter con
   resultados elige el primero, Escape cierra la lista y deja el foco en el
   campo; con 0 resultados Enter no toca el texto. El input suma
   `role="combobox"`, `aria-autocomplete="list"`, `aria-controls` y
   `aria-expanded` (se actualiza al pintar), más `autocapitalize="off"`,
   `autocorrect="off"`, `spellcheck="false"` e `inputmode="search"` (se
   conserva `enterkeyhint="search"`). El «No encontramos ese lugar.» sigue
   dentro del `aria-live` de `#map-search-results`.
6. **Rectángulo claro tras la fila de controles** — diagnóstico: el artefacto
   de composición de Chromium documentado en el propio CSS («rectángulo sin
   dibujar») pero a nivel de `.map-ctl` entera, no solo de sus píldoras (por
   eso la franja cubría también los huecos y tenía el color de `--bg` de
   `.map-wrap`). Se aplica a `.map-ctl` la misma guarda de una línea
   (`box-shadow: 0 1px 0 rgba(0,0,0,.01)`) dentro del `@media (max-width:
   899px)`, junto a la regla de la fila.
7. **Leyenda tapada por «Capas» en escritorio** — al abrir «Capas» la leyenda
   se repliega a su píldora (`.legend-closed`), extendiendo la regla «una
   cosa abierta a la vez» del `toggle` de `.map-layers`; se vuelve a abrir
   con «+». Además `.layers-body` baja su tope de `100dvh - 160px` a
   `100dvh - 190px` para que el panel nunca llegue a la píldora.

## Verificación

`tests/test_vista_mapa.py` (Python, leyendo archivos) y
`tests/js/buscador-teclado.test.mjs` (guardas de fuente, `node --test`).
`node --check` de los `.js` tocados. La medición en navegador la repite la
revisión del CI.

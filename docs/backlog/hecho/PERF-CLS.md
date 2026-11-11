---
id: PERF-CLS
repo: brasas
rama: perf/cls-hoja
modelo: swe-2-high
riesgo: B
archivos: web/js/app.js, web/css/app.css, tests/test_hoja_movil.py, docs/backlog/hecho/PERF-CLS.md, CHANGELOG.md
e2e: no
intento: 1
ronda_review: 0
---

**Objetivo.** Que la hoja inferior del teléfono deje de animar una propiedad de
composición (`height`) al cambiar de estado: cada cuadro de esa animación contaba
como salto de maquetación y disparaba el CLS al cargar una vista.

**Qué pasaba.** En `@media (max-width: 899px)`, `.panel` declaraba
`height: var(--sheet-h, 46dvh)` con `transition: height .42s`. La hoja ya estaba
pintada con el esqueleto a 46dvh y, al montar la primera vista, `setSheet()`
cambiaba `--sheet-h` y la altura se animaba cuadro a cuadro sin toque del usuario:
cada cuadro era un `layout-shift` de `section#panel.panel`.

**Qué se hizo.** La caja de `.panel` queda fija en `94dvh` (el tope del arrastre)
anclada sobre la tabbar; el estado publica la altura visible en `--sheet-h` como
siempre y la hoja se desliza con `transform: translateY(...)`, que el observador
de `layout-shift` no cuenta. `padding-bottom: calc(94dvh - var(--sheet-h))`
mantiene el contenido al alcance del desplazamiento interno. El arrastre sigue
cuadro a cuadro (`transition: none` con `.dragging`) y la primera aplicación cae
directa: la transición solo existe cuando ya no hay `#view-skel` (esqueleto) ni
arrastre. `setSheet` y el store no cambiaron. En `setupSheet` el alto visible se
mide del borde del panel a la tabbar, porque la caja ya no refleja el estado.

**Medición.** Playwright a 360 × 780 táctil, fast-3g y CPU ×4, carga en frío con
`PerformanceObserver` de `layout-shift` (misma metodología que la tabla de
producción del encargo), sirviendo `main` y esta rama con `servir.sh` en el
puerto 8765.

| Entrada | CLS antes (`main` faead26) | CLS después (esta rama) |
|---|---|---|
| `#/calidad` | 0,234 | 0,001 |
| `#/preparate` | 0,258 | 0,001 |
| `#/mapa` | 0,081 | 0,001 |

Con la misma medida, `#/mi-zona`, `#/riesgo` y `#/casos` quedaron en 0,001
antes y después. El único salto restante (~0,001) es un `::before` de texto,
no la hoja. Verificación funcional (mismo servidor, 360 × 780): caja fija en
94dvh con el borde visible igual a `--sheet-h`; el arrastre responde cuadro a
cuadro y suelta en el nivel correcto; Enter en el asa cicla los tres estados;
el contenido se desplaza hasta el final en `peek`, `half` y `full`; y con
`prefers-reduced-motion` no hay transición.

Referencia de producción (medición del encargo, `main` 9b6f215): `#/calidad`
0,237 · `#/preparate` 0,252 · `#/mapa` 0,079.

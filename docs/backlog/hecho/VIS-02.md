---
id: VIS-02
repo: brasas
rama: fix/vista-fichas
modelo: swe-2-high
riesgo: B
archivos: web/js/views/riesgo.js, web/js/views/incendio.js, web/css/app.css, tests/js/riesgo.test.mjs, tests/js/errores.test.mjs, tests/test_vis02_fichas.py, docs/backlog/hecho/VIS-02.md, CHANGELOG.md
e2e: no
intento: 0
ronda_review: 0
estado_desde: 2026-11-11T00:00:00
nota:
---

# VIS-02 · Fichas de comuna e incidente usables en el teléfono

**Objetivo.** Que la ficha de comuna en `#/riesgo` y la ficha de incidente en
`#/incendio/<id>` se puedan usar en 360–390 px: días del pronóstico tocables,
enlaces de fuente alcanzables, búsqueda que abre con Enter una coincidencia
única, filtro del ranking por nivel de peligro y errores que nombran qué falló.

**Evidencia medida en producción** (Playwright, 360/390 px táctil y 1280 px,
11-nov-2026). `button.day-cell` medía 37 × 77 px a 360 px y 41 × 77 a 390 px
(objetivo ≥ 44 px de ancho tocable); los enlaces de fuente «Ver en CONAF ↗»,
«Método ↗», «Fuente ↗» medían 15 px de alto y «Ver la calidad del aire medida
en SINCA ↗» 17 px; a 390 y 1280 px la ficha seguía «Cargando la comuna…»
2,5 s después de Enter sin reservar el alto; con `/api/risk` en 503 la vista
mostraba solo «No pudimos cargar esto ahora.»; tres enlaces sin nombre
accesible en Riesgo a 390 px; `#r-search` sin `enterkeyhint`,
`autocapitalize`, `autocorrect` ni `spellcheck`; Enter con un parcial de una
sola comuna no la abría; y el ranking no filtraba por nivel.

**Qué se hizo.**

1. **Días tocables (ficha).** En la sección `/* VIS-02: fichas de comuna e
   incidente */` de `web/css/app.css` (inmediatamente antes de la primera
   regla `.day-cell`, fuera del `@media`, así aplica a 360, 390 y 1280 px),
   `.day-strip` pasa a `grid-template-columns: repeat(7, minmax(44px, 1fr))`
   con `overflow-x: auto`, `scroll-snap-type: x proximity` y
   `overscroll-behavior-x: contain` dentro de su propio contenedor — la página
   no gana scroll horizontal — y `.day-cell` lleva `scroll-snap-align: start`;
   cuando las siete celdas no caben, la fila se desliza en vez de aplastar el
   objetivo por debajo de 44 px.
2. **Enlaces de fuente.** Dentro del `@media (max-width: 899px)` ya existente,
   las reglas VIS-02 dan a los enlaces dentro de `.callout`, `.em-official` y
   `.card .tiny` un relleno vertical de 5 px (≥24 px de alto tocable sin
   agrandar la letra), y la clase `a.src-linea` — que lleva el enlace «Ver la
   calidad del aire medida en SINCA ↗», que ocupa su propia línea — sube a
   `min-height: 44px` con `inline-flex`. Los enlaces de `brCallout`,
   `airCallout` y `dmcCallout` se pintan solo si su `href` existe
   (`source?.url ? … : ''`): antes renderizaban `href="undefined"` cuando la
   fuente no llegaba — el origen probable de los «enlaces sin nombre» medidos —
   y ahora se omite el enlace y queda solo el texto.
3. **Esqueleto de la ficha.** Mientras carga, `renderDetail` pinta
   `.ficha-skel`: `min-height: 80dvh` reserva el alto aproximado de la ficha y
   cuatro barras animadas con `skel-pulse` (que la regla global de
   `prefers-reduced-motion` apaga), así el layout no salta al llegar el dato.
4. **Errores que nombran la consulta.** `errorNombrado` reutiliza el marcado
   del bloque compartido (`role="alert"`, `dual()`, «Reintentar» con
   `data-retry`, `phonesHtml()`) pero con titular propio. La vista completa
   dice «No pudimos cargar el peligro de incendio por comuna.» y, si la sesión
   ya cargó un dato, nombra su fecha (`store.get('risk').computed_at`); la
   ficha dice «No pudimos cargar el pronóstico de peligro de <comuna>.» y su
   «Reintentar» repite solo `/api/risk/<code>`. Nunca se pinta un dato de
   respaldo inventado. El detalle además corta a los 15 s (`Promise.race` con
   el temporizador) tratándolo como fallo de la consulta.
5. **Búsqueda.** `#r-search` gana `enterkeyhint="search"`,
   `autocapitalize="off"`, `autocorrect="off"` y `spellcheck="false"`.
   `resolverBusqueda` (pura, sobre `findComuna`) devuelve la comuna cuando el
   texto es exacto o coincide con una sola — Enter/change la abre — y con
   varias coincidencias no elige: el mensaje de «sin resultado» ahora ofrece
   las tres primeras como botones. Sin tildes sigue funcionando («quilpue» →
   Quilpué) porque el orden vive en `findComuna`.
6. **Filtro por nivel.** Select `#r-level` con su `label` junto a región y
   orden («Todos», «Moderado o más», «Alto o más», «Solo extremo»), persistido
   en `storage` como `#r-region` y `#r-sort`. `filtrarPorNivel` (pura, sobre
   `LEVEL_ORDER` y `RISK` — sin umbrales inventados) filtra `#r-rank-list` y
   el resumen `#r-region-resumen`; `textoSinNivel` deja el estado vacío
   explícito: «Ninguna comuna de Valparaíso está hoy en alto o más.»
7. **Ficha de incidente.** `load` distingue el 404 del resto: con 404 pinta
   «Este incidente ya no está activo o no existe.» como encabezado y un
   callout con enlace «Ver el mapa» (`#/mapa`) — sin «Reintentar», porque el
   id caducó —; con error de red el encabezado nombra la consulta («No pudimos
   cargar la ficha del incidente.») y el cuerpo es `errorConSalida`
   compartido, lo que además conserva `errores.js` en el grafo estático de
   `zona.js` y la lista `modulepreload` de `index.html`. `overflow-wrap:
   anywhere` en la sección VIS-02 cubre los nombres largos de CONAF y comuna a
   360 px. Los estados ya venían con nombre (`INCIDENT`: «Señal de calor»,
   «Posible incendio», «Confirmado por CONAF», «Controlado»…), no solo color.

**Pruebas.** `tests/js/riesgo.test.mjs` cubre `filtrarPorNivel` (umbral,
`todos`/desconocido no filtra, nivel desconocido no pasa), `textoSinNivel`
(regiones y umbrales) y `resolverBusqueda` (exacta, única parcial, ambigua sin
autoelección, sin tildes). `tests/test_vis02_fichas.py` lee `riesgo.js` y
guarda los cuatro atributos de `#r-search`. `tests/js/errores.test.mjs` quedó
ajustado al contrato nuevo: `casos.js` sigue con `errorConSalida` y `riesgo.js`
conserva el marcado del bloque con titular propio.

**Fuera de alcance.** La vista completa no puede declarar la fecha de un dato
persistido entre sesiones porque `storage` no guarda `risk`; se nombra el
último dato de la sesión (`store`), que es lo que de verdad se cargó.

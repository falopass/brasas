---
id: VIS-03
repo: brasas
rama: fix/vista-filtros
modelo: swe-2-high
riesgo: B
archivos: web/js/views/mapa.js, web/js/data.js, web/css/app.css, tests/js/data-distancia.test.mjs, docs/backlog/hecho/VIS-03.md, CHANGELOG.md
e2e: no
intento: 0
ronda_review: 0
estado_desde: 2026-11-11T00:00:00
nota:
---

# VIS-03 · Filtro por distancia y errores que no dicen cero

**Objetivo.** Que una persona pueda recortar el mapa a lo que tiene cerca
(«Todo Chile · 10 km · 25 km · 50 km · 100 km» desde su ubicación o su primer
lugar guardado) con puntos, números y listas contando lo mismo, y que una
fuente caída nunca se lea como «0 = no hay fuego».

**Evidencia medida en producción** (Playwright, 360/390 px táctil y 1280 px,
11-nov-2026). No existía filtro por distancia: las listas («Posibles
incendios», «Incendios que informa CONAF», «Dónde hay más») y los números eran
de todo Chile. Con `/api/observations`, `/api/status` e `/api/incidents` en 503
el panel mostraba «puntos de calor 0 · más seguros 0 · el último — sin datos» —
cero no es «no sabemos» — y «Dónde hay más» decía solo «No pudimos cargar esto
ahora.», sin nombrar la fuente. El estado vacío sin focos ya estaba bien y se
conserva.

**Qué se hizo.**

1. **Filtro por distancia.** Chips «Todo Chile · 10 km · 25 km · 50 km · 100 km»
   con el mismo estilo `.chip`/`aria-pressed`: en la píldora «Filtros» del
   teléfono (grupo `#map-dist` con `role="group"` y `aria-label`, ≥44 px por
   `.map-chips .chip`) y junto a los chips de horas en escritorio
   (`.chips-dist`, oculta en celular igual que `.chips-hours`: una vía). El
   texto «desde: tu ubicación» o «desde: <nombre del primer lugar guardado>»
   acompaña a ambos grupos.
2. **Punto de referencia.** La posición se pide solo al tocar un chip de
   distancia (`navigator.geolocation.getCurrentPosition`, 12 s de espera,
   caché de 5 min), nunca al cargar: al montar solo se consulta el estado del
   permiso (`navigator.permissions`, sin gatillar el diálogo). Orden: posición
   si el permiso ya está dado → primer lugar guardado (`places[0]`) → sin
   ninguno, los chips quedan deshabilitados con «Guarda un lugar o permite tu
   ubicación para filtrar por distancia» (mismo texto en toast si la
   resolución falla al tocar).
3. **El radio recorta todo a la vez.** `filtrarPorDistancia` (pura, en
   `data.js`, sobre `haversineKm` ya existente) recorta focos, incendios CONAF
   e incidentes por igual: los puntos del mapa (`pintarFocos` reafirma
   `detections`/`goes-pixels` tras cada repintado de `app.js` vía `onReady`),
   los KPI, las listas, «Dónde hay más» y las líneas lugar↔foco más cercano
   comparten `focosFiltrados()`. Cada fila de lista muestra «a N km». El
   círculo se dibuja en fuente y capas propias (`filtro-radio`, línea
   discontinua `line-dasharray` con el azul `--accent` #3987e5, relleno al
   5 %), la vista encuadra su caja (`fitBbox`) y se repone tras cada
   `style.load`. `#map-summary` suma «Filtro de distancia: N km desde <origen>»
   al resumen accesible y `.filters-dot` se enciende con radio activo.
4. **Se recuerda.** La elección queda en `storage` (`mapa:radioKm`) como las
   horas; al volver se restaura solo con lugar guardado de referencia (la
   posición sigue sin pedirse al cargar). «Todo Chile» guarda 0.
5. **Errores que no dicen cero.** Con `obsError` o `statusError` en el store
   los tres números muestran «—» y un callout nombra la fuente («No pudimos
   cargar los puntos de calor ahora.» / «el estado de las fuentes») con «Lo
   último que llegó es de hace X.» desde `dataAsOf`, o «Reintenta en un
   momento.» si no hay dato previo. «Posibles incendios» y «Incendios que
   informa CONAF» nombran su propia falla (`incidentesError`, `officialError`);
   el bloque «Dónde hay más» conserva `errorConSalida` (teléfonos de
   emergencia donde ya aparecen) alimentado con `statusError || obsError`.
   «Reintentar» corre `reintentarCarga`: las mismas `refreshObservations` +
   `refreshStatus` del botón «Actualizar» (`import('../app.js')`, módulo ya
   evaluado — el mismo camino de `refresco.js`) más `loadOfficial` y
   `loadIncidents` de la vista. El aviso se repinta al llegar el fallo, sin
   esperar otro evento (suscripciones a `obsError`/`statusError`).
6. **Desfases corregidos.** «el último» ahora cuenta los puntos filtrados
   (antes medía el lote completo, incluidos sensores apagados), y `unmount`
   elimina `filtrosEl` — antes quedaba en el DOM y volver a «Mapa» duplicaba
   la píldora «Filtros». Las suscripciones existentes ya mantenían mapa,
   números y listas al día con horas y «Ocultar los dudosos».
7. **Estado vacío con radio.** «No se ve calor a menos de N km de <origen> en
   este período.» + la misma advertencia de nubes/humo de siempre.

**Supuestos.** Con `statusError` pero observaciones cargadas, los números
también muestran «—» (el encargo lo pide así: el error es de la consulta de
puntos o de estado). `refresco.js` no exporta la vuelta de sondeo: se reusa el
mismo `import('./app.js')` que él hace, sin duplicar la lógica. El color del
círculo es `--accent` (#3987e5), el mismo de los enlaces/acentos ya usados en
el mapa.

**Pruebas.** `tests/js/data-distancia.test.mjs` cubre `filtrarPorDistancia`
(dentro/fuera del radio, coordenadas no finitas, sin radio ni centro, entrada
no-arreglo, sin mutación). `node --check` en los `.js` tocados; los tests JS
existentes (`data.test.mjs`, `data-filtro.test.mjs`, `mapa-teclado.test.mjs`,
`buscador-teclado.test.mjs`, `errores.test.mjs`) pasan sin cambios.

**Fuera de alcance.** `errorConSalida` (errores.js) sigue con titular genérico
«No pudimos cargar esto ahora.»: nombrar la consulta ahí pediría tocar un
archivo fuera del alcance — el párrafo que antecede en el panel ya nombra la
fuente.

## Corrección del 11-nov

Tres fallas medidas en producción con el radio ya elegido: el círculo no se
dibujaba, el mapa no se encuadraba en él y el radio guardado no volvía tras
recargar.

- **El círculo sí se ve.** Las capas `filtro-radio-fill` y `filtro-radio-line`
  pasaron a vivir en `map.js` junto al resto de overlays registrados, y la
  vista solo alimenta la fuente `filtro-radio` con `setData`. La versión
  anterior agregaba fuente y capas a mano solo si `isStyleLoaded()` era verdad
  en ese instante; como los `setData` de focos, CONAF e incidentes corrían
  antes en el mismo repintado, el estilo quedaba «cargando» un rato, la
  condición nunca se cumplía y nada reintentaba el dibujo. Y `aplicarRadio`
  pinta la fuente ahora directo — `setData` escribe `overlayData` aunque el
  estilo siga cargando — porque la cola de `onReady` solo se vacía en
  `style.load`: un repintado pedido con el estilo aún cargando quedaba
  encolado para siempre y el círculo restaurado tras recargar no aparecía.
- **El mapa encuadra el círculo.** `encuadrarRadio` pasa a `fitBounds` solo
  los márgenes extra del área libre (barra y hoja en el teléfono, lienzo a la
  derecha del panel en escritorio): `fitBounds` ya suma el `transform.padding`
  — la hoja que `setPadding` reserva — al padding pedido, así que pedirla de
  nuevo la contaba dos veces y el ajuste quedaba imposible o desplazado. Con
  «Todo Chile» el mapa vuelve al encuadre nacional de `initMap`
  (`fly(-71.2, -35.4, 4.6)`).
- **El radio se recuerda sin diálogo.** Al cargar, `decidirRestaurarRadio`
  (función pura) decide: «ubicacion» si `navigator.permissions` informa
  `granted` — la consulta de posición no abre diálogo —, «lugar» si hay un
  primer lugar guardado, o nada: queda «Todo Chile» y el radio sigue guardado
  para el próximo toque. La decisión corre desde `sincronizarRadio` cuando
  resuelve la consulta de permiso y en cada repintado.

**Pruebas.** `tests/js/mapa-radio-restaurar.test.mjs` cubre la decisión pura
(`granted`/`prompt`/`denied` × con y sin lugar guardado, radio inválido y
«Todo Chile»). Verificación en navegador (Playwright sobre la demo sembrada)
a 360, 390 y 1280 px: capas presentes, `map.getBounds()` contiene el círculo
completo y el radio sobrevive la recarga con el permiso dado. El peso del
arranque sigue bajo el tope de 325 KB gzip.

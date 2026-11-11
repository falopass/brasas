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

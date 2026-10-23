---
id: FUEGO-14
repo: brasas
rama: feat/escenario-avance-en-palabras
modelo: swe-2-high
riesgo: B
archivos: web/js/spreadtext.js, web/js/views/incendio.js, tests/js/spreadtext.test.mjs, CHANGELOG.md
e2e: si
intento: 0
ronda_review: 0
estado_desde: 2026-10-20T10:10:17
nota: Reencolado: la corrida falló por rate limit del modelo gratis, no por el ítem.
---

**Objetivo.** Que el bloque «Escenario estimado de avance» de la ficha del incidente explique, en palabras que entienda un vecino de la Región del Maule, qué empuja el fuego (el viento), cuán seco está el pasto fino (el FFMC) y qué NO se sabe (la pendiente), con la etiqueta «escenario estimado, no es una predicción» siempre visible.

**Ítem del backlog.** FUEGO-02 (escenario estimado de propagación, PR #361 ya en `main`) y la prioridad 1 de esta ronda: «la propagación debe explicar viento, pendiente y humedad en términos que un vecino entienda, siempre rotulada como escenario estimado y nunca como predicción».

**Qué ve hoy el usuario y por qué está mal.** En `web/js/views/incendio.js:151-154` el bloque muestra una sola frase —«Con el clima de ahora el fuego podría avanzar unos X km/h hacia el Sur, con viento de Z km/h del Noroeste»— y debajo vuelca en letra chica y gris (`.tiny muted`) el campo `note` más los `assumptions` crudos del backend. El resultado es que la advertencia principal («no es una predicción ni el perímetro del incendio») y la limitación más importante («Terreno plano: BRASA aún no tiene modelo de elevaciones; la pendiente puede acelerar el avance», ver `backend/fwi.py:353-360`) quedan enterradas entre jerga: «ROS estimada 3,2 m/min · ISI efectivo 4,1 · pasto en pie seco (tipo O-1b del FBP canadiense)». Un vecino no puede sacar de ahí qué significa para él ni qué no debe concluir.

**Datos disponibles (no inventes otros).** `GET /api/incidents/{id}` devuelve `spread` desde `backend/routes/public.py:327-370` (`_incident_spread`), construido por `fwi.propagation_scenario` (`backend/fwi.py:304-390`). Campos: `kind`, `ffmc`, `wind_kmh`, `wind_deg`, `slope_deg` (hoy siempre `null`), `aspect_deg`, `effective_wind_kmh`, `isi`, `speed_m_min`, `speed_kmh`, `direction_deg`, `fuel`, `reference`, `assumptions` (lista) y `note`. Cuando falta FFMC o viento el backend devuelve `None` y la ficha no muestra nada: mantén ese comportamiento.

**Qué hacer.**
1. Crear `web/js/spreadtext.js`: módulo puro, sin DOM ni imports de vistas (mismo estilo que `web/js/satelite.js`), que exporte `spreadWords(spread)` y devuelva `{ resumen, porque, tecnico, etiqueta }`:
   - `resumen`: una frase con la velocidad y el rumbo («Podría avanzar unos 1,8 km/h hacia el sureste, empujado por viento de 25 km/h desde el noroeste»). Si `direction_deg` es `null`, dilo («no se sabe hacia dónde») y no escribas «hacia undefined».
   - `porque`: 2 o 3 frases cortas sobre (a) el viento, (b) la sequedad del pasto fino a partir de `ffmc` y (c) la pendiente: «BRASA todavía no tiene modelo de elevación; si el fuego sube una ladera puede ir más rápido. Este escenario supone terreno plano.». Las bandas de FFMC que uses deben quedar documentadas en el encabezado del módulo con su fuente; si no encuentras una fuente en el repo, usa solo dos estados («el pasto fino está seco» / «no está tan seco») y deja el número exacto para la línea técnica.
   - `tecnico`: la jerga actual (ROS, ISI, combustible de referencia, fuente), que se queda en el bloque `.x-tech`.
   - `etiqueta`: siempre «Escenario estimado» y «no es una predicción»; no la omitas en ningún caso.
2. En `web/js/views/incendio.js`, reemplazar el texto vecino del bloque por `spreadWords()` manteniendo `dual()`: la versión corta en palabras y la técnica en `.x-tech`. No cambies el resto de la ficha.

**Pruebas (`tests/js/spreadtext.test.mjs`, nuevo, `node:test`).** Casos: con rumbo y viento; sin `wind_deg`; `ffmc` alto y bajo; `slope_deg` nulo. Asserts: en todos los casos `etiqueta` contiene «escenario estimado» y «no es una predicción»; ningún texto contiene «undefined» ni «null»; `porque` nunca viene vacío; con `wind_deg` nulo el texto dice explícitamente que no se conoce la dirección. No toques `tests/js/index.js` (otro encargo lo está cambiando).

**Criterio de listo (verificable).** `node --test tests/js/spreadtext.test.mjs` en verde; `python dev.py check` termina en «Todo en orden»; en `python dev.py run --demo`, abrir un incidente con escenario muestra el resumen, las dos o tres razones y la etiqueta, y la jerga queda en la línea técnica; `python dev.py e2e` sin fallos.

**Nota de peso (importante).** Hoy `python scripts/local/presupuesto_peso.py` mide **199,8 KB gzip de 200,0**: el margen es de 0,2 KB y ese paso corre dentro de `dev.py check`. No subas el umbral. El margen real lo libera PESO-03 (`perf/preparate-fuera-del-arranque`, en curso). Si tu rama sale de un `main` sin ese merge, entrega el PR igual y anota en el PR la medición exacta: una falla **solo** del presupuesto de peso es previa y tiene dueño, no tuya. Si aun con ese margen no cabe, recorta tus frases y no dupliques literales que ya existen en `web/js/views/*.js`.

**No toques nada más.** Nada de `backend/` (el payload ya trae lo necesario), nada de `web/js/map.js` ni `web/js/views/mapa.js`, y de `CHANGELOG.md` solo la línea del encargo. PR de menos de ~150 líneas.

Verifica con /verificar y entrega con /entregar-pr.


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.

---
id: ALR-28
repo: brasas
rama: feat/avisos-resumen-por-lugar
modelo: swe-2-high
riesgo: B
archivos: web/js/alertas-resumen.js, web/js/views/alertas.js, tests/js/alertas-resumen.test.mjs, CHANGELOG.md
e2e: si
intento: 0
ronda_review: 0
estado_desde: 2026-10-20T10:10:17
nota: Reencolado: la corrida falló por rate limit del modelo gratis, no por el ítem.
---

**Objetivo.** Que el historial de avisos muestre, arriba de la lista, un resumen **por lugar**: cuántos avisos te llegaron, cuántos fueron urgentes, cuántos te sirvieron y cuántos resultaron ser quemas; y que cuando la consulta falle el error ofrezca «Reintentar» en vez de dejar la pantalla muerta.

**Ítem del backlog.** ALR-05 («¿Te sirvió este aviso?», ya con botones y `feedback` guardado) y ALR-09 («calibrar los avisos durante el verano: avisos por lugar, “no me sirvió” y quemas confundidas»). Prioridad 4 de esta ronda: alertas útiles, sin fatiga.

**Qué ve hoy el usuario y por qué está mal.** `web/js/views/alertas.js:68-110` arma la lista agrupada por día y calcula solo dos agregados: `urgent` (total) y `places` (nombres únicos, en las líneas 75-76), que usa para poblar un `<select>` de filtro. No hay ninguna cifra por lugar: para saber si un lugar te está llenando de avisos —o si todos los avisos de un lugar los marcaste como «era una quema»— hay que recorrer el historial completo a ojo. Eso es justo lo que produce fatiga y lo que ALR-09 necesita medir. Además, el estado de error de la línea 70 («No se pudo leer el historial.») no ofrece salida: UX-16 pide siempre un siguiente paso y un botón para reintentar (patrón ya usado en `web/js/views/riesgo.js:281`).

**Qué hacer.**
1. Crear `web/js/alertas-resumen.js`: módulo puro, sin DOM, que exporte `summaryByPlace(alerts)` y devuelva una lista `[{ place, total, urgente, aviso, kinds: { oficial, reporte, diario, prueba }, feedback: { sirvio, no_sirvio, quema } }]` ordenada por `total` descendente y, en empate, por nombre con `localeCompare('es')`. Reglas: los avisos sin `place` se agrupan bajo `place: null` y la vista los rotula «Sin lugar»; un `kind` o `feedback` desconocido no se inventa (no se cuenta en ninguna categoría, pero sí en `total`); una lista vacía devuelve `[]` sin lanzar.
2. En `web/js/views/alertas.js`, renderizar el bloque «Tus avisos por lugar» entre el resumen y la lista, con una fila por lugar: nombre, total, cuántos urgentes, «N te sirvieron» y «M eran quemas» (omite las frases cuyo contador sea 0). Cada fila debe poder aplicar el filtro por ese lugar (reutiliza el `state.place` y el `<select>` existentes, sin duplicar estado).
3. Añadir el botón «Reintentar» al bloque de error que vuelva a llamar la carga del historial (misma función que usa el montaje), sin perder el filtro elegido.

**Pruebas (`tests/js/alertas-resumen.test.mjs`, nuevo, `node:test`).** Casos: lista vacía; tres avisos de dos lugares con niveles distintos; un aviso sin lugar; `kind` desconocido; feedback mixto. Asserts: el orden por total es estable y determinista; `total` siempre es la suma de todos los avisos del lugar, incluidos los de `kind` desconocido; ningún contador queda en `undefined`; `summaryByPlace(null)` no lanza. No toques `tests/js/index.js` (otro encargo lo está cambiando).

**Criterio de listo (verificable).** `node --test tests/js/alertas-resumen.test.mjs` en verde; `python dev.py check` en «Todo en orden»; en `python dev.py run --demo`, el historial con avisos de ejemplo muestra el bloque por lugar y al forzar un error (por ejemplo apagando el servidor) aparece «Reintentar» y funciona al volver; `python dev.py e2e` sin fallos.

**Nota de peso (importante).** Hoy `python scripts/local/presupuesto_peso.py` mide **199,8 KB gzip de 200,0**: el margen es de 0,2 KB y ese paso corre dentro de `dev.py check`. No subas el umbral. El margen real lo libera PESO-03 (`perf/preparate-fuera-del-arranque`, en curso). Si tu rama sale de un `main` sin ese merge, entrega el PR igual y anota en el PR la medición exacta: una falla **solo** del presupuesto de peso es previa y tiene dueño, no tuya. Si aun con ese margen no cabe, recorta tus frases y no dupliques literales que ya existen en `web/js/views/*.js`.

**No toques nada más.** Nada de `backend/routes/personal.py` ni del contrato de `/api/alerts`; no toques `web/js/views/zona.js` (tiene otro encargo encima); de `CHANGELOG.md`, solo tu línea.

Verifica con /verificar y entrega con /entregar-pr.


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.

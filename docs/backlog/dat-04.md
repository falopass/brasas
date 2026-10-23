---
id: DAT-04
repo: brasas
rama: feat/datos-abiertos-explicados
modelo: swe-2-high
riesgo: B
archivos: web/datos.html, web/js/datos.js, tests/test_datos_abiertos.py, CHANGELOG.md
e2e: si
intento: 0
ronda_review: 0
estado_desde: 2026-10-20T10:10:17
nota: Reencolado: la corrida falló por rate limit del modelo gratis, no por el ítem.
---

# DAT-04 · Datos abiertos explicados en palabras simples

## Objetivo
Que quien llega a `/web/datos.html` entienda, sin saber GIS, qué es cada conjunto, cada cuánto cambia y qué **no** se puede concluir de él; hoy solo ve una tabla de parámetros, geometrías y nombres de campos técnicos.

## Ítem del backlog
Foco del dueño (4): «datos abiertos bien explicados». El conjunto existe y es correcto (PR del índice autodescriptivo), pero está escrito para alguien que ya sabe qué es un GeoJSON.

## Qué pasa hoy (verificado en `main` 3ceae01)
- `web/datos.html:78-84`: la tabla tiene cinco columnas —Conjunto, Parámetros, Geometría, Propiedades, Fuente— y nada más; el `description` de la página promete incidentes, detecciones, riesgo, rayos, humo y tiempos de respuesta, pero no los explica.
- `web/js/datos.js:61-78`: `fila(d)` pinta `d.id`, `d.url`, `d.params`, `d.geometry`, `d.properties`, `d.source`. No hay ninguna frase de producto: la única explicación vive en `/api/opendata` (`backend/routes/opendata.py:86-170`), en jerga.
- `web/datos.html:85-97`: el bloque `#directo` («Acceso directo a cada conjunto») **duplica** exactamente las ocho URL que ya están en la tabla.
- Nadie dice hoy que un punto de calor no es un incendio (sí está en «Regla de oro», pero no por conjunto), ni que las cicatrices no son el área quemada oficial, ni que el riesgo es una aproximación de BRASA y no el Botón Rojo.

## Solución pedida
1. En `web/js/datos.js`, un mapa `PLAIN` con los ocho `id` del índice (`incidents`, `observations`, `risk`, `lightning`, `smoke`, `scars`, `response`, `boton-rojo`): para cada uno, tres frases cortas —`que` («qué es», en castellano de calle), `cadencia` («cada cuánto cambia», honesto: p. ej. «con cada barrido del satélite, cada ~10 min»; «con el reporte de CONAF, que se actualiza durante el día») y `ojo` («qué no se puede concluir»). Sin prometer periodicidad que el código no cumpla: míralo en `backend/services.py` antes de escribirla.
2. Pintar arriba de la tabla una lista de ocho tarjetas (o `<details>`) con esas tres frases + el nombre del conjunto y el enlace al archivo. La tabla técnica se queda como está (es útil para quien programa).
3. Para no engordar: **quitar** el bloque `#directo` con las ocho URL duplicadas de `datos.html:100-110` y dejar un solo enlace al índice `/api/opendata`. El peso total del frontend está en 199.9 KB de 200 y no hay margen: el cambio debe quedar en peso neutro o negativo (compruébalo con `python scripts/local/presupuesto_peso.py`).
4. Si el índice trae un `id` sin entrada en `PLAIN`, no rompas la página: cae al `source` del índice y muestra solo lo técnico. Si falla `/api/opendata`, se mantienen las tarjetas con el texto local y el enlace directo (la página ya tiene `Reintentar`).
5. Añadir `<caption class="sr-only">` y `scope="col"` a la tabla de `datos.html` (hoy no tiene ni lo uno ni lo otro).

## Criterio de listo (verificable)
- `tests/test_datos_abiertos.py` (nuevo, stdlib): lee con `re` los `"id"` del índice en `backend/routes/opendata.py` y comprueba que **cada uno** tiene entrada en `PLAIN` de `web/js/datos.js` con `que`, `cadencia` y `ojo` no vacíos; y que `datos.html` conserva `<table>` con `<caption>` y `scope="col"`.
- `node --check web/js/datos.js` limpio y `python dev.py check` en verde (si el único rojo es el presupuesto de arranque de `main`, anótalo en el PR: lo arregla PERF-05).
- `python scripts/local/presupuesto_peso.py` sigue dentro del presupuesto (no debe subir respecto de `main`).
- En e2e: abrir `/web/datos.html` y ver las ocho tarjetas, cada una con «Qué es», «Cada cuánto» y «Ojo»; sin JS, los enlaces directos siguen funcionando.

No toques nada más: ni `backend/routes/opendata.py` (lo está tocando DET-21), ni `web/sw.js`, ni `web/css/app.css`, ni el resto de las páginas.

Verifica con /verificar y entrega con /entregar-pr. No mergees por iniciativa propia.


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.

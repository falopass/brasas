---
id: DET-23
repo: brasas
rama: feat/rayo-que-origino-el-incendio
modelo: swe-2-high
riesgo: C
archivos: backend/db.py, backend/services.py, backend/incidents.py, backend/routes/opendata.py, web/js/views/incendio.js, docs/FUENTES.md
e2e: si
intento: 0
ronda_review: 0
---

## Motivo de que sea decisión de Diego

Requiere **guardar** los rayos de GLM, y hoy no se guardan: `/api/opendata/lightning.geojson` los pide en vivo a NOAA (`backend/routes/opendata.py:337-351`) y no existe tabla en `backend/db.py`. Persistir una fuente nueva (tabla, ingestión por ciclo, retención y respaldo R2) es cambio de datos, y el backlog exige revisión del dueño antes de tocar migraciones y fuentes oficiales.

## Qué quedaría

`DET-03` (P2) pide «marca en el incidente si hubo un rayo a ≤ 5 km antes de la primera detección». Lo demás de DET-03 ya está: `backend/providers/glm.py` y la capa de rayos de la última hora en el mapa (PR #197).

Lo que falta es lo que hace que un vecino del sur entienda por qué apareció un fuego sin que nadie lo viera: si el satélite de rayos registró una descarga justo antes, en el mismo lugar, la ficha puede decir «Posible origen: rayo» —siempre como **posible**, nunca como causa—. En el sur y la Patagonia las igniciones por rayo son frecuentes y un rayo sobre pasto seco es alerta temprana.

## Diseño propuesto (para aprobar o corregir)

1. Tabla `lightning` con (`id` único del flash, `observed_at`, `lat`, `lon`, `energy_j`, `source`), retención 48 h y purga en el mismo ciclo de ingesta. Sin datos personales.
2. Ingestión: GLM ya se consulta por la capa; se guarda el mismo lote una vez por ciclo con `INSERT OR IGNORE` (clave: `id`).
3. `backend/incidents.py`: al crear/fusionar, contar flashes a ≤ 5 km en las 2 h previas a `first_seen_at` y guardar `lightning_near_start` (entero) y `lightning_last_at`. Sin llamada externa en el camino de lectura.
4. `web/js/views/incendio.js`: una línea en la ficha solo si `lightning_near_start > 0`: «Un satélite de rayos registró N descargas a menos de 5 km en las dos horas previas. Posible origen: rayo.» Y su nota técnica con la fuente.
5. `docs/FUENTES.md`: GLM con su licencia (dominio público) y la ventana de retención real.
6. Pruebas: `tests/test_lightning_store.py` (ingesta idempotente, purga a 48 h) y `tests/test_incident_lightning.py` (marca con 1 flash a 4 km, no marca a 6 km ni con un flash 3 h antes). E2E: la ficha del incidente sembrado muestra la línea.

## Por qué NO se lanza solo

- Migración de base: `backend/db.py` y el respaldo R2 cambian de tamaño y de forma.
- Es una fuente oficial nueva en el camino de ingesta: si GLM falla, no puede tumbar el ciclo.
- El texto «posible origen: rayo» roza lo científico: conviene que Diego lo lea antes de publicarlo.

Si Diego prefiere una versión sin persistencia (calcular la marca solo al abrir la ficha, con una llamada en vivo), es más barata pero más frágil: GLM entrega ~20 s de datos por consulta y no sirve para ventanas de horas. Recomiendo la tabla.


Aprobado por Hermes (20-10): Diego delegó la decisión. Pasa a cola.


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.

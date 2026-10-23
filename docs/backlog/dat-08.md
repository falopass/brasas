---
id: DAT-08
repo: brasas
rama: feat/catalogo-datos-abiertos
modelo: swe-2-high
riesgo: B
archivos: backend/routes/opendata.py, tests/test_opendata_catalogo.py, docs/API.md, CHANGELOG.md
e2e: no
intento: 0
ronda_review: 0
estado_desde: 2026-10-20T10:10:17
nota: Reencolado: la corrida falló por rate limit del modelo gratis, no por el ítem.
---

# DAT-08 · Catálogo legible por máquina de las capas de datos abiertos

## Objetivo

Publicar `GET /api/opendata/catalog` con todas las capas abiertas, sus campos, fuente, licencia, cadencia y cobertura, para que un municipio, un periodista o un tesista sepa qué hay sin leer el código, y para que agregar o renombrar una capa no deje el índice mintiendo.

## Ítem y evidencia

Prioridad 4 («datos abiertos bien explicados»). `backend/routes/opendata.py` ya publica nueve capas (`:195 /incidents.geojson`, `:245 /observations.geojson`, `:293 /risk.geojson`, `:337 /lightning.geojson`, `:385 /smoke.geojson`, `:423 /boton-rojo.json`, `:492 /scars.geojson`, `:523 /response.json`, más el índice en `:85`), pero **no hay catálogo**: la única explicación está en prosa en `docs/API.md` y en `web/datos.html` (DAT-04, en curso). Cuando alguien agrega una capa, nada lo obliga a documentarla; y quien consume los datos no tiene forma de saber la licencia ni la fuente de cada una sin abrir el código. Es exactamente el hueco de «datos abiertos explicados» que no depende de una vista.

## Qué hacer

1. En `backend/routes/opendata.py`, define una constante `DATASETS` con una entrada por capa: `id`, `title`, `path`, `format` (`geojson`/`json`), `source`, `source_url`, `license`, `cadence` (`cada 10 min`, `diaria`, …), `fields` (lista de nombres) y `description` en una frase.
2. Agrega `@router.get("/catalog")` que devuelva `{"updated_at": ..., "datasets": DATASETS}`. La cobertura por comunas se calcula **una vez** y se cachea 10 minutos (no consultes la base en cada request).
3. Agrega `tests/test_opendata_catalogo.py`: con `TestClient`, recorre cada `path` del catálogo y exige 200; exige `source`, `license` y `fields` no vacíos en todas las entradas; y un caso que falle si se inyecta un dataset sin `license` (guarda contra la desincronización).
4. Documenta el endpoint y el contrato en `docs/API.md`.

## Criterio de listo

`python dev.py test -k opendata` en verde; el catálogo lista las **9** capas existentes; ninguna respuesta de las capas actuales cambia; `ruff check backend tests` limpio.

Verifica con `/verificar` y entrega con `/entregar-pr`.


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.

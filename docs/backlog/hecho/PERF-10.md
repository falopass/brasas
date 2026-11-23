---
id: PERF-10
repo: brasas
rama: perf/cliente-mapa-zona-incendio
modelo: agente-alto
riesgo: B
archivos: web/js/map.js, web/js/views/mapa.js, web/js/views/incendio.js, web/js/views/zona.js, backend/routes/public.py, tests/
e2e: si
---

# PERF-10 · Optimizar descargas y repintados en `map.js`, `mapa.js`, `incendio.js` y `zona.js`

## Objetivo

Corregir los cuellos de botella de rendimiento identificados en el cliente durante la auditoría (`CONSOLIDADO.md` y `mapa.md` §5.1): evitar descargas innecesarias de `incidents.geojson` y `comunas.geojson`, consolidar las peticiones de «Mi zona», evitar reconstrucciones destructivas de estilo y DOM, y condicionar mediciones de depuración a un flag explícito.

## Contexto

- `web/js/views/incendio.js:481` descarga todo `incidents.geojson?hours=336` (14 días) solo para leer 3 campos de rayos de un incidente; conviene exponer esos campos en `/api/incidents/{id}` o filtrarlos sin bajar el GeoJSON completo.
- `web/js/views/zona.js:840-873` dispara hasta ~70 peticiones y repinta decenas de veces al cargar «Mi zona».
- `web/js/map.js:559` descarga `comunas.geojson` (1,9 MB) al superar zoom 6 aunque las tres coropletas (`risk`, `rain`, `senapred`) estén apagadas y no haya comuna seleccionada.
- `web/js/map.js:590-599` usa `setStyle(..., { diff: false })` al cambiar el mapa base o tema, destruyendo las 25 fuentes GeoJSON y re-descargando `comunas.geojson`.
- `web/js/map.js:623-626` ejecuta `map.queryRenderedFeatures` en cada evento `idle` tras `refreshDetections()` solo para `console.debug`.
- `web/js/views/mapa.js:1071-1196` reescribe todo `container.innerHTML` en cada `render()`, destruyendo `#explore`, `#map-search`, foco activo y listeners.

## Archivos

- `web/js/views/incendio.js` y `backend/routes/public.py` (evitar bajar `incidents.geojson` entero para datos de rayos)
- `web/js/views/zona.js` (agrupar carga de datos y consolidar repintados)
- `web/js/map.js` (`ensureComunas()` solo con coropleta/comuna activa, cambio de capas base sin destruir fuentes, debug `idle` detrás de `?debug=1` / `localStorage`)
- `web/js/views/mapa.js` (actualización incremental por bloques preservando `#explore` y `#map-search`)
- `tests/`

## Criterio de listo

- Hacer zoom >= 6 en el mapa sin coropletas activas no descarga `comunas.geojson`.
- Abrir una ficha en `#/incendio/...` no descarga `incidents.geojson?hours=336`.
- Cambiar de mapa base (`Mapa` / `Satélite` / `Topográfico`) no reinicia ni re-descarga `comunas.geojson`, y `render()` de `mapa.js` conserva el foco en `#map-search` al recibir datos nuevos.
- «Mi zona» reduce drásticamente el número de peticiones y repintados por carga sin pérdida funcional.
- CI en verde (`pytest`, revisión JS y `e2e`).

## Fuente y licencia

- **Nombre:** Auditoría técnica interna de rendimiento (`CONSOLIDADO.md` §1 y `mapa.md` §5.1).
- **Enlace:** `web/js/map.js`, `web/js/views/mapa.js`, `web/js/views/incendio.js` y `web/js/views/zona.js` en el repositorio.
- **Licencia:** N/A (código propio del proyecto).

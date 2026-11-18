---
id: MAPA-168
repo: brasas
rama: feat/nasa-gibs-capas-satelite
modelo: agente-alto
riesgo: B
archivos: web/js/map.js, web/js/capas.js, web/js/views/mapa.js, web/js/views/casos.js, web/data/licencias.json, docs/FUENTES.md, tests/
e2e: si
---

# MAPA-168 · NASA GIBS WMTS: GOES GeoColor cada 10 min, VIIRS color real diario y aerosol (AOD)

## Objetivo

Agregar capas raster opcionales desde NASA GIBS WMTS directamente en MapLibre (`GOES-East_ABI_GeoColor` subdiaria cada ~10 min, `VIIRS_NOAA20_CorrectedReflectance_TrueColor` diaria y `MODIS_Terra_Aerosol` para AOD), superando en uso operativo la antigüedad del mosaico estático EOxCloudless 2016 —que se mantiene como base satelital CC BY 4.0— sin sacar al usuario a enlaces externos ni sumar dependencias JS.

## Contexto

- Hoy el fondo satelital es EOxCloudless 2016 (elegido en `NEG-05` porque los vintages recientes de EOX son CC BY-NC-SA 4.0) y `web/js/satelite.js` solo construye enlaces externos hacia NASA Worldview / SLIDER.
- NASA GIBS sirve teselas WMTS/XYZ gratuitas, sin clave y en `EPSG:3857` para ver nubosidad, columnas de humo diurnas/nocturnas (GeoColor) y cicatrices frescas tanto en el mapa en vivo (`mapa.js`, con selector «Hoy / Ayer») como en `casos.js` (sincronizado con la fecha del caso).
- Si se cierra la CSP en `SEC-15`, incluir `https://gibs.earthdata.nasa.gov` en `img-src`.

## Archivos

- `web/js/map.js` (fuentes raster GIBS `GoogleMapsCompatible_Level*` y control de opacidad)
- `web/js/capas.js` (registro de capas en `CAPAS` y URL `?capas=`)
- `web/js/views/mapa.js` (interruptores en grupo Contexto, selector «Hoy / Ayer», leyenda y atribución NASA EOSDIS)
- `web/js/views/casos.js` (soporte opcional de escena del día del caso)
- `web/data/licencias.json`, `docs/FUENTES.md` y `tests/`

## Criterio de listo

- Desde el panel de Capas del mapa se pueden encender GOES GeoColor y VIIRS color real diario con opacidad ajustable y atribución visible a NASA EOSDIS GIBS.
- En `casos.js` la capa GIBS puede mostrar la fecha histórica del caso cuando haya cobertura.
- EOxCloudless 2016 permanece intacto como fondo satelital base CC BY 4.0 (para no depender de una capa fechada por día sin cobertura en todas las escalas).
- CI en verde (`pytest`, revisión JS y `e2e`).

## Fuente y licencia

- **Nombre:** NASA Global Imagery Browse Services (GIBS / EOSDIS).
- **Enlace:** `https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/` (<https://nasa-gibs.github.io/gibs-api-docs/>).
- **Licencia:** Dominio público / datos abiertos NASA EOSDIS, con atribución requerida («Imagery provided by NASA's Global Imagery Browse Services (GIBS), part of NASA EOSDIS», <https://www.earthdata.nasa.gov/engage/open-data-services-and-software/data-and-information-policy>).

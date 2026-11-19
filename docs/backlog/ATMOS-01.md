---
id: ATMOS-01
repo: brasas
rama: feat/rutas-atmosfericas-independientes-y-cdse
modelo: agente-alto
riesgo: B
archivos: docs/investigacion/, backend/providers/, deploy/cloudflare/src/index.ts, web/js/views/incendio.js, web/js/views/casos.js, docs/FUENTES.md, tests/
e2e: no
---

# ATMOS-01 · Rutas independientes de Open-Meteo (ECMWF Open Data, GEFS-Aerosols, CAMS ADS/GFAS, GEOS-CF) y Sentinel Hub SWIR bajo proxy

## Objetivo

Preparar las integraciones por lotes (batch/R2) que eliminan la dependencia única y la restricción no comercial de Open-Meteo ante un eventual crecimiento de tráfico o cambio de figura legal, además de evaluar imágenes Sentinel-2 True Color / SWIR bajo proxy para detalle de incidentes y casos (`incendio.js` / `casos.js`).

## Contexto

- Open-Meteo limita su uso gratuito a `<= 10.000 llamadas/día` y prohíbe uso comercial o con ingresos sin licencia paga (`atmosfera.md` §4.A.1).
- Las alternativas abiertas y sin límite comercial verificadas en `atmosfera.md` (§4.A.2, §4.A.4–7) requieren procesamiento batch fuera de la petición HTTP del usuario:
  1. **ECMWF Open Data** (`data.ecmwf.int/forecasts/`, `ecmwf-opendata`): GRIB2 IFS/AIFS 0,1°–0,25°, **CC BY 4.0** (permite uso comercial y redistribución).
  2. **NOAA GEFS-Aerosols** (`noaa-gefs-pds` S3): PM2,5, carbono orgánico/negro y AOD a 0,25° a 5 días cada 3 h, dominio público NOAA.
  3. **Copernicus CAMS ADS & GFAS** (`ads.atmosphere.copernicus.eu/api`): flujo de emisiones de fuego y altura de inyección de pluma a 0,1° (`GFAS`), **CC BY 4.0** con clave gratuita.
  4. **NASA GEOS-CF / GEOS-FP** (`opendap.nccs.nasa.gov`): pronóstico horario de composición química/CO/PM2,5 a 0,25°, **CC0** / dominio público NASA.
- En el plano visual de alta resolución (`mapa.md` §4.B.7), **Copernicus Data Space / Sentinel Hub** ofrece Sentinel-2 10–20 m True Color y **SWIR** (atraviesa el humo denso para ver frente activo), pero su plan gratuito tiene **50.000 req/mes** y exige ocultar el `INSTANCE_ID` detrás de un proxy Worker + caché R2 limitado únicamente a vistas de detalle (`incendio.js` / `casos.js`), nunca en el paneo nacional.

## Archivos

- `docs/investigacion/` (diseño batch de recorte GRIB2/NetCDF hacia R2 y presupuesto de cuotas CDSE)
- `backend/providers/` y `scripts/` (prototipo o pipeline batch seleccionable según prioridad: ECMWF / GEFS-Aerosols / CAMS GFAS / GEOS-CF)
- `deploy/cloudflare/src/index.ts` (proxy cacheado en R2 para Sentinel-2 SWIR en fichas de incidente/casos si se activa `CDSE_INSTANCE_ID`)
- `web/js/views/incendio.js`, `web/js/views/casos.js`, `docs/FUENTES.md` y `tests/`

## Criterio de listo

- Ningún `INSTANCE_ID` ni clave de ADS/CDSE se expone al navegador o al repositorio.
- Quedan definidos y probados con fixtures los adaptadores/pipelines batch elegidos, degradando sin error si faltan credenciales o archivos en R2.
- Las fuentes integradas quedan anotadas en `docs/FUENTES.md` con su licencia exacta verificada.
- CI en verde (`pytest`).

## Fuente y licencia

- **Nombre:** ECMWF Open Data, NOAA GEFS-Aerosols (AWS S3), Copernicus CAMS ADS/GFAS, NASA GEOS-CF/FP (NCCS OPeNDAP) y Copernicus Data Space Ecosystem (Sentinel Hub WMS/WMTS).
- **Enlace:** `https://data.ecmwf.int/forecasts/` · `https://noaa-gefs-pds.s3.amazonaws.com/` · `https://ads.atmosphere.copernicus.eu/api` · `https://opendap.nccs.nasa.gov/` · `https://sh.dataspace.copernicus.eu/`.
- **Licencia:** **CC BY 4.0** para ECMWF Open Data y Copernicus CAMS ADS/GFAS; dominio público para NOAA GEFS-Aerosols y NASA GEOS-CF/FP; para Copernicus Data Space / Sentinel Hub, **licencia por confirmar** en los términos legales de uso en <https://documentation.dataspace.copernicus.eu/> (cuota gratuita 50.000 req/mes).

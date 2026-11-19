---
id: MAPA-187
repo: brasas
rama: feat/viento-025-bilineal-rafagas
modelo: agente-alto
riesgo: B
archivos: backend/windgrid.py, backend/services.py, backend/routes/public.py, web/js/viento.js, web/js/views/mapa.js, docs/FUENTES.md, tests/
e2e: si
---

# MAPA-187 · Grilla de viento de 0,25° con ráfagas, selector horario e interpolación bilineal `O(1)`

## Objetivo

Mejorar la capa de viento animado pasando de `STEP_DEG = 1.0` (~111 km, un único instante cada 6 h) en `backend/windgrid.py` a una grilla de **0,25° (~25 km)** con ráfagas (`GUST:surface` / `wind_gusts_10m`) y pasos horarios (`+0/+3/+6/+12 h`) desde NOAA GFS (`noaa-gfs-bdp-pds` en AWS, sin gasto de cuota Open-Meteo) o franja centro-sur de Open-Meteo, y reemplazar en `web/js/viento.js` la búsqueda lineal `O(N)` por indexación directa `O(1)` con interpolación bilineal y color por intensidad.

## Contexto

- Hoy `backend/windgrid.py:20` usa `STEP_DEG = 1.0` (~380 puntos para todo Chile, lo que promedia costa, valle y cordillera en un solo vector) y `web/js/viento.js:37-44` recorre los 380 puntos para cada una de las 350 partículas en cada frame (~133.000 iteraciones/frame). Si la grilla sube a 0,25° (~6.000 puntos), una búsqueda lineal trabaría móviles de gama media.
- Como la grilla es regular `(lat0, lon0, step)`, el muestreo en `viento.js` puede indexar en `O(1)` con `Math.floor((lat - lat0)/step)` e interpolar bilinealmente entre las 4 celdas vecinas.
- La lectura de `noaa-gfs-bdp-pds` por rango de bytes / `.idx` en el backend elimina la presión sobre Open-Meteo; si se opta por Open-Meteo como paso intermedio, restringir a regiones IV–X tras `RISK-26` (FWI incremental).

## Archivos

- `backend/windgrid.py` (resolución 0,25°, ráfagas y pasos horarios +0/+3/+6/+12 h)
- `backend/services.py` y `backend/routes/public.py` (formato compatible de `/api/wind/grid` con metadatos de grilla regular)
- `web/js/viento.js` (indexación `O(1)`, interpolación bilineal y color por velocidad en km/h)
- `web/js/views/mapa.js` (selector horario rápido +0/+3/+6/+12 h y leyenda con rangos de velocidad)
- `docs/FUENTES.md` y `tests/`

## Criterio de listo

- `/api/wind/grid` entrega grilla regular a 0,25° (o franja activa) con pasos horarios y ráfagas sin romper clientes previos.
- `viento.js` realiza muestreo `O(1)` con interpolación bilineal sin degradación de FPS en `1280` ni `320 px`.
- La fuente activa (NOAA GFS o Open-Meteo) queda reflejada con enlace y licencia en `docs/FUENTES.md` y en la leyenda.
- CI en verde (`pytest`, revisión JS y `e2e`).

## Fuente y licencia

- **Nombre:** NOAA/NCEP Global Forecast System (GFS) 0,25° en AWS Open Data (alternativa/complemento: Open-Meteo ECMWF/GFS).
- **Enlace:** `https://noaa-gfs-bdp-pds.s3.amazonaws.com/` (<https://registry.opendata.aws/noaa-gfs-bdp-pds/>).
- **Licencia:** Dominio público NOAA (sin clave, gratis); si se usa Open-Meteo como origen, **CC BY 4.0** solo no comercial (<https://open-meteo.com/en/terms>).

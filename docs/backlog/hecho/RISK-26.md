---
id: RISK-26
repo: brasas
rama: perf/fwi-incremental-y-obs-hour
modelo: agente-alto
riesgo: B
archivos: backend/providers/weather.py, backend/fwi.py, backend/services.py, backend/db.py, docs/FUENTES.md, tests/
e2e: no
---

# RISK-26 · FWI diario incremental y corrección de `obs_hour` por horario de verano/invierno

## Objetivo

Cambiar `compute_fwi` / `fwi_inputs` en `backend/providers/weather.py` y `backend/services.py` para persistir y reutilizar el estado diario anterior `(ffmc, dmc, dc)` de cada comuna en `fwi_daily` y consultar únicamente una ventana corta (7–14 días) en vez de descargar meses de archivo histórico desde el 1 de junio en cada corrida, además de corregir el desfase de `obs_hour` entre horario de invierno y verano en Chile continental.

## Contexto

- Hoy `weather.py` solicita hasta 12 meses de Open-Meteo Archive × 345 comunas por corrida diaria para recalcular el FWI desde cero, consumiendo gran parte de la cuota gratuita de 10.000 llamadas/día y bloqueando el margen para variables adicionales (`RISK-24`) o grilla fina.
- En `docs/research/02-30-30-30-y-fwi.md#L76` y `atmosfera.md` §5.1 se documentó además el desfase entre `obs_hour` estándar del método canadiense FWI (12:00 hora solar / local estándar) y la hora local chilena con cambio de huso (`America/Santiago`).
- Mantener la recarga histórica completa únicamente como arranque inicial (`cold start`) cuando `fwi_daily` no tenga estado previo para la comuna o haya un hueco superior a la ventana corta.

## Archivos

- `backend/providers/weather.py` (ventana incremental de 7–14 días cuando exista estado previo en `fwi_daily`)
- `backend/fwi.py` (inicialización desde `(ffmc, dmc, dc)` previo y manejo correcto de `obs_hour` con `America/Santiago`)
- `backend/services.py` y `backend/db.py` (lectura y persistencia del estado previo)
- `tests/` (equivalencia numérica entre corrida completa e incremental y prueba de cambio de hora DST)

## Criterio de listo

- Una corrida diaria con `fwi_daily` poblada solicita <= 14 días a Open-Meteo Archive y produce los mismos valores `(ffmc, dmc, dc, isi, bui, fwi)` que el recálculo desde junio dentro de tolerancia de punto flotante.
- Ante una tabla vacía o hueco >14 días, el sistema recurre automáticamente al arranque largo desde el inicio de temporada.
- `obs_hour` selecciona correctamente el mediodía solar/estándar en invierno y verano en Chile.
- CI en verde (`pytest`).

## Fuente y licencia

- **Nombre:** Open-Meteo Archive API (ERA5) y documentación interna `02-30-30-30-y-fwi.md` / `atmosfera.md` §5.1.
- **Enlace:** `https://archive-api.open-meteo.com/v1/archive` (<https://open-meteo.com/en/docs/historical-weather-api>).
- **Licencia:** **CC BY 4.0** (<https://open-meteo.com/en/terms>), gratuito sin clave solo para uso no comercial (<= 10.000 llamadas/día).

---
id: RISK-24
repo: brasas
rama: feat/open-meteo-variables-haines
modelo: agente-alto
riesgo: B
archivos: backend/providers/weather.py, backend/risk.py, backend/routes/comuna.py, backend/routes/public.py, web/js/views/incendio.js, docs/FUENTES.md, tests/
e2e: no
---

# RISK-24 · Open-Meteo: más variables (VPD, humedad de suelo, CAPE, 850/700 hPa), `models=` e Índice de Haines

## Objetivo

Aprovechar la API de Open-Meteo ya integrada fijando explícitamente el modelo meteorológico (`models=ecmwf_ifs025`, con opción de contraste/respaldo `gfs_seamless` / `icon_seamless`) e incorporando variables de estrés atmosférico y del combustible que hoy no se piden (`vapour_pressure_deficit`, `soil_moisture_0_to_1cm`, `soil_moisture_0_to_7cm`, `cape` y niveles `temperature_850hPa`, `temperature_700hPa`, `relative_humidity_850hPa`, más `500hPa`/`700hPa` en cordillera) para calcular el **Índice de Haines** (escala 2–6) de inestabilidad vertical en la ficha de comuna/incidente.

## Contexto

- Hoy `backend/providers/weather.py` consulta `/v1/forecast` con `best_match` implícito y solo pide variables de superficie (temperatura, humedad relativa, viento y ráfagas).
- El 30-30-30 y el FWI describen la superficie, pero no detectan atmósfera inestable y seca en altura (columnas convectivas / pirocúmulos) ni la desecación directa del combustible fino por déficit de presión de vapor (VPD).
- El consumo diario debe respetar estrictamente `DAILY_LOCATIONS_CAP = 9000` (el plan gratuito no comercial permite 10.000 ubicaciones/día): pedir estas variables en lotes existentes o bajo demanda por incidente/comuna con caché, nunca multiplicando ubicaciones sin presupuesto.

## Archivos

- `backend/providers/weather.py` (parámetro `models=`, nuevas variables horarias y consulta de niveles de presión)
- `backend/risk.py` (cálculo del Índice de Haines en variante media 850–700 hPa y alta 700–500 hPa según altitud)
- `backend/routes/comuna.py` y `backend/routes/public.py` (exposición en ficha de comuna e incidente)
- `web/js/views/incendio.js` (lectura en `dual(sencillo, técnico)` cuando exista dato)
- `docs/FUENTES.md` y `tests/` (pruebas unitarias del Índice de Haines y manejo de `None`)

## Criterio de listo

- `forecast_hourly` fija `models=` de forma explícita y solicita VPD, humedad de suelo superficial y `cape` sin superar el presupuesto diario `DAILY_LOCATIONS_CAP`.
- El cálculo del Índice de Haines está cubierto por pruebas unitarias (casos bajos, altos, datos faltantes y variante de altura).
- La ficha muestra fuente («Open-Meteo · ECMWF IFS»), hora y explicación en dos niveles sin inventar valores cuando falten niveles.
- CI en verde (`pytest` y revisión JS).

## Fuente y licencia

- **Nombre:** Open-Meteo Weather Forecast API (modelos ECMWF IFS / NOAA GFS / DWD ICON).
- **Enlace:** `https://api.open-meteo.com/v1/forecast` (<https://open-meteo.com/en/docs>).
- **Licencia:** Datos bajo **CC BY 4.0** con atribución a Open-Meteo; uso gratuito restringido a **fines estrictamente no comerciales** hasta 10.000 ubicaciones/día (<https://open-meteo.com/en/terms>).

---
id: RISK-25
repo: brasas
rama: feat/aire-co-pm10-aod
modelo: agente-alto
riesgo: B
archivos: backend/providers/weather.py, backend/services.py, backend/routes/public.py, backend/routes/climate.py, web/js/views/zona.js, docs/FUENTES.md, tests/
e2e: si
---

# RISK-25 · Calidad del aire pronosticada con CO, PM10, AOD y polvo (Open-Meteo Air Quality)

## Objetivo

Ampliar `air_quality()` en `backend/providers/weather.py` (`air-quality-api.open-meteo.com/v1/air-quality?domains=cams_global`) para solicitar `pm10`, `carbon_monoxide`, `aerosol_optical_depth` y `dust` además de `pm2_5`, permitiendo distinguir humo de combustión (alto MP2,5 + monóxido de carbono) de polvo en suspensión (alto MP10 + `dust`), y reemplazar las peticiones puntuales bajo demanda por lotes multi-ubicación de 50 comunas cada 6–12 h.

## Contexto

- Hoy `weather.air_quality` pide solo `pm2_5` a 2 días punto por punto (`backend/routes/public.py:728-768`), lo que no distingue episodios de polvo del norte de plumas de humo forestal y consume más peticiones HTTP.
- Con lotes de 50 comunas en el ciclo cada 6–12 h, cubrir las 345 comunas cuesta ~7 peticiones HTTP por corrida (345 ubicaciones), habilitando además un panorama nacional de humo pronosticado.
- Debe seguir rotulándose siempre como **pronóstico de modelo** (CAMS), separado de las mediciones reales de SINCA.

## Archivos

- `backend/providers/weather.py` (`air_quality` y versión por lotes `air_quality_batch` con `pm2_5`, `pm10`, `carbon_monoxide`, `aerosol_optical_depth`, `dust`)
- `backend/services.py` (refresco periódico en lotes respetando el cupo diario de Open-Meteo)
- `backend/routes/public.py` y `backend/routes/climate.py` (campos e indicador humo vs polvo)
- `web/js/views/zona.js` (mostrar distinción humo/polvo cuando el dato sea relevante, con `dual`)
- `docs/FUENTES.md` y `tests/`

## Criterio de listo

- La consulta a Open-Meteo Air Quality incluye `pm2_5`, `pm10`, `carbon_monoxide`, `aerosol_optical_depth` y `dust` con `domains=cams_global`.
- El refresco por comunas usa lotes de hasta 50 ubicaciones dentro del presupuesto diario y degrada a `None` si falla.
- La interfaz indica claramente que es pronóstico del modelo CAMS vía Open-Meteo y distingue humo probable frente a polvo sin emitir falsas alarmas.
- CI en verde (`pytest` y `e2e`).

## Fuente y licencia

- **Nombre:** Open-Meteo Air Quality API (modelo CAMS Global de Copernicus).
- **Enlace:** `https://air-quality-api.open-meteo.com/v1/air-quality` (<https://open-meteo.com/en/docs/air-quality-api>).
- **Licencia:** Datos bajo **CC BY 4.0** con atribución; uso gratuito **únicamente no comercial** (<https://open-meteo.com/en/terms>).

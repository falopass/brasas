---
id: RISK-28
repo: brasas
rama: feat/sequia-satelital-y-ensemble
modelo: agente-alto
riesgo: B
archivos: scripts/, backend/providers/weather.py, web/data/, web/js/views/riesgo.js, web/js/views/historia.js, docs/FUENTES.md, tests/
e2e: no
---

# RISK-28 · Sequía satelital (NOAA VHI, Copernicus SWI, NASA SMAP), pronóstico Ensemble y evaluación SPEI/CR2MET

## Objetivo

Enriquecer el análisis de sequía estacional y pronóstico de riesgo por comuna incorporando: (1) **NOAA STAR VHI** semanal a 4 km como indicador directo de estrés térmico-vegetal por comuna (mismo flujo semanal en GitHub Actions que `RISK-11`), (2) evaluación/integración de humedad real del suelo satelital (**Copernicus CLMS SWI** ~12,5 km y/o **NASA SMAP** 9 km vía AppEEARS), (3) **Open-Meteo Ensemble API** (`ecmwf_ifs025_ensemble` / `gfs_seamless`) para bandas de incertidumbre de viento y lluvia a 3–10 días (una vez liberado cupo con `RISK-26`), y (4) evaluación histórica de **Global SPEI** y **CR2MET v2.5** para reconstrucción e Historia.

## Contexto

- Hoy el modelo FWI (DMC/DC) es puramente meteorológico y no observa riego, napa freática ni estrés térmico acumulado real de la vegetación (`atmosfera.md` §4.E.18–20 y §4.A.1).
- **Atención a licencias:**
  - NOAA STAR VHI es dominio público sin clave.
  - NASA SMAP / AppEEARS es CC0 con Earthdata Login gratuito.
  - Global SPEI (`spei.csic.es`) usa **ODbL** (exige *share-alike*), por lo que debe evaluarse su compatibilidad antes de mezclarlo con datasets CC BY 4.0 en `/api/opendata/`.
  - CR2MET v2.5 (`ftp.cr2.cl` / Zenodo) tiene ~9 días de rezago (sirve para Historia/validación, no NRT según `INV-08`).

## Archivos

- `scripts/` (job semanal de recorte y promedio comunal de NOAA STAR VHI —y opcionalmente CLMS SWI / SMAP— hacia JSON versionado)
- `backend/providers/weather.py` (soporte opcional de `ensemble-api.open-meteo.com/v1/ensemble` con percentil 10/50/90 de rachas y lluvia)
- `web/js/views/riesgo.js` y `web/js/views/historia.js`
- `docs/investigacion/` (compatibilidad ODbL de SPEI y validación CR2MET), `docs/FUENTES.md` y `tests/`

## Criterio de listo

- El indicador semanal NOAA STAR VHI por comuna se genera de forma reproducible con atribución y fecha de compuesto en `docs/FUENTES.md`.
- La respuesta de Ensemble (si se activa tras `RISK-26`) respeta los límites de llamadas de Open-Meteo y muestra incertidumbre en lenguaje dual comprensible.
- Queda documentada la decisión sobre compatibilidad ODbL de Global SPEI antes de exponer derivados en `/api/opendata/`.
- CI en verde (`pytest`).

## Fuente y licencia

- **Nombre:** NOAA STAR Blended-VHP (VHI), Copernicus CLMS Global SWI, NASA SMAP (AppEEARS), Open-Meteo Ensemble API, CSIC Global SPEI y (CR)2 CR2MET v2.5.
- **Enlace:** <https://www.star.nesdis.noaa.gov/smcd/emb/vci/VH/> · <https://land.copernicus.eu/en/products/soil-moisture> · <https://appeears.earthdatacloud.nasa.gov/api/> · <https://ensemble-api.open-meteo.com/v1/ensemble> · <https://spei.csic.es/database.html> · <https://zenodo.org/records/7529682>.
- **Licencia:** Dominio público para NOAA STAR VHI; **CC0** para NASA SMAP/AppEEARS; Copernicus libre y abierto con cita para CLMS SWI (**licencia exacta por confirmar** en <https://land.copernicus.eu/en/products/soil-moisture>); **CC BY 4.0** solo no comercial para Open-Meteo Ensemble (<https://open-meteo.com/en/terms>); **ODbL** para Global SPEI; **CC BY 4.0** para CR2MET v2.5.

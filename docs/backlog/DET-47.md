---
id: DET-47
repo: brasas
rama: feat/goes18-rapa-nui
modelo: agente-alto
riesgo: B
archivos: backend/providers/goes.py, backend/providers/glm.py, backend/services.py, docs/FUENTES.md, tests/
e2e: no
---

# DET-47 · GOES-18 `ABI-L2-FDCF` y cobertura GLM para Rapa Nui

## Objetivo

Incorporar el satélite GOES-18 (GOES-West, bucket S3 `noaa-goes18`) y una ventana geográfica dedicada para Rapa Nui (`lat ~ -27,1`, `lon ~ -109,4`), tanto para detecciones térmicas `ABI-L2-FDCF` en `backend/providers/goes.py` como para rayos en `backend/providers/glm.py`, ya que la ventana continental actual excluye el territorio insular.

## Contexto

- Hoy `backend/providers/goes.py:45` y `backend/providers/glm.py:72-73` fijan `READ_WINDOW = (-81.5, -56.5, -66.0, -17.0)`, que deja fuera a Rapa Nui (`lon -109,4`), y leen únicamente los buckets `noaa-goes16` / `noaa-goes19` (GOES-East, a 75,2° W, con ángulo extremo sobre Isla de Pascua).
- `noaa-goes18` (137° W) cubre Rapa Nui con mejor geometría y ofrece exactamente el mismo formato NetCDF4 (`ABI-L2-FDCF` cada ~10 min y `GLM-L2-LCFA` cada ~5 min) y proyección `goes_imager_projection` que ya procesan `goes.py` y `glm.py`.
- Debe respetarse el filtrado geográfico estricto sobre Rapa Nui (sin ingerir polinesia ni océano abierto innecesario) y su etiqueta de origen `GOES-18` en observaciones/incidentes.

## Archivos

- `backend/providers/goes.py` (soporte `noaa-goes18` y subventana de Rapa Nui)
- `backend/providers/glm.py` (soporte `noaa-goes18` / ventana de Rapa Nui en `in_chile`)
- `backend/services.py` (integración en ciclo de ingesta con aislamiento de fallos)
- `docs/FUENTES.md`
- `tests/` (pruebas unitarias de filtrado espacial en Rapa Nui y selección de bucket)

## Criterio de listo

- Una detección sintética o real sobre Rapa Nui proveniente de `noaa-goes18` pasa `in_chile` y se almacena con fuente `GOES-18` sin aumentar ruido en Chile continental.
- Un fallo en `noaa-goes18` no interrumpe la ingesta de `noaa-goes19` ni el ciclo general.
- `docs/FUENTES.md` documenta GOES-18 y su cobertura en Rapa Nui.
- CI en verde (`pytest`).

## Fuente y licencia

- **Nombre:** NOAA GOES-18 (GOES-West) `ABI-L2-FDCF` y `GLM-L2-LCFA` vía NOAA Open Data Dissemination (AWS S3).
- **Enlace:** `https://noaa-goes18.s3.amazonaws.com/` (<https://www.noaa.gov/information-technology/open-data-dissemination>).
- **Licencia:** Dominio público NOAA, gratis y sin clave.

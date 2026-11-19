---
id: RISK-27
repo: brasas
rama: feat/ndvi-viirs-respaldo-y-ndmi
modelo: agente-alto
riesgo: B
archivos: scripts/actualizar_sequedad_vegetacion.py, web/data/vegetacion-sequedad.json, docs/FUENTES.md, tests/
e2e: no
---

# RISK-27 · Respaldo de verdor con VIIRS `VNP13A1` (ORNL) y evaluación de `NDMI`/`dNBR` Sentinel-2

## Objetivo

Añadir VIIRS `VNP13A1` (500 m, 16 días, vía ORNL REST API) como sucesor/respaldo automático de `MOD13Q1` en `scripts/actualizar_sequedad_vegetacion.py` para evitar estancamientos cuando ORNL retrasa MODIS, ampliar la cobertura hacia las 345 comunas y diseñar/evaluar el cálculo comunal de `NDMI` (humedad viva foliar) y `dNBR` (severidad post-incendio para aluviones) con Sentinel-2 L2A vía CDSE STAC o NASA AppEEARS.

## Contexto

- En producción (`cierre-brasa-2026-11-17.md#L48-L58`), `actualizar_sequedad_vegetacion.py` quedó atascado en el compuesto `MOD13Q1` del 16-10 dejando 57 comunas sin dato.
- `https://modis.ornl.gov/rst/api/v1/VNP13A1` sigue el mismo patrón REST que ya usa el script (sin clave) y entrega el sucesor operacional VIIRS.
- Además, el NDVI refleja verdor con semanas de rezago respecto al estrés hídrico real; el índice `NDMI` `(B8A - B11)/(B8A + B11)` en Sentinel-2 mide contenido de agua foliar, y `dNBR` cuantifica la severidad de quema de cicatrices para aluviones (`AGUA-04`). Se puede apoyar en NASA AppEEARS / CMR (`appeears.earthdatacloud.nasa.gov`) o CDSE STAC (`stac.dataspace.copernicus.eu/v1/`).

## Archivos

- `scripts/actualizar_sequedad_vegetacion.py` (respaldo automático a `VNP13A1` con etiqueta de sensor/fecha y ampliación gradual a más comunas)
- `web/data/vegetacion-sequedad.json` (incluir fuente `MOD13Q1` vs `VNP13A1` por comuna/corrida)
- `docs/investigacion/` (nota técnica de viabilidad, cuotas y licencia para `NDMI`/`dNBR` vía CDSE STAC o AppEEARS)
- `docs/FUENTES.md` y `tests/`

## Criterio de listo

- Cuando `MOD13Q1` tenga >20 días de rezago o falle, `actualizar_sequedad_vegetacion.py` consulta `VNP13A1` dejando constancia explícita del producto y fecha en `vegetacion-sequedad.json`.
- Queda documentada la arquitectura y términos de licencia verificados antes de activar un pipeline permanente de `NDMI`/`dNBR` con CDSE o AppEEARS.
- CI en verde (`pytest`).

## Fuente y licencia

- **Nombre:** ORNL DAAC MODIS/VIIRS Subsets (`VNP13A1`), NASA AppEEARS / CMR y Copernicus Data Space Ecosystem (Sentinel-2 L2A).
- **Enlace:** `https://modis.ornl.gov/rst/api/v1/VNP13A1` · `https://appeears.earthdatacloud.nasa.gov/api/` · `https://stac.dataspace.copernicus.eu/v1/`.
- **Licencia:** Dominio público / **CC0** para NASA EOSDIS y ORNL DAAC (<https://www.earthdata.nasa.gov/engage/open-data-services-and-software/data-and-information-policy>); para Sentinel-2 vía Copernicus Data Space Ecosystem, **licencia por confirmar** en los términos de Copernicus/CDSE en <https://dataspace.copernicus.eu/> (requiere registro gratuito).

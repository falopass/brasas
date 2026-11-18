---
id: DET-49
repo: brasas
rama: feat/sentinel3-slstr-frp
modelo: agente-alto
riesgo: B
archivos: backend/providers/sentinel3.py, backend/services.py, backend/config.py, docs/FUENTES.md, tests/
e2e: no
---

# DET-49 · Tercera familia satelital polar: Sentinel-3 SLSTR FRP (noche SWIR 500 m) vía CDSE

## Objetivo

Evaluar e integrar los productos de potencia radiativa del fuego **Sentinel-3 SLSTR `SL_2_FRP`** desde Copernicus Data Space Ecosystem (CDSE) como tercera constelación polar independiente de NASA FIRMS/NOAA, aprovechando sus canales SWIR nocturnos a ~500 m (complemento clave para fuegos activos bajo humo o de menor tamaño en pasadas vespertinas/nocturnas).

## Contexto

- Hoy toda la detección polar depende de NASA FIRMS (VIIRS + MODIS). Si FIRMS o NOAA sufren demoras o cortes, o en pasadas entre órbitas (~10:30 / 22:30 hora local de Sentinel-3A/B), BRASA queda sin ojos polares de alta sensibilidad nocturna.
- El catálogo OData/STAC de CDSE permite filtrar `SL_2_FRP___` NRT sobre la caja de Chile con cuenta gratuita CDSE (credenciales en secretos del entorno, nunca en el repo).

## Archivos

- `backend/providers/sentinel3.py` (búsqueda OData/STAC y parseo de focos FRP nocturnos sobre Chile)
- `backend/config.py` y `backend/services.py` (integración opcional condicionada a credenciales configuradas y aislamiento de fallos)
- `docs/FUENTES.md` y `tests/` (fixtures reales o sintéticos del esquema `SL_2_FRP` sin credenciales en código)

## Criterio de listo

- Sin credenciales CDSE configuradas el proveedor permanece inactivo sin degradar el estado de salud ni el ciclo actual.
- Con credenciales CDSE y fixture/respuesta de prueba, los focos dentro de Chile ingresan con fuente `Sentinel-3 SLSTR`, confianza y FRP en MW sin duplicar incidentes existentes.
- CI en verde (`pytest`).

## Fuente y licencia

- **Nombre:** ESA / Copernicus Sentinel-3 SLSTR `SL_2_FRP` vía Copernicus Data Space Ecosystem (CDSE).
- **Enlace:** `https://catalogue.dataspace.copernicus.eu/odata/v1` (<https://dataspace.copernicus.eu/>).
- **Licencia:** Licencia por confirmar en los términos legales vigentes del Copernicus Data Space Ecosystem en <https://dataspace.copernicus.eu/> (datos Copernicus libres y abiertos con atribución; verificar cláusulas exactas del aviso legal al crear las credenciales).

---
id: OPS-30
repo: brasas
rama: fix/rate-limit-cuotas-y-errores-ciclo
modelo: agente-alto
riesgo: B
archivos: backend/routes/community.py, backend/routes/public.py, backend/services.py, web/js/views/calidad.js, tests/
e2e: no
---

# OPS-30 · Rate limit en `polar` y `downwind-infrastructure`, y errores de `windgrid`/`aluvion` en Calidad

## Objetivo

Proteger las cuotas externas de NASA FIRMS y Overpass frente a peticiones repetidas sin control, y publicar en `/api/status` y `#/calidad` los errores de `windgrid` y `aluvion` que hoy solo quedan silenciosos.

## Contexto

- Hallazgos #9 y #12 de `CONSOLIDADO.md`:
  - `POST /api/cases/{id}/polar` (`backend/routes/community.py:569-589`) no verifica primero si `case-firms:{case_id}` ya está en caché ni aplica rate limit, pudiendo agotar la cuota de `FIRMS_MAP_KEY` compartida con la ingesta en vivo.
  - `GET /api/incidents/{id}/downwind-infrastructure` y `/api/terrain/downwind-infrastructure` (`backend/routes/public.py:476-516`) carecen de rate limit hacia Overpass.
  - Los errores de `windgrid` y `aluvion` (`backend/services.py:1934-1980`) no figuran entre las claves `*_error` publicadas por `_publish_cycle` ni en `CYCLE_ERRORS` de `web/js/views/calidad.js:273`.

- Seguimiento de [DET-46](hecho/det-46.md) (#896): la clave `case-firms:{case_id}` no incluye las fuentes consultadas; al leer la caché previa, invalidarla (o versionar la clave) cuando cambie `firms_sources` del caso, para que los casos 2024+ ya cargados reciban `VIIRS_NOAA21_SP`.
- Choque de archivos: #896 cambia el sello del ciclo en `backend/services.py` (`_source_outcomes`, `last_ingest_at`); rebasar sobre #896 antes de tocar `_publish_cycle`.

## Archivos

- `backend/routes/community.py` (lectura previa de caché y límite por IP en `load_case_polar`)
- `backend/routes/public.py` (límite por IP en rutas `downwind-infrastructure`)
- `backend/services.py` (incluir `windgrid_error` y `aluvion_error` en el resumen del ciclo)
- `web/js/views/calidad.js` (entradas en `CYCLE_ERRORS`)
- `tests/`

## Criterio de listo

- `POST /api/cases/{id}/polar` devuelve el resultado cacheado sin llamar a FIRMS si ya existe `case-firms:{case_id}`, y limita ráfagas por IP.
- Las rutas `downwind-infrastructure` aplican rate limit por IP (reutilizando la lógica de `routes/common.py`).
- `windgrid_error` y `aluvion_error` aparecen en `errors.cycle_errors` de `/api/status` y en texto legible en `#/calidad`.
- Un caso con `case-firms:{case_id}` en caché y una fuente nueva en `firms_sources` vuelve a consultar FIRMS solo por la fuente faltante (o recarga una vez).
- CI en verde.

## Fuente y licencia

- **Nombre:** Revisión interna de código (`CONSOLIDADO.md`, hallazgos #9 y #12).
- **Enlace:** `backend/routes/community.py`, `backend/routes/public.py`, `backend/services.py`, `web/js/views/calidad.js`.
- **Licencia:** N/A (código propio).

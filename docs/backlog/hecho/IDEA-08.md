---
id: IDEA-08
repo: brasas
rama: feat/vialidad-cortes-incendio
modelo: agente-alto
riesgo: B
archivos: backend/providers/vialidad.py, backend/routes/public.py, web/js/api.js, web/js/views/incendio.js, docs/FUENTES.md, tests/
e2e: no
---

# IDEA-08 · Cortes de caminos en la ficha del incendio (Vialidad)

## Objetivo

Mostrar en la ficha de un incidente las emergencias viales vigentes que afectan el tránsito a ≤30 km, con camino, tramo, restricción y hora informada por la fuente, sin calcular desvíos.

## Contexto

- `docs/BACKLOG_MAESTRO.md` ya pedía investigar cierres de rutas con fuente oficial; la oportunidad externa de investigación propone usar el servicio público de Vialidad (`Emergencias_Vialidad`).
- La capa 0 del MapServer de Vialidad concentra las emergencias vigentes como puntos y declara nombre de camino, tramo km, tránsito, restricción, resumen y fechas; se actualiza alrededor de las 15 h, no en tiempo real.

## Criterio de listo

- `GET /api/incidents/{id}/road-cuts` devuelve solo emergencias que afectan el tránsito dentro del radio, con fuente, enlace y fecha de actualización; la descarga externa queda en caché y con tope por IP.
- La ficha del incendio muestra el bloque «Cortes y restricciones de caminos» con hasta 4 tramos y aclaración de que Vialidad no calcula desvíos.
- CI en verde (`pytest`, `web`).

## Fuente y licencia

- **Nombre:** Dirección de Vialidad del Ministerio de Obras Públicas (MOP), servicio `Emergencias_Vialidad`.
- **Enlace:** <https://rest-sit.mop.gob.cl/arcgis/rest/services/VIALIDAD/Emergencias_Vialidad/MapServer>
- **Licencia:** servicio público de emergencia; atribución a la Dirección de Vialidad (MOP). Verificar términos de reutilización antes de redistribuir geometrías.

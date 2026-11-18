---
id: OFI-38
repo: brasas
rama: feat/openaq-respaldo-y-eval-redmeteo
modelo: agente-alto
riesgo: B
archivos: backend/providers/openaq.py, backend/providers/sinca.py, backend/services.py, backend/config.py, web/js/views/zona.js, docs/FUENTES.md, tests/
e2e: no
---

# OFI-38 · Respaldo de calidad del aire con OpenAQ v3 y evaluación de RedMeteo como referencia no oficial

## Objetivo

Integrar OpenAQ v3 (`api.openaq.org/v3`) como respaldo automático de `backend/providers/sinca.py` cuando el proxy y el snapshot de SINCA superen las 12 horas de antigüedad (filtrando estrictamente las fuentes por su licencia en `/v3/licenses` para no redistribuir sensores restrictivos como PurpleAir), y documentar/evaluar la viabilidad de RedMeteo 3.0 (`redmeteo.cl`) como referencia secundaria ciudadana claramente etiquetada como no oficial donde no haya estaciones DMC ni Agromet a <= 25 km.

## Contexto

- Hoy `sinca.mma.gob.cl` bloquea las IPs de Cloudflare, por lo que `sinca.py` depende de `SINCA_PROXY_URL` o de snapshots ≤12 h (`PASOS_DUENO.md`). OpenAQ v3 indexa estaciones oficiales chilenas (SINCA) desde una API alcanzable en Cloudflare (`60 req/min` y `2.000 req/h` con API key gratuita).
- Regla estricta en OpenAQ v3: cada ubicación indica su licencia en `/v3/licenses`; solo deben ingerirse fuentes cuya licencia permita redistribución abierta en apps públicas.
- Para RedMeteo (`redmeteoaficionadachile@gmail.com`), requiere solicitud por correo, caché propio obligatoria y etiqueta explícita «estación ciudadana no oficial» (`CLAUDE.md` y `atmosfera.md` §4.C.13). Ambos requieren gestión de acceso por la persona dueña antes de activarse en producción.

## Archivos

- `backend/providers/openaq.py` (consulta v3 cacheada por Chile con filtrado obligatorio por licencia permitida en `/v3/licenses`)
- `backend/providers/sinca.py` y `backend/services.py` (uso de OpenAQ como fallback cuando SINCA supera 12 h)
- `backend/config.py` (lectura opcional de `OPENAQ_API_KEY`)
- `web/js/views/zona.js` (mostrar fuente y licencia real de la lectura)
- `docs/investigacion/` (nota sobre respuesta/términos de RedMeteo) y `docs/FUENTES.md`, `tests/`

## Criterio de listo

- Sin `OPENAQ_API_KEY`, el ciclo no falla y sigue operando con SINCA como hoy.
- Las pruebas unitarias comprueban que mediciones en OpenAQ cuya licencia en `/v3/licenses` no permite redistribución quedan excluidas automáticamente.
- Cualquier dato mostrado conserva nombre de fuente, hora de Chile continental y enlace verificable.
- CI en verde (`pytest`).

## Fuente y licencia

- **Nombre:** OpenAQ API v3 y RedMeteo Chile (red ciudadana de aficionados).
- **Enlace:** `https://api.openaq.org/v3/` (<https://docs.openaq.org/>) · <https://redmeteo.cl/api.html>.
- **Licencia:** En OpenAQ v3, **licencia por confirmar por estación** consultando `https://api.openaq.org/v3/licenses` (filtrar solo fuentes con redistribución permitida); en RedMeteo, **licencia por confirmar** en <https://redmeteo.cl/api.html> y mediante autorización formal por correo antes de integrar.

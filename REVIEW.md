# REVIEW.md — BRASA Chile

Instrucciones para el revisor automático (Devin Review). Responde en español.

## Contexto
App ciudadana de alertas de incendios para Chile. Backend Python/FastAPI + web estática,
despliegue en Cloudflare. El backlog vive en `docs/backlog/` y `CLAUDE.md` tiene el mapa del código.

## Revisa con rigor (camino crítico)
- `backend/routes/community.py`, Turnstile (`backend/security.py`), `web/js/reportes.js`,
  la caché de `/api/reports` y el service worker: cualquier error aquí rompe el reporte
  ciudadano o deja datos públicos corruptos. Exige consistencia con los tests de reportes.
- Datos geoespaciales: orden lat/lon (EPSG:4326), unidades (ha vs m²), zona horaria de Chile
  (UTC-3/-4, no offset fijo), frescura y deduplicación de focos de incendio.
- PII y seguridad: nada personal público, Turnstile no se salta, sin secretos en código o fixtures.

## Ignora
- Comentarios de estilo fuera del diff. Notas de backlog en `docs/` salvo que contradigan el código.
- `deploy/` solo se toca cuando el encargo lo pide; no sugerir cambios ahí por iniciativa.

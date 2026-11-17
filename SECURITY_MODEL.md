# Modelo de amenazas — BRASA Chile

Usado por los escaneos de seguridad de Devin para priorizar hallazgos. Edítalo cuando cambien el sistema o las prioridades. Infraestructura: `wrangler.jsonc` de este repo (no hay repo de infraestructura aparte).

## Prioridades (Diego, 2026-11-17)

- Todos los activos pesan igual: datos personales y acceso a paneles de administración.
- Importan todos los atacantes: anónimo en internet, usuaria registrada contra otra y quien obtiene una clave o cookie de panel.
- Fuera de alcance / riesgo aceptado: nada. Todo cuenta, incluidos DoS y gasto de cuotas.

Parte de `docs/REVISION_SEGURIDAD.md` (SEC-13, 2026-10-19), que sigue siendo el detalle de referencia.

## Componentes

| Componente | Código | Despliegue |
|---|---|---|
| `BRASA-API` | `backend/` (`routes/*`, `security.py`, `reports.py`, `storage.py`, `notify/*`, `db.py`, `services.py`) | Contenedor único (`max_instances: 1`), SQLite `brasa.db` + `work.db`, respaldos en R2 |
| `BRASA-Edge-Web` | `deploy/cloudflare/src/*`, `web/` (incl. `web/sw.js`) | Worker frente al contenedor; PWA con service worker |

## Límites de confianza y puntos de entrada

- Anónimo: `/api/*` públicas (observaciones, incidentes, riesgo, casos), reportes ciudadanos con foto (Turnstile), suscripción push, `/docs` y `/openapi.json`.
- Persona con token (`X-Brasa-Token`): lugares, avisos, enlace de familia `#/v/<token>`, `DELETE /api/me`.
- Administración: `ADMIN_TOKEN` único; `INTERNAL_TOKEN` para rutas internas.
- Salida a proveedores: NASA FIRMS, GOES, CONAF (ArcGIS y CSV), Telegram, Web Push.

## Activos

- Datos personales (Ley 21.719): ubicación de lugares guardados, avisos, fotos de reportes.
- Disponibilidad del contenedor único y cuota compartida de NASA FIRMS.
- Secretos: `ADMIN_TOKEN`, `INTERNAL_TOKEN`, Turnstile, Telegram, VAPID.

## Controles existentes

- Autorización por recurso, tokens de alta entropía, comparación en tiempo constante, SQL parametrizado, validación de fotos.
- CSP idéntica en `backend/security.py` y `deploy/cloudflare/src/index.ts`, HSTS, `nosniff`, sin CORS.

## Riesgos conocidos (siguen en alcance)

Los de `docs/REVISION_SEGURIDAD.md`: cuota FIRMS sin límite en `/api/cases/{id}/polar`; rate limits incompletos; `ADMIN_TOKEN` único sin límite ni revocación; `INTERNAL_TOKEN` con acceso a base y fotos; confianza en `X-Forwarded-For`; Turnstile fail-open; service worker conserva datos tras `DELETE /api/me`; `/docs` público; SSRF ciego por endpoints push.

## Preguntas abiertas

Las de `docs/REVISION_SEGURIDAD.md` (IP real detrás de Cloudflare, `Vary: X-Brasa-Token`, CVEs de dependencias, tamaños máximos de respuestas externas).

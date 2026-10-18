# BRASA Chile — guía para agentes de código

Sistema ciudadano de alerta de incendios forestales para Chile: detecciones satelitales (GOES-19 cada 10 min, VIIRS) agrupadas en incidentes, avisos por lugar guardado, riesgo por comuna, fuentes oficiales de CONAF y reconstrucción de incendios históricos. Repositorio público `falopass/brasas`, rama `main`, desplegado en Cloudflare (Worker + Container + R2).

## Comandos

```bash
python dev.py setup [--e2e]   # .venv + dependencias (+ Playwright)
python dev.py run [--demo]    # http://127.0.0.1:8000 (demo: data/demo, sin ingesta)
python dev.py seed            # datos de ejemplo (incidente, CONAF, Botón Rojo)
python dev.py test [-k ...]   # pytest
python dev.py check           # ANTES DE CADA COMMIT: pytest + node --check web/**/*.js + reglas de diseño
python dev.py e2e             # con el servidor corriendo: errores JS, CSP y textos cortados en 320/390/1280 px
```

Guía completa: `docs/DESARROLLO_LOCAL.md`. Convenciones: `CONTRIBUTING.md`.

## Mapa rápido

- `backend/services.py`: ciclo de ingesta (`ingest_cycle`, `tick`, `tick_and_backup`), CONAF (`ingest_official_fires`, `ingest_boton_rojo`), respaldos.
- `backend/incidents.py`: agrupación, estados (`anomalia → posible → reportado`; `confirmado/controlado` solo vía `link_official`), fuentes fijas, `expire`, `prune`.
- `backend/alerts.py`: `evaluate` (satélite, omite fuentes fijas, menciona el incidente) y `evaluate_official` («CONAF informa»).
- `backend/providers/conaf.py`: Botón Rojo (ArcGIS) e incendios (CSV público de GEPRIF).
- `backend/routes/public.py`: `/api/observations` (con `incident_id`), `/api/incidents[/{id}]`, `/api/official-fires`, `/api/risk` (con `boton_rojo`).
- `backend/routes/personal.py`: lugares, `build_summary` (estado del lugar: urgente/aviso/riesgo/tranquilo), enlace de familia.
- `backend/db.py`: `brasa.db` (personas, respaldada) + `work.db` adjunta como `work` (reconstruible, respaldada cada hora). Migraciones en `_migrate_user`.
- `backend/security.py` y `deploy/cloudflare/src/index.ts`: la CSP debe ser idéntica en ambos (lo verifica `tests/test_security.py`).
- `web/js/views/`: `zona.js` (Mi zona y modo emergencia), `mapa.js`, `riesgo.js`, `casos.js`, `incendio.js`, `preparate.js`, `vecino.js` (`#/v/<token>`).
- `web/data/cases.json`: casos con `scope` y `figures[].revisions[]` (cada revisión con fuente, enlace y fecha).

## Reglas

- Español neutro, sin voseo, en todo (interfaz, comentarios, documentos, commits).
- Interfaz en dos niveles: `dual(sencillo, técnico)`. Que lo entiendan «la abuela y el amigo experto».
- Nunca datos simulados en vistas reales. Toda fuente oficial, con nombre y enlace. «Confirmado» solo con CONAF.
- El repo es público: ningún secreto en archivos ni en entradas de workflows. Los secretos los agrega la persona dueña en GitHub.
- Sin dependencias nuevas de frontend; sin scripts en línea (CSP).
- Commits: autor y committer `Claude <noreply@anthropic.com>` cuando los hace un agente; sin identificadores de modelo en el repositorio.
- Desplegar es manual: `gh workflow run deploy-cloudflare.yml --ref main` y después `gh workflow run diagnostico-cloudflare.yml --ref main -f minutos=11`. Las anotaciones del diagnóstico se leen con `gh api repos/falopass/brasas/check-runs/<job>/annotations`.

## Estado (octubre de 2026, v0.6.0)

La **Fase 1** del plan «next level» (`docs/PLAN_NEXT_LEVEL.md`) está terminada y en producción: incidentes, ficha de incidente, Botón Rojo e incendios de CONAF, modo emergencia, contenido de evacuación e Historia con cifras con fuente (6 casos).

Siguiente: **Fase 2** (riesgo explicado): FWI propio, anomalía de lluvia, riesgo en 3 capas, panel El Niño, viento animado, avisos DMC (CAP, dominio público) y Telegram. Detalle y pendientes en `docs/PLAN_NEXT_LEVEL.md`.

Decisiones pendientes de la persona dueña: autorización formal de CONAF para el CSV de incendios (sin licencia declarada); acceso oficial a alertas de SENAPRED (su API es interna); bot de Telegram (@BotFather) y proveedor de SMS.

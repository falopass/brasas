# AGENTS.md — BRASA Chile

> Agentes (Devin, Claude, Codex, DeepSeek…): lean esto ANTES de tocar el repositorio. Aplica también a las sesiones Cloud, que corren en VMs y NO ven la configuración de la máquina del dueño.

## Qué es
BRASA Chile: app ciudadana de alertas de incendios para Chile. Backend Python/FastAPI + web estática; despliegue en Cloudflare (Workers/Containers + R2). El backlog vivo está en `docs/BACKLOG_MAESTRO.md`.

**Lee también `CLAUDE.md`**: tiene el mapa del código, los comandos de `dev.py`, las reglas de interfaz y datos, y el estado de la versión. Devin no lo carga solo.

## Límites de recursos (RAM) — obligatorio
La máquina de desarrollo es de una sola persona y no se puede saturar. En local:
- MAX_BUILD=1 · MAX_FULL_TEST_SUITE=1 · MAX_DEV_SERVER=1 · MAX_BROWSER=1 · MAX_HEAVY_TASKS=1 · TEST_RUNNER_MAX_WORKERS=2
- Un build, un dev server, un navegador y una suite completa **a la vez**. Nada de paralelizar tareas pesadas.
- En Cloud (VM propia) puedes correr lo pesado, pero sigue siendo una tarea pesada a la vez por sesión.

## Subagentes
- Los subagentes **solo editan archivos y exploran** el repo. NO corren dev servers, builds, typecheck ni suites completas.
- Máximo 2 escribiendo a la vez, cada uno con archivos distintos. Los archivos compartidos (`CHANGELOG.md`, `requirements*.txt`, `deploy/`) los toca el agente principal.
- El agente principal ejecuta las tareas pesadas, de a una, y verifica una vez al final.

## Flujo de trabajo
- **Nunca push directo a `main`.** Una rama por tanda (`tipo/nombre-corto`) + un Pull Request: los encargos que tocan los mismos archivos van juntos en la misma rama. El título y el cuerpo del PR nombran los IDs de todos sus encargos (por ejemplo `(VEC-01, VEC-02)`).
- Merge con CI en verde: el agente mergea el PR (squash + `--delete-branch`) cuando el CI está en verde (y con la revisión de `geo-reviewer` si aplica). Nunca con el CI en rojo o pendiente, ni con conflictos. Deja el PR con resumen y checklist: el dueño lo revisa después.
- Commits en español (Conventional Commits: `feat:`, `fix:`, `docs:`…).
- Antes de empezar: `git switch main && git pull --rebase` (hay varias sesiones trabajando).
- Si rebasas una rama ya subida, súbela con `git push --force-with-lease`, nunca con `--force`.
- Actualiza `CHANGELOG.md` cuando corresponda.
- No toques `deploy/` salvo que el encargo lo pida explícitamente.

## Cómo testear y verificar
- **Sin pruebas en local.** En la máquina del dueño no se corre pytest, `.venv`, `dev.py test`/`check`/`e2e`, servidor ni navegador para validar: todo lo valida el CI de GitHub en el PR (ruff, pytest, JS, reglas de diseño y e2e), y el merge exige el CI en verde. Si el CI falla, lee el log (`gh run view <id> --log-failed`), corrige y vuelve a subir.
- Cuando un encargo pide «`python dev.py check`», «e2e» o «smoke» en verde, vale el CI del PR en verde.
- Verificación en producción: GET contra https://brasa-chile.ddiegosebastianbb.workers.dev, sin pruebas destructivas. En corridas desatendidas usa la herramienta fetch y no `curl`, porque `curl` queda pendiente de aprobación y se rechaza.
- Procedimientos paso a paso en `.devin/skills/`: `verificar`, `entregar-pr` y `desplegar` (este último solo con aprobación del dueño).

## Camino crítico: reportar
Cualquier cambio en `backend/routes/community.py`, Turnstile (`backend/security.py`), el formulario
(`web/js/ui.js`), `web/js/reportes.js`, la caché de `/api/reports` o el service worker **obliga** a que el CI
del PR pase las pruebas de reportes (`test_reports_safety`, `test_reportes_publicos`, `test_reports_caducidad`,
`test_alert_report`) y el e2e. Sin ese verde no hay merge. El flujo manual de `smoke-reporte` se corre solo en
una sesión Cloud y solo si el dueño lo pide.

## Datos geoespaciales
Antes de entregar un PR que toque ingesta, unidades o alertas, pide la revisión del subagente
`geo-reviewer` (`.devin/agents/geo-reviewer.md`): unidades (ha vs m²), orden lat/lon, EPSG:4326,
zona horaria de Chile (UTC-3/-4, no offset fijo), frescura y deduplicación de focos.

## Cómo trabajar
- Skills del repo: `verificar`, `entregar-pr`, `desplegar` (solo con OK del dueño) y `smoke-reporte`.
- Features grandes: primero un plan (Opus en modo Plan), revisión del dueño, y recién ahí SWE-2 implementa.
- E2E con navegador/Cesium y auditorías de seguridad: en Cloud con `/handoff`, no en la máquina local.

## Seguridad y datos
- Nunca secretos en el repo (commits, docs, fixtures). Las claves viven en secretos de Cloudflare.
- Nada personal es público: revisa SEC-01..SEC-05 del backlog antes de exponer datos.
- Contra producción solo sondas GET; borra lo que crees.

## Si algo no calza
- Si el backlog contradice el código, anótalo en el PR y decide lo mínimo razonable.
- Bloqueado >30 min en algo no esencial: sigue con otra parte y déjalo documentado.

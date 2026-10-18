# AGENTS.md — BRASA Chile

> Agentes (Devin, Claude, Codex, DeepSeek…): lean esto ANTES de tocar el repositorio. Aplica también a las sesiones Cloud, que corren en VMs y NO ven la configuración de la máquina del dueño.

## Qué es
BRASA Chile: app ciudadana de alertas de incendios para Chile. Backend Python/FastAPI + web estática; despliegue en Cloudflare (Workers/Containers + R2). El backlog vivo está en `docs/BACKLOG_MAESTRO.md`.

## Límites de recursos (RAM) — obligatorio
La máquina de desarrollo es de una sola persona y no se puede saturar. En local:
- MAX_BUILD=1 · MAX_FULL_TEST_SUITE=1 · MAX_DEV_SERVER=1 · MAX_BROWSER=1 · MAX_HEAVY_TASKS=1 · TEST_RUNNER_MAX_WORKERS=2
- Un build, un dev server, un navegador y una suite completa **a la vez**. Nada de paralelizar tareas pesadas.
- En Cloud (VM propia) puedes correr lo pesado, pero sigue siendo una tarea pesada a la vez por sesión.

## Subagentes
- Los subagentes **solo editan archivos y exploran** el repo. NO corren dev servers, builds, typecheck ni suites completas.
- El agente principal ejecuta las tareas pesadas, de a una.

## Flujo de trabajo
- **Nunca push directo a `main`.** Una rama por feature/fix (`tipo/nombre-corto`) + Pull Request.
- El merge lo hace el dueño; deja el PR con resumen y checklist.
- Commits en español (Conventional Commits: `feat:`, `fix:`, `docs:`…).
- Antes de empezar: `git switch main && git pull --rebase` (hay varias sesiones trabajando).
- Actualiza `CHANGELOG.md` cuando corresponda.
- No toques `deploy/` salvo que el encargo lo pida explícitamente.

## Cómo testear y verificar
- Check del repo: `python dev.py check` (pruebas + JS + reglas de diseño; debe quedar en verde).
- Backend: `python dev.py test` (pytest) con `ruff check` limpio.
- Interfaz: `python dev.py run --demo` y `python dev.py e2e`.
- Verificación en producción: `curl` GET contra https://brasa-chile.ddiegosebastianbb.workers.dev — sin pruebas destructivas.

## Seguridad y datos
- Nunca secretos en el repo (commits, docs, fixtures). Las claves viven en secretos de Cloudflare.
- Nada personal es público: revisa SEC-01..SEC-05 del backlog antes de exponer datos.
- Contra producción solo sondas GET; borra lo que crees.

## Si algo no calza
- Si el backlog contradice el código, anótalo en el PR y decide lo mínimo razonable.
- Bloqueado >30 min en algo no esencial: sigue con otra parte y déjalo documentado.

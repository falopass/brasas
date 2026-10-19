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
- **Nunca push directo a `main`.** Una rama por feature/fix (`tipo/nombre-corto`) + Pull Request.
- El merge lo autoriza el dueño: deja el PR con resumen y checklist. Ejecútalo solo cuando él lo pida o apruebe, con el CI en verde; nunca por iniciativa propia.
- Commits en español (Conventional Commits: `feat:`, `fix:`, `docs:`…).
- Antes de empezar: `git switch main && git pull --rebase` (hay varias sesiones trabajando).
- Si rebasas una rama ya subida, súbela con `git push --force-with-lease`, nunca con `--force`.
- Actualiza `CHANGELOG.md` cuando corresponda.
- No toques `deploy/` salvo que el encargo lo pida explícitamente.

## Cómo testear y verificar
- Check del repo: `python dev.py check` (pruebas + JS + reglas de diseño; debe quedar en verde).
- Backend: `python dev.py test` (pytest), y `ruff check` limpio si `ruff` está instalado (no está en `requirements-dev.txt` ni en el CI). Mientras iteras, acota con `python dev.py test -k <tema>`.
- Interfaz: `python dev.py run --demo` y `python dev.py e2e` (pesado: en Cloud, o en local solo si el encargo lo pide).
- Verificación en producción: GET contra https://brasa-chile.ddiegosebastianbb.workers.dev, sin pruebas destructivas. En corridas desatendidas usa la herramienta fetch y no `curl`, porque `curl` queda pendiente de aprobación y se rechaza.
- Procedimientos paso a paso en `.devin/skills/`: `verificar`, `entregar-pr` y `desplegar` (este último solo con aprobación del dueño).

## Seguridad y datos
- Nunca secretos en el repo (commits, docs, fixtures). Las claves viven en secretos de Cloudflare.
- Nada personal es público: revisa SEC-01..SEC-05 del backlog antes de exponer datos.
- Contra producción solo sondas GET; borra lo que crees.

## Si algo no calza
- Si el backlog contradice el código, anótalo en el PR y decide lo mínimo razonable.
- Bloqueado >30 min en algo no esencial: sigue con otra parte y déjalo documentado.

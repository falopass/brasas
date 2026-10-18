---
name: desplegar
description: Despliega BRASA a Cloudflare desde main y verifica que la versión quedó activa. Solo cuando el dueño lo pide explícitamente.
triggers:
  - user
---

# Desplegar BRASA

Solo con aprobación explícita del dueño en este encargo. Despliega `main`, nunca una rama.

1. Confirma que `main` tiene lo que se quiere publicar: `gh pr list --state merged --limit 5` y `CHANGELOG.md`.
2. Desplegar: anota el commit con `git fetch origin && git rev-parse origin/main` y lanza `gh workflow run deploy-cloudflare.yml --ref main`. Para seguir la corrida correcta (un push a `main` también dispara este workflow), lista `gh run list --workflow deploy-cloudflare.yml --event workflow_dispatch --json databaseId,headSha,createdAt,status --limit 5`, elige la que tenga ese `headSha` y se creó después del dispatch, y síguela con `gh run watch <databaseId>`.
3. Diagnóstico: `gh workflow run diagnostico-cloudflare.yml --ref main -f minutos=11`. Lee las anotaciones con `gh api repos/falopass/brasas/check-runs/<job>/annotations`.
4. Verifica con GET (herramienta fetch) contra `https://brasa-chile.ddiegosebastianbb.workers.dev`: la versión, el health y una vista pública. Nada destructivo.
5. Reporta qué corrida desplegó qué commit, lo que verificaste y cómo volver atrás (redesplegar el commit anterior con el mismo workflow).

No declares el deploy exitoso solo porque el workflow terminó en verde: el GET a producción manda.

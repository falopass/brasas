---
name: desplegar
description: Redespliega BRASA a Cloudflare a mano (o vuelve a un commit anterior) y verifica que la versión quedó activa. Cada merge a main que toca código ya se despliega solo.
triggers:
  - user
---

# Desplegar BRASA

Desde el 23-oct-2026 cada merge a `main` que toca código se despliega solo (`CLOUDFLARE_DEPLOY=true`). Esta skill es para redesplegar `main` a mano, nunca una rama. Para volver atrás: `git revert` del merge en una rama + PR con auto-merge; al mergearse se despliega solo.

1. Confirma que `main` tiene lo que se quiere publicar: `gh pr list --state merged --limit 5` y `CHANGELOG.md`.
2. Desplegar: anota el commit con `git fetch origin && git rev-parse origin/main` y lanza `gh workflow run deploy-cloudflare.yml --ref main`. Para seguir la corrida correcta (un push a `main` también dispara este workflow), lista `gh run list --workflow deploy-cloudflare.yml --event workflow_dispatch --json databaseId,headSha,createdAt,status --limit 5`, elige la que tenga ese `headSha` y se creó después del dispatch, y síguela con `gh run watch <databaseId>`.
3. Diagnóstico: `gh workflow run diagnostico-cloudflare.yml --ref main -f minutos=11`. Lee las anotaciones con `gh api repos/falopass/brasas/check-runs/<job>/annotations`.
4. Verifica con GET (herramienta fetch) contra `https://brasa-chile.ddiegosebastianbb.workers.dev`: la versión, el health y una vista pública. Nada destructivo.
5. Reporta qué corrida desplegó qué commit, lo que verificaste y cómo volver atrás (redesplegar el commit anterior con el mismo workflow).

No declares el deploy exitoso solo porque el workflow terminó en verde: el GET a producción manda.

---
name: entregar-pr
description: Sube el trabajo de BRASA en una rama propia y abre o actualiza su Pull Request sin tocar main. Úsala al cerrar cada bloque de trabajo.
---

# Entregar un cambio por PR

1. Rama propia: si estás en `main`, `git switch -c tipo/nombre-corto` (`feat/`, `fix/`, `docs/`, `ops/`).
2. Antes de subir: `git fetch origin && git rebase origin/main`. Si hay conflictos, resuélvelos y vuelve a verificar con la skill `verificar`.
3. Commits en español con Conventional Commits. Si el cambio lo nota alguien que usa la app, agrega la entrada en `CHANGELOG.md`.
4. Subir: `git push -u origin HEAD`. Si la rama ya estaba subida y la rebasaste: `git push --force-with-lease`.
5. PR: `gh pr create --base main --fill` (o `gh pr edit` si ya existe). Cuerpo:
   - Qué cambia y por qué (ítem del backlog, por ejemplo `FIX-12`).
   - Verificación: comandos corridos y resultado; lo no verificado, dicho como tal.
   - Riesgos y datos personales tocados (SEC-01..05), si aplica.
6. No mergees y no ejecutes `gh pr merge`. El merge lo decide el dueño.

Cierra tu respuesta con el enlace del PR y una línea `RESULTADO:`.

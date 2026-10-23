---
name: entregar-pr
description: Sube una tanda de trabajo de BRASA en su rama, abre o actualiza su Pull Request sin tocar main y lo mergea con el CI en verde. Úsala al cerrar cada bloque de trabajo.
---

# Entregar un cambio por PR

0. Antes de empezar, descarta un duplicado por cada ítem de la tanda: `gh pr list --state open --search "<ITEM>"` (el código entre paréntesis del título, por ejemplo `MAPA-01`). Si ya hay un PR abierto del mismo ítem, no abras otro: si es de tu sesión, actualízalo; si es de otra, trabaja sobre su rama o anota el solape en el PR y deja que el dueño decida cuál se queda. Dos PRs del mismo ítem pisan los mismos archivos y dejan el check en rojo aunque cada uno por separado esté bien (MAPA-01 y FUEGO-02, oct-2026).
1. Rama de la tanda: si estás en `main`, `git switch -c tipo/nombre-corto` (`feat/`, `fix/`, `docs/`, `ops/`). Una rama por tanda: los encargos que tocan los mismos archivos van juntos.
2. Commit primero: `git add` de los archivos de tu encargo (revisa `git status`; nada de `.env` ni datos locales) y `git commit` en español con Conventional Commits. Si el cambio lo nota alguien que usa la app, agrega antes la entrada en `CHANGELOG.md`. Mueve los encargos terminados a `docs/backlog/hecho/` (`git mv`) en el mismo PR.
3. Con el árbol limpio: `git fetch origin && git rebase origin/main`. Si hay conflictos, resuélvelos, `git rebase --continue` y vuelve a verificar con la skill `verificar`.
4. Subir: `git push -u origin HEAD`. Si la rama ya estaba subida y la rebasaste: `git push --force-with-lease`.
5. PR: escribe el cuerpo en un archivo temporal fuera del repo y úsalo con `gh pr create --base main --title "<tipo>: <resumen>" --body-file <archivo>` (o `gh pr edit --body-file <archivo>` si el PR ya existe). No uses `--fill`, porque arma el cuerpo con los commits y deja fuera lo que importa. El cuerpo lleva:
   - Qué cambia y por qué, con los IDs de todos los ítems de la tanda (por ejemplo `FIX-12, FIX-13`); el título también los nombra.
   - Verificación: comandos corridos y resultado; lo no verificado, dicho como tal.
   - Riesgos y datos personales tocados (SEC-01..05), si aplica.
6. Espera el CI con `gh pr checks --watch` y reporta el resultado.
7. Merge con el CI en verde: si todos los checks pasaron (y `geo-reviewer` revisó, si aplica), `gh pr merge --squash --delete-branch`. Con el CI en rojo o pendiente, o con conflictos, no mergees: arregla o reporta.

Cierra tu respuesta con el enlace del PR y una línea `RESULTADO:`.

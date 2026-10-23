---
name: revisar-pr
description: Revisa un PR abierto de BRASA sin mergearlo — resumen, check real, riesgo y choques con otros PRs abiertos.
---

# Revisar un PR sin mergearlo

Se usa para despejar la cola: primero se entiende y clasifica cada PR, después se mergea por riesgo.

## Pasos

1. **Contexto**: `gh pr view <N> --json title,body,files,additions,deletions,mergeStateStatus,statusCheckRollup`.
   Resume en 3 líneas qué cambia y para quién.
2. **Código real, no el diff del API**: `git fetch origin pull/<N>/head:pr-<N>` y
   `git worktree add --detach /tmp/pr-<N> pr-<N>`. Trabaja ahí; no toques el checkout principal.
3. **Check**: el resultado del CI del PR (`statusCheckRollup` del paso 1 o `gh pr checks <N>`); en local no se
   corre nada. Si el PR toca reportes, Turnstile, caché o el formulario, confirma que pasaron las pruebas de
   reportes y el e2e.
4. **Choques**: `gh pr list --state open --json number,title,files` y compara las rutas con las de este PR.
   Lista los PRs con las que comparte archivos y en qué líneas se cruzarían.
5. **Riesgo**:
   - **bajo**: docs, tests, config de agentes, CSS aislado.
   - **medio**: lógica de una capa, sin tocar URLs, datos oficiales ni CSP.
   - **alto**: ingesta, unidades, alertas, reportes, caché, CSP, migraciones o cambios de contrato.
6. **Veredicto** en 5 líneas: qué cambia, resultado del check, riesgo, choques y qué falta. **Nunca mergees**
   ni hagas push: la decisión es del dueño o de la fábrica.

## Regla de la cola

Con muchos PRs abiertos, primero se revisan y mergean los de riesgo **bajo**, después **medio**, y los
**alto** se rebasan uno por uno. Nunca dejar que la cola crezca por encima de 20 PRs abiertos.

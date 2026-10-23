---
name: verificar
description: Verifica un cambio en BRASA a través del CI de GitHub, sin correr pruebas en local. Úsala al terminar una edición de backend, web o datos.
---

# Verificar un cambio en BRASA

En local no se corre ninguna prueba: ni pytest, ni `.venv`, ni `dev.py test`/`check`/`e2e`, ni servidor o navegador. Todo lo valida el CI de GitHub en el PR (ruff, pytest, JS, reglas de diseño y e2e).

1. Antes del commit, relee el diff (`git diff`).
2. Si tocaste la CSP: `backend/security.py` y `deploy/cloudflare/src/index.ts` deben quedar idénticos (lo comprueba `tests/test_security.py` en el CI).
3. Sube la rama, abre o actualiza el PR y activa el auto-merge (skill `entregar-pr`); no hace falta esperar el CI.
4. Si el CI falla: `gh run view <id> --log-failed`, corrige, commit y push. Repite hasta verde.
5. Producción: solo GET, con la herramienta fetch, contra `https://brasa-chile.ddiegosebastianbb.workers.dev`.

En el PR, reporta el resultado del CI. Lo que no quedó validado, dilo; no lo inventes.

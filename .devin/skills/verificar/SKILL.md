---
name: verificar
description: Verifica un cambio en BRASA antes de abrir o actualizar un PR, respetando los límites de RAM. Úsala al terminar una edición de backend, web o datos.
---

# Verificar un cambio en BRASA

Verifica una sola vez, al final, desde el agente principal. Los subagentes no corren nada de esto.

1. Mientras iteras: solo pruebas acotadas al tema, `python dev.py test -k <tema>` (por ejemplo `-k conaf` o `-k alerts`).
2. Antes de cada commit, el gancho pre-commit corre `python dev.py check --rapido` (ruff, presupuestos de peso, `node --check`, pruebas JS y reglas de diseño; sin pytest) y no corre nada si solo cambian archivos `.md`. La suite completa y el e2e los corre el CI en cada PR: el CI en verde reemplaza al «`python dev.py check` en verde» de los encargos. No corras el `check` completo en local salvo que el encargo lo exija explícitamente.
3. Si tocaste Python y `ruff` está instalado en `.venv` (`.venv\Scripts\ruff.exe` en Windows, `.venv/bin/ruff` en Linux): `ruff check` limpio. Hoy no está en `requirements-dev.txt` ni en el CI; no lo agregues sin que el dueño lo pida, y si no está, dilo en el PR.
4. Si tocaste la CSP: `backend/security.py` y `deploy/cloudflare/src/index.ts` deben quedar idénticos (lo verifica `tests/test_security.py`).
5. Interfaz (`python dev.py run --demo` + `python dev.py e2e`): es pesado. Hazlo en una sesión Cloud, o en local solo si el encargo lo pide, y nunca con otro build, servidor o navegador corriendo.
6. Producción: solo GET, con la herramienta fetch, contra `https://brasa-chile.ddiegosebastianbb.workers.dev`.

En el PR, reporta qué corriste y su resultado. Si algo no lo corriste, dilo; no lo inventes.

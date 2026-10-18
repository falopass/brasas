---
name: verificar
description: Verifica un cambio en BRASA antes de abrir o actualizar un PR, respetando los límites de RAM. Úsala al terminar una edición de backend, web o datos.
---

# Verificar un cambio en BRASA

Verifica una sola vez, al final, desde el agente principal. Los subagentes no corren nada de esto.

1. Mientras iteras: solo pruebas acotadas al tema, `python dev.py test -k <tema>` (por ejemplo `-k conaf` o `-k alerts`).
2. Antes de cada commit: `python dev.py check`. Corre pytest, `node --check` sobre `web/**/*.js` y las reglas de diseño, y debe quedar en verde.
3. Si tocaste Python: `ruff check` limpio.
4. Si tocaste la CSP: `backend/security.py` y `deploy/cloudflare/src/index.ts` deben quedar idénticos (lo verifica `tests/test_security.py`).
5. Interfaz (`python dev.py run --demo` + `python dev.py e2e`): es pesado. Hazlo en una sesión Cloud, o en local solo si el encargo lo pide, y nunca con otro build, servidor o navegador corriendo.
6. Producción: solo GET, con la herramienta fetch, contra `https://brasa-chile.ddiegosebastianbb.workers.dev`.

En el PR, reporta qué corriste y su resultado. Si algo no lo corriste, dilo; no lo inventes.

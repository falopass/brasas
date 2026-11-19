---
id: PROD-03
repo: brasas
rama: feat/vigias-verificados-moderacion
modelo: agente-alto
riesgo: A
archivos: backend/db.py, backend/routes/community.py, backend/routes/admin.py, web/admin.html, web/js/views/admin.js, tests/
e2e: si
---

# PROD-03 · Vigías verificados (juntas de vecinos y bomberos) con prioridad en moderación

## Objetivo

Añadir el rol opcional de **vigía verificado** (integrantes acreditados de juntas de vecinos, cuerpos de bomberos o brigadas locales) habilitado manualmente desde el panel de administración, de modo que sus reportes ciudadanos aparezcan destacados y priorizados en la cola de moderación (`admin.py` / `web/admin.html`) manteniendo siempre la regla de que ningún reporte se publica ni dispara alertas sin pasar revisión o flujo seguro.

## Contexto

- Durante episodios simultáneos, la cola de moderación puede acumular muchos reportes de distinto origen; identificar en la cabecera a personas conocidas en terreno (bomberos o dirigentes vecinales verificados por la persona dueña) acelera el triaje sin abrir cuentas públicas ni exponer datos personales (`CLAUDE.md` / `CONTRIBUTING.md`).
- Por ser un cambio sobre `backend/routes/community.py` y el flujo de reportes, exige cumplimiento estricto de seguridad (`test_reports_safety`, `test_reportes_publicos`, privacidad Ley 21.719 y borrado en `delete_me`).

## Archivos

- `backend/db.py` (columna o tabla de acreditación de vigía vinculada al token/suscriptor sin exponer PII en endpoints públicos)
- `backend/routes/admin.py` y `web/admin.html` / `web/js/views/admin.js` (asignar/revocar etiqueta «Vigía verificado» y ordenar/filtrar cola por prioridad)
- `backend/routes/community.py` (marcar prioridad interna en cola al recibir reporte de vigía acreditado, sin auto-publicar sin control ni filtrar identidad en `/api/reports`)
- `tests/` (pruebas de reportes, privacidad y autorización de administrador)

## Criterio de listo

- Solo una persona administradora autenticada (`ADMIN_TOKEN`) puede otorgar o revocar la marca de vigía verificado.
- Los reportes enviados por un vigía verificado aparecen primero en `/web/admin.html` con distintivo visible; la API pública `/api/reports` nunca expone identificadores privados del vigía.
- `delete_me` elimina también la condición de vigía asociada al dispositivo.
- CI en verde (`pytest` incluidas todas las pruebas de reportes, revisión JS y `e2e`).

## Fuente y licencia

- **Nombre:** Propuesta de producto de la revisión interna (`CONSOLIDADO.md` §4).
- **Enlace:** `backend/routes/community.py` y `backend/routes/admin.py` en el repositorio.
- **Licencia:** N/A (funcionalidad propia del proyecto).

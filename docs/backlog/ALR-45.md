---
id: ALR-45
repo: brasas
rama: fix/alertas-segundo-foco-push-supresion
modelo: agente-alto
riesgo: A
archivos: backend/alerts.py, backend/services.py, backend/routes/personal.py, web/sw.js, tests/
e2e: si
---

# ALR-45 · Segundo foco en `evaluate`, `tag` push por nivel y supresión completa en `delete_me`

## Objetivo

Corregir tres defectos de confiabilidad y privacidad detectados en la revisión del 18-11-2026 (`CONSOLIDADO.md` #6, #10 y #11):
1. Evitar que un segundo foco distinto (>3 km) en el mismo ciclo quede marcado como evaluado tras el `break` del primer aviso en `evaluate`.
2. Evitar que una notificación push de nivel `aviso` sobrescriba en la bandeja del sistema a una notificación `urgente` por compartir `tag: place-<id>`.
3. Garantizar que `DELETE /api/me` (`delete_me`) elimine también `reports.subscriber_id`, `incident_follows` y `follow_alerts` en cumplimiento de la Ley 21.719.

## Estado frente a PRs abiertos (19-11-2026)

- **Parte 1 (segundo foco en `evaluate`): sigue abierta.** El PR [#895](https://github.com/falopass/brasas/pull/895) la intentó y la revirtió en `ae46bb8`: sin el corte por lugar, un mismo fuego visto por FIRMS y GOES a pocos km daba dos avisos en el mismo ciclo. Hoy `evaluate` mantiene un aviso por lugar y ciclo y el segundo foco avisa en el ciclo siguiente. Retomarla exige separar «mismo fuego en dos fuentes» de «foco distinto» y es un cambio de criterio de alertas: necesita aprobación de Sovran.
- **Lo que sí cubre #895 (no es parte de este encargo):** `evaluate_official` avisa por cada incendio CONAF nuevo dentro del radio (antes solo `near[0]`), la fusión de incidentes hereda `official_ref`/estado y `prune` deja de invalidar la caché espacial sin borrados.
- **Partes 2 (`tag` push por nivel en `web/sw.js`) y 3 (`delete_me`): siguen abiertas.** Verificado en `main`: `web/sw.js:174` usa `place-<id>` sin nivel y `delete_me` (`backend/routes/personal.py:130-142`) no toca `reports.subscriber_id`, `incident_follows` ni `follow_alerts`. Ningún PR abierto las cubre.
- Choque de archivos: rebasar sobre #895 (`backend/alerts.py`) y #896 (`backend/services.py`) antes de empezar.

## Contexto

- `backend/alerts.py:531,553` y `backend/services.py:1781`: `evaluate` hace `break` tras el primer aviso por lugar, pero luego el ciclo marca todas las detecciones como evaluadas; un segundo foco simultáneo a >3 km queda esperando hasta la siguiente detección (en VIIRS, la próxima pasada orbital).
- `web/sw.js:174`: usa `tag: data.place?.id ? 'place-' + data.place.id : undefined` sin distinguir nivel; un aviso posterior reemplaza silenciosamente una alerta urgente no leída.
- `backend/routes/personal.py:129-142`: `delete_me` borra `family_acks`, `alerts`, `places` y `subscribers`, pero omite desvincular `reports.subscriber_id` y borrar `incident_follows` / `follow_alerts`.

## Archivos

- `backend/alerts.py` y `backend/services.py` (marcar evaluadas solo las detecciones realmente procesadas o separar el filtro por foco/incidente)
- `web/sw.js` (incluir nivel o identificador único en `tag` para no pisar urgentes)
- `backend/routes/personal.py` (limpieza de `reports.subscriber_id`, `incident_follows` y `follow_alerts` en `delete_me`)
- `tests/` (pruebas unitarias para los tres casos)

## Criterio de listo

- Con dos focos distintos (>3 km) en el mismo ciclo dentro del radio de un lugar, el segundo no queda marcado como evaluado sin haberse avisado.
- En `web/sw.js`, una notificación `aviso` no reemplaza el `tag` de una `urgente` del mismo lugar.
- Tras `DELETE /api/me`, no quedan filas en `incident_follows` ni `follow_alerts` del suscriptor y `reports.subscriber_id` queda en `NULL`.
- Revisión `geo-reviewer` si aplica a `alerts.py` y CI en verde.

## Fuente y licencia

- **Nombre:** Revisión interna de código (`CONSOLIDADO.md`, hallazgos #6, #10 y #11).
- **Enlace:** `backend/alerts.py`, `web/sw.js`, `backend/routes/personal.py` en el repositorio.
- **Licencia:** N/A (código propio).

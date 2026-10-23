---
id: ALR-19
repo: brasas
rama: feat/silencio-nocturno-avisos
modelo: swe-2-high
riesgo: C
archivos: backend/alerts.py, web/js/ui.js, tests/test_alert_quiet_hours.py, CHANGELOG.md
e2e: si
intento: 0
ronda_review: 0
---

# ALR-19 · Horario de silencio para los avisos que no son urgentes (decisión)

## Por qué es delicado (va a decisión de Diego)

Cambia **cuándo** le llega un aviso a una persona. Es una decisión de producto y de seguridad: retrasar un aviso puede ser la diferencia entre enterarse a tiempo o no. Solo lo puede autorizar el dueño.

## Qué propongo

- Los avisos de nivel `aviso` (foco lejano, reporte de vecino, DMC, diario) que caigan entre 23:00 y 07:00 de Chile **no se envían**: quedan en cola y salen a las 07:00, con la hora original en el texto («te lo enviamos ahora porque anoche no quisimos despertarte»).
- Los de nivel `urgente` **nunca** se retrasan. Esa regla no se negocia: `ALERT_RANK` ya distingue los dos niveles (`backend/alerts.py:40`).
- Se puede apagar por lugar (columna nueva en `places`) o quedar fijo por diseño; eso es parte de la decisión: la columna implica una migración pequeña.

## Evidencia

- `backend/alerts.py` no tiene ninguna noción de hora local al entregar: `evaluate_*` crea los avisos y los manda en la misma pasada. `LEVEL_RANK` (`:40`) y `is_alertable` ya separan niveles; `compose_daily` (`:555`) usa `CHILE_TZ`.
- El backlog lo pide de forma indirecta en `docs/BACKLOG_MAESTRO.md:347` (ALR-09, «fatiga = la gente apaga los avisos») y el CHANGELOG ya documenta que los avisos se pueden apagar por completo (0.7.0). Apagarlos del todo es peor que no despertar a las 3 de la mañana por un foco a 40 km.

## Criterio de término (si lo apruebas)

- `pytest tests/test_alert_quiet_hours.py` (nuevo): un aviso `aviso` a las 02:00 de Chile no se entrega y sale a las 07:00; uno `urgente` a las 02:00 sale de inmediato; el texto dice por qué llegó tarde.
- `python dev.py check` en verde y `python dev.py e2e` sin problemas.
- El aviso reprogramado no se duplica ni pierde el `observation_id`.

Verifica con `/verificar` y entrega con `/entregar-pr`. No mergees.


Aprobado por Hermes (20-10): Diego delegó la decisión. Pasa a cola.


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.

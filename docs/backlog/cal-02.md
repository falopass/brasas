---
id: CAL-02
repo: brasas
rama: feat/calendario-con-avisos-dmc
modelo: swe-2-high
riesgo: B
archivos: backend/routes/calendar.py, tests/test_calendar_ics.py, CHANGELOG.md
e2e: no
intento: 0
ronda_review: 0
estado_desde: 2026-10-20T10:10:17
nota: Reencolado: la corrida falló por rate limit del modelo gratis, no por el ítem.
---

## Objetivo
Que el calendario `.ics` de una comuna incluya también los avisos oficiales de viento y calor extremo de la DMC vigentes, no solo los días de Botón Rojo, para que la familia vea en su propio calendario el día peligroso completo sin abrir la aplicación.

## Ítem del backlog
CAL-02, extensión de IDEA-14 (calendario de Botón Rojo) con los avisos DMC de OFI-01 y ALR-14.

## Evidencia
- `backend/routes/calendar.py:1-12` documenta que el feed lee **solo** `boton_rojo` y sirve un evento de día completo por día con Botón Rojo.
- `backend/providers/dmc.py` y la tabla `dmc_alerts` (`backend/db.py:188`) ya guardan los avisos CAP de viento y calor con sus horas, severidad y fuente; `/api/risk` y el resumen del lugar ya los publican.
- `tests/test_calendar_ics.py` cubre Botón Rojo, comuna desconocida, calendario vacío y plegado RFC 5545; no hay ningún caso de avisos DMC.

## Qué hacer
1. En `_ics`, agrega un `VEVENT` por aviso DMC vigente de la comuna: `UID` estable (`dmc-<id>@brasa`), `DTSTART`/`DTEND` con la hora del aviso en `America/Santiago` (o de día completo si el CAP solo trae fecha), `SUMMARY` con el tipo («Aviso de viento · DMC»), `DESCRIPTION` con severidad, enlace al aviso y la frase `NO_OFICIAL`, y `URL`.
2. Ordena los eventos por fecha, no dupliques avisos y excluye los vencidos; sin avisos, el calendario sigue siendo válido y vacío.
3. Mantén `X-WR-CALNAME` honesto: «Días peligrosos · <comuna>» si ahora incluye dos fuentes; si eso rompe `tests/test_calendar_ics.py`, actualiza la prueba con el nombre nuevo.
4. Agrega casos: aviso vigente incluido con su enlace; aviso vencido excluido; escape RFC 5545 del texto del CAP (puede traer comas y saltos de línea).

## Archivos
`backend/routes/calendar.py`, `tests/test_calendar_ics.py` y `CHANGELOG.md`. No toques `backend/providers/dmc.py`, `backend/db.py` ni vistas web.

## Criterio de listo (verificable)
`python dev.py test -k calendar` en verde con los 3 casos nuevos; un `.ics` de prueba de una comuna con Botón Rojo y aviso de viento trae los dos tipos de evento y valida como VCALENDAR.

## Cierre
Verifica con `/verificar` y entrega con `/entregar-pr`. No mergees por iniciativa propia.


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.

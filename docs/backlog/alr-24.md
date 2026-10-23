---
id: ALR-24
repo: brasas
rama: feat/aviso-edad-y-paso
modelo: swe-2-high
riesgo: B
archivos: backend/alerts.py, tests/test_risk_alerts.py, tests/test_alerts.py, CHANGELOG.md
e2e: no
intento: 0
ronda_review: 0
estado_desde: 2026-10-20T10:10:17
nota: Reencolado: la corrida falló por rate limit del modelo gratis, no por el ítem.
---

# ALR-24 · El aviso dice hace cuánto se detectó el foco y cuál es el paso siguiente

## Objetivo

Que cualquier aviso que reciba un vecino (push, Telegram o la lista de Avisos) diga **en palabras hace cuánto se detectó** el foco y termine con **un paso concreto**, sin que la persona tenga que interpretar una fecha ni buscar qué hacer.

## Ítem y evidencia

No viene de una fila del backlog: sale del código y de la prioridad 4 del foco («alertas útiles»). Hoy `compose()` (`backend/alerts.py:123-142`) arma el cuerpo con distancia, rumbo, viento, resumen del incidente y una marca **absoluta**: «Fuente: VIIRS NOAA-20 · 12-10 14:30 hora de Chile · confianza nominal» (`backend/alerts.py:139`). Un vecino que abre el push a las 3 de la mañana tiene que calcular mentalmente si eso es de hace 8 minutos o de hace 5 horas. Peor: el único paso a seguir aparece **solo** cuando el lugar tiene la marca de persona mayor (`backend/alerts.py:136-138`); el resto recibe «Un foco de calor no confirma un incendio…» (`:140`) sin ninguna instrucción. La app ya sabe que el aviso existe solo si la detección es reciente (`is_recent()`, `backend/alerts.py:58`), o sea que la edad es accionable, pero nunca se escribe.

## Qué hacer

1. En `backend/alerts.py`, agrega `age_phrase(observed_at, now)` que devuelva «hace menos de 5 minutos» (<5), «hace N minutos» (5-59), «hace N hora(s)» (≥60), en la misma zona horaria que el resto del archivo.
2. Define **una** constante `ACTION_LINE` («Si ves fuego o humo, llama al 130 (CONAF) o al 132 (Bomberos); no te acerques.») y agrégala exactamente una vez al final del cuerpo de `compose()`.
3. Usa la misma frase de edad en `compose_official()` (`:250`) y `compose_report()` (`:312`) con la hora que corresponda (detección CONAF y hora del reporte).
4. No cambies el título (los push lo truncan y hoy dice distancia), ni `classify()`, ni `escalation_due()`, ni los evaluadores. No toques vistas, `web/js` ni `docs/`.

## Criterio de listo

`python dev.py test -k alert` en verde, con pruebas nuevas que cubran: (a) 12 minutos → «hace 12 minutos»; (b) 3 horas → «hace 3 horas»; (c) 0 a 4 minutos → «hace menos de 5 minutos»; (d) `ACTION_LINE` aparece exactamente una vez en `compose`, `compose_official` y `compose_report`; (e) los tests que comparan el cuerpo completo se actualizan, no se borran.

Verifica con `/verificar` y entrega con `/entregar-pr`.


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.

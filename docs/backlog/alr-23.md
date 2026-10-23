---
id: ALR-23
repo: brasas
rama: feat/calendario-del-lugar
modelo: swe-2-high
riesgo: B
archivos: backend/routes/calendar.py, tests/test_calendar_ics.py, web/js/views/vecino.js, CHANGELOG.md
e2e: si
intento: 0
ronda_review: 0
estado_desde: 2026-10-20T10:10:17
nota: Reencolado: la corrida falló por rate limit del modelo gratis, no por el ítem.
---

**Objetivo:** que una familia pueda suscribir el calendario de su lugar y recibir ahí los días en que las condiciones van a estar peligrosas, no solo los días de Botón Rojo de CONAF, y que el enlace compartido ofrezca esa suscripción.

**Ítem del backlog:** IDEA-13 e IDEA-14 (calendario .ics). Hoy `backend/routes/calendar.py:83-96` sirve un único conjunto, `/calendar/boton-rojo/{code}.ics`, con un evento por día de Botón Rojo: si CONAF no pronostica Botón Rojo para la comuna (fuera de temporada, o comunas sin capa), el archivo baja vacío y la familia no recibe nada, aunque BRASA sí tenga un nivel alto o extremo calculado con el 30-30-30 y el FWI (`risk_daily`, ver `backend/routes/comuna.py:37-45`). El enlace compartido tampoco lo ofrece: `web/js/views/vecino.js:131-140` solo tiene «Que me avisen a mí también» y «Compartir el enlace», sin ninguna forma de suscribir el calendario.

**Qué hacer:**
1. En `backend/routes/calendar.py` agrega `/calendar/lugar/{code}.ics`, reusando `_esc`, `_fold` y `NO_OFICIAL`. Une dos fuentes: (a) los días con `boton_rojo` (texto actual, con su fuente CONAF y su enlace al tablero) y (b) los días con `risk_daily.level_combined` en `alto` o `extremo`, con `SUMMARY` del tipo «Condiciones peligrosas estimadas en <comuna>» y una `DESCRIPTION` que diga textualmente que es un escenario estimado de BRASA (30-30-30 + FWI), no un pronóstico oficial, más el enlace a senapred.cl. Si un día tiene las dos cosas, un solo VEVENT con las dos razones.
2. Sin filas, responde un VCALENDAR válido vacío, igual que hoy; `Cache-Control` 1800 s.
3. En `web/js/views/vecino.js`, junto al botón de compartir, agrega un enlace discreto «Recordarme los días peligrosos (.ics)» a `/calendar/lugar/${data.comuna.code}.ics`, solo si `data.comuna?.code` existe, con el aviso de que es una estimación de BRASA. No reordenes ni toques el resto de la vista.
4. `tests/test_calendar_ics.py`: un caso con Botón Rojo y riesgo alto el mismo día (un VEVENT, dos razones), uno con solo riesgo alto (evento con la etiqueta de estimación y la palabra «estimado» en la descripción), uno vacío (VCALENDAR sin VEVENT) y uno con 404 para una comuna inexistente. Verifica el plegado a 75 octetos con un texto acentuado.

**Archivos a tocar:** `backend/routes/calendar.py`, `tests/test_calendar_ics.py`, `web/js/views/vecino.js`, `CHANGELOG.md`. No toques nada más: `web/js/views/zona.js` está en curso (RISK-22) y `web/js/util.js` está bloqueado (FIX-60). En `vecino.js` el cambio es una sola línea de enlace junto al botón de compartir: no reordenes la vista. Esa vista también aparece en la tarjeta C UX-48, que sigue en `decision/` sin aprobar; si se aprueba antes de que salga esta rama, rebasa con `git pull --rebase` y deja el enlace donde calce.

**Criterio de listo:** `python dev.py test -k calendar` verde; `python dev.py check` verde; y con la demo, descargar `/calendar/lugar/7101.ics` y validar que abre y que cada VEVENT tiene `DTSTART;VALUE=DATE`, `UID` estable y una `DESCRIPTION` que aclara que no es pronóstico oficial.

Verifica con /verificar y entrega con /entregar-pr. No mergees por iniciativa propia.


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.

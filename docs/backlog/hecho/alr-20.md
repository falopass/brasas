---
id: ALR-20
repo: brasas
rama: feat/tope-anti-fatiga-avisos
modelo: swe-2-high
riesgo: C
archivos: backend/alerts.py, backend/services.py, tests/test_alert_caps.py, CHANGELOG.md
e2e: no
intento: 0
ronda_review: 0
---

# ALR-20 · Tope anti-fatiga de avisos por lugar (decisión)

## Por qué es delicado (va a decisión de Diego)

Cambia **cuántos** avisos le llegan a una persona y cuándo. Es la misma familia que ALR-19 (silencio nocturno) y FIX-08 (umbral de urgencia): un tope de más esconde un incendio real; un tope de menos hace que la familia apague las notificaciones y no reciba nada. Solo lo puede autorizar el dueño.

## Qué propongo

Implementar los topes que la investigación ya recomendó y que hoy no existen:

- **1 urgente por incidente y lugar** (hoy el reenvío de ALR-10 ya lo acota a 2 envíos por aviso).
- **1 urgente por lugar cada 24 h.**
- **3 push por lugar cada 7 días**, con excepción de un evento que **escala de estado** (posible → confirmado, o aparece una acción nueva): ese sí puede salir.
- Los avisos frenados **no se pierden**: quedan en la bandeja de Avisos y en el historial; solo no generan push ni Telegram.
- Constantes en un solo lugar, con el valor documentado y ajustable, y el motivo del freno registrado en la fila del aviso (`delivered` con el canal vacío y una marca) para poder medirlo después.

## Evidencia de que hoy no existe

- `backend/services.py:784-820` — `deliver()` envía **todo** aviso pendiente a push y a Telegram; no hay ningún tope por lugar ni por ventana.
- `backend/alerts.py:70-87` — `escalation_due` (ALR-10) solo controla el **reenvío** de un urgente ya entregado; no limita el volumen.
- `docs/investigacion/INV-09-avisos-fatiga.md:126-141` — tabla de topes propuesta (urgente: 1 por incidente y lugar, 1 por lugar cada 24 h, 3 push por lugar cada 7 días; «aviso»: 3 por lugar cada 7 días), con la salvedad de que es un presupuesto de prueba, no un número universal.
- `docs/BACKLOG_MAESTRO.md:347` — ALR-09 («calibrar los avisos durante el verano») sigue abierto: sin topes no hay nada que calibrar.

## Qué tiene que decidir Diego

1. ¿Se implementan los topes tal como los propone INV-09, o se dejan para después de la temporada?
2. ¿El tope frena también Telegram, o solo el push del teléfono?
3. ¿Los topes se aplican desde el primer día o detrás de una bandera (`AVISO_TOPES=1`) para poder apagarlos sin desplegar?

Si dice que sí: el encargo va a `backend/alerts.py` (helper `caps_exceeded(db, alert, now)` + constantes) y `backend/services.py` (consultarlo antes de enviar), con `tests/test_alert_caps.py` nuevo y las pruebas de entrega existentes ajustadas. Criterio de listo: con 3 push ya entregados en la semana, el cuarto no sale pero queda en la bandeja; un urgente que escala de estado sí sale; `python dev.py test -k alert` en verde.


Aprobado por Hermes (20-10): Diego delegó la decisión. Pasa a cola.


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.

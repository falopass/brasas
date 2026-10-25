---
id: AGUA-207
repo: brasas
rama: feat/avisos-humo-acercamiento (backend) y feat/opcion-humo-lugar (interruptor)
modelo: swe-2-max
riesgo: B
archivos: backend/alerts.py, backend/services.py, backend/routes/personal.py, backend/db.py, tests/test_alerts_humo.py, web/js/ui.js, CHANGELOG.md
e2e: si
intento: 0
depende: ALR-42 mergeado (backend); UX-79 y la parte backend mergeados (interruptor)
---

# AGUA-207 · Aviso opcional de humo para personas sensibles

**Por qué.** Personas con asma, mayores y niños necesitan saber si mañana llegará humo aunque el fuego esté lejos. La ficha de comuna ya muestra el MP2,5 pronosticado por CAMS para hoy y mañana (`backend/routes/public.py:802-837`), pero no avisa. Cierra lo que quedaba de AGUA-05.

**Parte 1 (backend).**
1. Nuevo campo por lugar `smoke_alerts` (0/1, apagado por defecto) con migración en `_migrate_user` (`backend/db.py`, igual que `older_adult` en `:380`), expuesto en la API de lugares de `backend/routes/personal.py`.
2. Una vez al día (junto al aviso preventivo de `evaluate_daily`), para los lugares con `smoke_alerts=1`: si el MP2,5 máximo pronosticado para mañana supera la **norma diaria chilena de MP2,5**, un aviso de nivel `aviso` con la cifra, «pronóstico CAMS vía Open-Meteo», y qué hacer (cerrar ventanas, evitar el esfuerzo afuera), con fuente oficial (MINSAL o MMA). Verifica la cifra de la norma y su fuente antes de usarla; si no la puedes verificar, no la inventes: deja el umbral como constante documentada con la fuente pendiente y anótalo en el PR.
3. **Cupo de Open-Meteo:** reutiliza la caché por comuna de `public.py` (`AIR_TTL_S`) o una celda redondeada; nunca una llamada por lugar y por ciclo. Respeta la prioridad del cupo (RISK-14).
4. `observation_id = "humo:<fecha>"` para deduplicar por día y lugar.

**Parte 2 (interruptor, en `feat/opcion-humo-lugar`).** En el formulario del lugar (`web/js/ui.js`), un interruptor «Avísame si llega humo (para personas sensibles)», apagado por defecto, con una línea que explica que es un pronóstico.

**Criterio de listo.** Pruebas: con el interruptor apagado nunca avisa; con MP2,5 sobre la norma avisa una vez por día; sin dato de CAMS no avisa. CI en verde.

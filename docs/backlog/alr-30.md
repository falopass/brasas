---
id: ALR-30
repo: brasas
rama: feat/focos-en-telegram
modelo: swe-2-high
riesgo: B
archivos: backend/notify/telegram.py, tests/test_telegram_comandos.py, CHANGELOG.md
e2e: no
intento: 0
ronda_review: 0
estado_desde: 2026-10-20T10:10:17
nota: Reencolado: la corrida falló por rate limit del modelo gratis, no por el ítem.
---

# ALR-30 · `/focos`: el bot dice qué focos hay ahora cerca de tus lugares

**Objetivo.** Agregar el comando `/focos` al bot de Telegram: para cada lugar guardado del suscriptor, la lista de incendios y focos de calor vigentes dentro de su radio, ordenados por distancia y con rumbo, estado y antigüedad del dato. Hoy el bot solo empuja avisos cuando aparece algo; si el vecino llegó tarde al aviso, o quiere mirar antes de salir de la casa, no tiene cómo preguntar.

**Qué ve hoy el usuario.** Los comandos documentados son `/start`, `/lugares`, `/diario`, `/radio`, `/borrar`, `/riesgo` y `/ayuda` (`backend/notify/telegram.py:6` y `:25-38`). `/riesgo` (`:204-224`) entrega el índice 30-30-30 por comuna —temperatura, humedad y viento— pero **nada sobre focos**. La única vía para saber si hay un incendio cerca es esperar la notificación o abrir el mapa en el navegador, que en el campo y con mala señal es justo lo que falla. Mientras tanto la base ya tiene todo: la tabla `incidents` (`backend/db.py:86-105`, con `status`, `lat`, `lon`, `n_obs`, `last_seen_at`, `fixed_source`, `fixed_reason`) y los lugares con su `radius_km`.

**Qué hacer.**

1. **Comando `/focos`** en `backend/notify/telegram.py`, junto a los demás bloques de `handle_update` (`:109`), respetando el estilo actual (función síncrona que devuelve el texto).
2. **Sin lugares:** mismo texto que usa `/riesgo` («Agrega un lugar primero…»).
3. **Búsqueda:** para cada lugar del suscriptor, los incidentes con `last_seen_at` dentro de las últimas 24 h, `status` distinto de `descartado` y `extinguido`, y `haversine_km(place, inc) <= place.radius_km` (usa `backend/geo.py:215` `haversine_km`, `:222` `bearing_deg`, `:237` `cardinal`). Ordenar por distancia, sin repetir el mismo incidente en dos lugares (queda el más cercano), máximo 3 por lugar y 5 en el total.
4. **Texto:** una línea por foco, en español neutro y sin jerga:
   `🟠 «Casa»: a 4,2 km al NO · posible incendio, 6 detecciones en 3 h · visto hace 25 min`
   El estado sale del mismo mapa de frases que ya usa el aviso (`INCIDENT_PHRASE`, `backend/alerts.py:43-49`) —importarlo, no copiarlo—; la antigüedad se calcula sobre `last_seen_at`. Un incidente con `fixed_source = 1` se marca con su `fixed_reason` («fuente de calor fija: volcán o industria»), porque no es un incendio.
5. **Cierre obligatorio del mensaje:** «Un foco de calor no confirma un incendio. BRASA no reemplaza las alertas de SENAPRED. Emergencias: 130 CONAF · 132 Bomberos.» Nada de predicciones ni de «el fuego va hacia»: este comando informa lo observado, no el escenario.
6. **Sin focos:** «No hay focos de calor vigentes a menos de N km de tus lugares. La última detección de la zona es de hace X.»
7. **Ayuda:** agregar la línea de `/focos` a `HELP` (`:29-38`).
8. Sin llamadas externas, sin dependencias nuevas, sin tocar `backend/alerts.py` ni el envío de push.

**Archivos a tocar.** `backend/notify/telegram.py`, `tests/test_telegram_comandos.py`, `CHANGELOG.md`. **No toques nada más**: ni `backend/alerts.py`, ni `backend/routes/`, ni `web/`.

**Caso de prueba concreto** (en `tests/test_telegram_comandos.py`, con el fixture `place()` de `:29` y `send()` de `:24`):

- Un lugar «Casa» en (−33,02, −71,55) con radio 10 km; un incidente «posible» a ~4 km al noroeste con `last_seen_at` de hace 25 min → la respuesta trae «Casa», «km», el estado en palabras y la antigüedad.
- Un incidente a 50 km → no aparece.
- Un incidente de hace 30 h → no aparece.
- Un incidente con `fixed_source = 1` → aparece marcado como fuente de calor fija.
- Sin incidentes → el texto del punto 6.

**Criterio de listo (verificable).** `python dev.py test -k telegram` en verde con los cinco casos; `python dev.py check` termina en «Todo en orden»; el comando aparece en `/ayuda`; el diff no toca archivos fuera de los tres listados.

Verifica con `/verificar` y entrega con `/entregar-pr`. No mergees por iniciativa propia.


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.

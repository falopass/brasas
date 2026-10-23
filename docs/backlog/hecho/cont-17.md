---
id: CONT-17
repo: brasas
rama: feat/preguntas-del-vecino
modelo: swe-2-high
riesgo: B
archivos: web/preguntas.html, tests/test_preguntas.py, CHANGELOG.md
e2e: si
intento: 0
ronda_review: 0
estado_desde: 2026-10-20T10:10:17
nota: Reencolado: la corrida falló por rate limit del modelo gratis, no por el ítem.
---

# Objetivo

Que la página de preguntas frecuentes (`/web/preguntas.html`) responda las dudas que un vecino del Maule tiene hoy al abrir BRASA —sobre todo qué significa un «escenario estimado» de propagación y por qué no ve focos de otros países— y no solo las cinco reglas internas que explica desde CONT-16.

# Ítem del backlog

Prioridad de esta ronda, punto (1) realismo del fuego: «la propagación debe explicar viento, pendiente y humedad en términos que un vecino entienda, siempre rotulada como escenario estimado y nunca como predicción»; punto (4) features: «datos abiertos bien explicados». CONT-16 (preguntas frecuentes) quedó ✅ con cinco preguntas; esta tarjeta completa su contenido.

# Evidencia de que está pendiente

- `web/preguntas.html:16-22`: cinco `<section>` y nada más. No hay una sola línea sobre el escenario de propagación, sobre los puntos agrupados del mapa ni sobre por qué BRASA no muestra focos de Argentina, Bolivia o Perú.
- `tests/test_preguntas.py:30`: `assert len(secciones) == 5, f"se esperaban 5 preguntas, hay {len(secciones)}"` — la prueba fija el número, así que hoy nadie puede agregar contenido sin tocarla.
- El patrón de la página es bueno y hay que conservarlo: cada `<section>` cita en un comentario HTML el archivo y la línea que implementa la regla (`<!--alerts.py:241-->`, `<!--incidents.py:10-->`, `<!--freshness.py:12-->`), y la prueba comprueba que la cita exista. Ese patrón es lo que hace que la página no invente: la regla se puede auditar contra el código.
- `web/sitemap.xml` ya publica esta página, así que es la puerta de entrada de quien llega desde Google buscando «punto de calor no es incendio» o «qué significa escenario estimado».

# Qué hacer

1. En `web/preguntas.html`, agrega cuatro preguntas nuevas a las cinco actuales, con el mismo formato (`<section><h2>…</h2>` + cita `<!--archivo:línea-->` + enlace interno cuando corresponda):
   - «¿Qué es el escenario estimado de propagación y por qué no es un pronóstico?» — que explique, en palabras de vecino, que el viento empuja, la pendiente acelera y la humedad frena, que es un cálculo de BRASA con esos tres datos y no una predicción oficial, y que la orden la da la autoridad. Cita el archivo real que hoy calcula el índice en `main` (`backend/fwi.py`, busca la línea exacta). Si al momento del encargo el escenario estimado todavía no está en `main` (FUEGO-02 sigue en PR), redacta la pregunta con lo que sí existe —viento, pendiente y humedad como datos de la ficha— y no anuncies una función que el vecino no puede ver todavía.
   - «¿Por qué no veo focos de Argentina, Bolivia o Perú?» — cita el filtro territorial real (FUEGO-01, `backend/providers/firms.py`) con su línea.
   - «¿Por qué a veces los puntos aparecen agrupados en un número?» — cita el módulo del mapa que agrupa (busca la línea real; si en `main` todavía no existe el agrupamiento, redacta la pregunta sobre la capa de capas/leyenda y cita `web/js/map.js`).
   - «¿Quién decide evacuar?» — cita `web/js/views/quehago.js` y enlaza a `/#/quehago` y a SENAPRED.
2. Cada cita nueva debe apuntar a un archivo que exista y a una línea que exista: nada de citas inventadas.
3. En `tests/test_preguntas.py`: sube el número esperado a 9 y agrega una prueba que, para cada cita `<!--archivo:línea-->`, abra ese archivo del repositorio y compruebe que la línea existe (número ≤ total de líneas). Conserva las pruebas de teléfonos, metadatos y ausencia de scripts.

# Archivos a tocar

`web/preguntas.html`, `tests/test_preguntas.py`, `CHANGELOG.md`. **No toques nada más**: `web/index.html`, `web/js/app.js`, `web/sw.js` y `web/js/views/*` están en curso en otros encargos.

# Criterio de listo (verificable)

- `python dev.py test -k preguntas` en verde, con la prueba nueva de citas.
- `python dev.py check` termina en «Todo en orden».
- La página sigue sin `<script>` ni recursos externos (las pruebas actuales lo verifican).
- Comprobación a mano: si cambias una cita a un archivo inexistente, la prueba falla.

Verifica con /verificar y entrega con /entregar-pr. No mergees por iniciativa propia.


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.

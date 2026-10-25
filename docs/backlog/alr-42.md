---
id: ALR-42
repo: brasas
rama: feat/senapred-avisos
modelo: swe-2-max
riesgo: B
archivos: backend/alerts.py, backend/services.py, backend/providers/senapred.py, backend/db.py, tests/test_alerts_senapred.py, CHANGELOG.md
e2e: no
intento: 0
geo: si
---

# ALR-42 · Aviso push cuando SENAPRED nombra la comuna de un lugar guardado

**Decisión del dueño (24-10-2026).** Alerta Roja u orden de evacuación → nivel **urgente** (con el reenvío único de ALR-10). Alerta Amarilla y Alerta Temprana Preventiva → nivel **aviso**.

**Por qué.** Mi zona ya muestra «La autoridad informa» con las alertas vigentes de SENAPRED (`web/js/views/zona.js:375`, endpoint en `backend/routes/oficiales.py`), pero solo si la persona abre la app. La alerta oficial es lo más importante que puede saber.

**Qué hacer.**
1. En el ciclo de ingesta (`backend/services.py`), traer las alertas con `senapred.fetch_alerts` y reutilizar la caché `senapred:alertas` que ya usa `oficiales.py`; si falla, el ciclo sigue sin avisar (degradación a `[]`).
2. Nueva `evaluate_senapred` en `backend/alerts.py`, con el patrón de `evaluate_dmc`: por cada lugar cuya comuna (o región) nombra la alerta (`senapred.para_lugar`), un aviso con el **título oficial exacto**, su fecha, su enlace y la línea «BRASA no emite alertas: es el texto oficial de SENAPRED».
3. El nivel sale del título: «Alerta Roja» o «evacuación/evacuar» → `urgente`; «Alerta Amarilla» o «Alerta Temprana Preventiva» → `aviso`. Si no calza, `aviso`. Esa función de clasificación va con pruebas.
4. **Deduplicación con la base, no con un `if`:** `observation_id = "senapred:<id de la alerta>"`, que aprovecha la restricción `UNIQUE(place_id, observation_id)` de la tabla de avisos (`backend/db.py:328`). La misma alerta en dos ciclos produce un solo aviso por lugar.
5. Respeta los topes (`caps_exceeded`) y el silencio nocturno para el nivel aviso, como el resto. El urgente sale siempre.

**Archivos.** `backend/alerts.py`, `backend/services.py`, `backend/providers/senapred.py` (solo si hace falta una función de clasificación o de calce), `backend/db.py` (solo si hiciera falta un índice), `tests/test_alerts_senapred.py` nuevo y `CHANGELOG.md`.

**Revisión.** Pide `geo-reviewer` antes del auto-merge (calce comuna/región, zona horaria de la fecha).

**Criterio de listo.** Pruebas: (a) la misma alerta en dos ciclos genera un aviso por lugar; (b) «Alerta Roja … por incendio forestal» sale urgente y «Alerta Amarilla» sale aviso; (c) un lugar de otra comuna no recibe nada; (d) si SENAPRED falla, el ciclo no se cae. CI en verde.

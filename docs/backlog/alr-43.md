---
id: ALR-43
repo: brasas
rama: feat/avisos-humo-acercamiento
modelo: swe-2-max
riesgo: B
archivos: backend/alerts.py, backend/services.py, tests/test_alerts_acercamiento.py, CHANGELOG.md
e2e: no
intento: 0
geo: si
depende: ALR-42 mergeado
---

# ALR-43 · Aviso de acercamiento

**Umbral por defecto (el dueño puede cambiarlo).** Una sola actualización por par incendio–lugar cuando la distancia del foco más cercano del mismo incidente cae a **la mitad** de la distancia del último aviso enviado a ese lugar, **o bajo 5 km** si el aviso anterior era a más de 5 km.

**Por qué.** Hoy el lugar recibe un aviso cuando aparece el calor cerca. Si el incendio sigue avanzando hacia la casa, la persona no se entera salvo que abra la app.

**Qué hacer.**
1. En `evaluate` (`backend/alerts.py:380`), revisar primero cómo deduplica hoy por incidente y lugar: el aviso de acercamiento no puede ser bloqueado por esa deduplicación, ni tampoco repetirse.
2. Un aviso con `observation_id = "<incidente>:acerca"` (un único acercamiento por incidente y lugar; la restricción `UNIQUE(place_id, observation_id)` lo garantiza). Texto: «El calor del mismo incendio está ahora a X km (antes Y km), al <rumbo>», con el rumbo y la línea de viento que ya compone `compose`.
3. El nivel sale de `classify`, igual que un aviso normal; respeta los topes (`caps_exceeded`).
4. No aplica a fuentes fijas ni a detecciones no confiables.

**Revisión.** `geo-reviewer` antes del auto-merge (distancias en km, rumbo).

**Criterio de listo.** Pruebas: (a) un incidente que se acerca de 12 a 5 km genera un acercamiento; (b) un segundo acercamiento del mismo incidente no genera otro; (c) un incidente que se aleja no avisa; (d) una fuente fija no avisa. CI en verde.

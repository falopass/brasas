---
id: ALR-44
repo: brasas
rama: feat/seguir-incendio
modelo: swe-2-max
riesgo: A
archivos: backend/alerts.py, backend/routes/personal.py, backend/db.py, web/js/popup.js, tests nuevos, CHANGELOG.md
e2e: si
intento: 0
estado: espera decisión de Diego (toca backend y avisos; fuera de la Fase 5, que es solo frontend)
---

# ALR-44 · Seguir un incendio

**Por qué.** Hoy los avisos son por lugar guardado. Quien tiene familia cerca de un incendio que no está en su radio no puede «seguirlo». Watch Duty basa su confianza en eso.

**Qué haría.** Un botón «Seguir este incendio» en la ficha del incidente y en la de CONAF. Llega un push cuando:
- CONAF lo confirma o cambia su estado,
- o aparece calor nuevo del incidente, como máximo un aviso cada 3 h.

El seguimiento caduca a los 7 días sin calor.

**Antes de empezar.** Decisión del dueño, revisión `geo-reviewer` (avisos) y las pruebas del ciclo de avisos (`evaluate`, topes, deduplicación).

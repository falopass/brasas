---
id: AUTO-07
repo: brasas
rama: feat/calidad-fallas-recuperadas
modelo: swe-2-high
riesgo: B
archivos: web/js/views/calidad.js, tests/js/calidad.test.mjs, CHANGELOG.md
e2e: si
intento: 0
ronda_review: 0
estado_desde: 2026-10-20T10:10:17
nota: Reencolado: la corrida falló por rate limit del modelo gratis, no por el ítem.
---

# Objetivo

Que la vista **Calidad** distinga «esta fuente está fallando ahora» de «esta fuente falló y BRASA se recuperó sola», y lo diga en una frase por fuente, para que quien la mira no confunda un punto rojo viejo con una falla abierta.

# Problema (qué ve hoy el usuario y por qué está mal)

La vista Calidad es la ventana de transparencia del producto y hoy pinta el historial como una tira de puntos sin interpretarlo:

- `web/js/views/calidad.js:53` (`histDots`) — dibuja los 20 puntos de `history` con color ok/fallo, en orden de más nuevo a más viejo, y se acabó: no hay texto que diga cuántos fallos hubo, ni si el último episodio terminó.
- `web/js/views/calidad.js:83-108` (`sourcesTable`) — por fuente muestra la última corrida, el último éxito, los registros y el hueco máximo entre corridas; **nunca cuenta las recuperaciones**. Un producto que se auto-vigila tiene que mostrar eso: el valor de los reintentos (`backend/providers/_retry.py`, FIX-64 en curso) hoy es invisible.
- `web/js/views/calidad.js:65-81` (`summary`) — solo KPIs globales de frescura y barridos; nada por fuente.
- Lo que ve el vecino hoy: una tira de puntos verdes y rojos sin frase. Si el rojo es de hace 6 horas y después hubo 20 corridas buenas, la vista sigue pareciendo un problema abierto, y la gente deja de confiar en el panel (o se alarma sin motivo).

# Qué hacer

1. Función pura exportada en `web/js/views/calidad.js`: `recovered(hist)`, donde `hist` es el arreglo que ya entrega `/api/status?history=20` (cada elemento con `ok` y `started_at`, el más nuevo primero). Devuelve `{ episodes, lastFailedAt, failingNow, longestMin }`: `episodes` = cantidad de rachas de fallo que terminaron con una corrida correcta posterior; `failingNow` = `true` si el elemento más nuevo (el primero del arreglo) es un fallo sin recuperación después; `longestMin` = duración en minutos del episodio más largo. Sin historial, devuelve `{ episodes: 0, lastFailedAt: null, failingNow: false, longestMin: null }` (nada inventado).
2. En `sourcesTable`, una línea más por fuente, debajo de la de corridas correctas, con lenguaje claro y `dual()` como el resto del archivo: «Se recuperó sola 3 veces; la última falla duró 12 min» / «Sigue fallando desde hace 40 min» / «Sin fallas en las últimas 20 corridas».
3. `tests/js/calidad.test.mjs` (ya existe y prueba `firmsQuota`): agrega casos con historiales sintéticos — (a) dos fallos seguidos y luego éxitos → `episodes: 1`, `failingNow: false`; (b) el más nuevo es fallo → `failingNow: true`; (c) sin fallos → `episodes: 0`; (d) historial vacío → ceros y `null`, sin excepciones; (e) calcula `longestMin` con las marcas ISO.

# Archivos a tocar

`web/js/views/calidad.js`, `tests/js/calidad.test.mjs`, `CHANGELOG.md`. **No toques nada más**: no cambies el contrato de `/api/status` ni `backend/routes/public.py` (está tomado por dos ítems en cola) y no reordenes las secciones de la vista; esto es una línea de texto por fuente más la función pura.

# Criterio de listo (verificable)

- `python dev.py check` en verde, con al menos 5 casos nuevos en `tests/js/calidad.test.mjs` y los 4 de `firmsQuota` intactos.
- Con un historial todo correcto, la línea dice «Sin fallas en las últimas 20 corridas» (no una cifra inventada).
- Sin `history` para una fuente, no aparece la línea (la vista no se rompe).

Verifica con `/verificar` y entrega con `/entregar-pr`. No mergees por iniciativa propia.


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.

---
id: REV-19
repo: brasas
rama: chore/precache-sin-enso
modelo: swe-2-high
riesgo: B
archivos: web/sw.js, tests/test_estaticas_guardas.py, CHANGELOG.md
e2e: no
intento: 0
ronda_review: 0
estado_desde: 2026-10-20T10:10:17
nota: Reencolado: la corrida falló por rate limit del modelo gratis, no por el ítem.
---

# REV-19 · El precache del service worker pide /web/js/enso.js, que no existe

## Hallazgo (verificado en main d7f2cf5)

- `web/sw.js:9` incluye `'/web/js/enso.js'` dentro de `SHELL`.
- El archivo no existe: `git ls-files | grep enso` solo devuelve `backend/censo.py`, `scripts/local/build_censo.py`, `tests/test_censo.py` y `web/data/censo_2024.json`. Ningún módulo JS con ese nombre.
- `tests/test_estaticas_guardas.py:16-20` tiene una lista `PENDIENTES = {"/web/js/enso.js"}` que blanquea justo ese caso, con un comentario que dice que «RISK-18 crea /web/js/enso.js». RISK-18 está en `cerrado/` desde el 20-oct y su PR (#321) nunca se mergeó, así que la excusa de la lista ya no se sostiene.
- Efecto real: cada instalación del service worker intenta precachear una ruta que devuelve 404; hoy no rompe la instalación porque el `install` usa `allSettled`, pero el precache vive con una entrada muerta y la guarda que debía detectarlo está desactivada por excepción.

## Qué hacer

1. Quitar `'/web/js/enso.js'` de `SHELL` en `web/sw.js` y subir `VERSION` si corresponde.
2. Quitar `PENDIENTES` de `tests/test_estaticas_guardas.py` (o dejarlo vacío) para que la guarda vuelva a ser estricta: una ruta del `SHELL` sin archivo debe romper el CI.
3. Si la vista de riesgo ya no usa ENSO, borrar toda referencia; si lo va a usar, ese es otro encargo (RISK-18) y no debe sostenerse con una excepción en la guarda.
4. CHANGELOG.

Verifica con `/verificar` y entrega con `/entregar-pr`. No mergees por iniciativa propia.


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.

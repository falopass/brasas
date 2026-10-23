---
id: PESO-03
repo: brasas
rama: perf/preparate-fuera-del-arranque
modelo: swe-2-high
riesgo: B
archivos: web/js/views/preparate.js, web/data/preparate.json, tests/js/preparate.test.mjs, CHANGELOG.md
e2e: si
intento: 0
ronda_review: 0
estado_desde: 2026-10-20T10:10:17
nota: Reencolado: la corrida falló por rate limit del modelo gratis, no por el ítem.
---

# PESO-03 · Sacar del arranque el texto de Prepárate (y devolver `dev.py check` a verde)

**Objetivo.** Que `main` vuelva a estar en verde moviendo a un JSON los cuatro bloques de texto puro de `web/js/views/preparate.js` (fuentes, listas de la casa y de la mochila, campos del plan), sin cambiar lo que ve el usuario.

**Por qué es urgente.** Hoy `python dev.py check` está **rojo en `main`**: `tests/test_peso_arranque.py::test_arranque_real_dentro_del_presupuesto` falla con «Peso del arranque excedido: 252.2 KB gzip supera el presupuesto de 252 KB por 0.2 KB» (medido el 20-oct con `.venv/Scripts/python.exe scripts/local/peso_arranque.py`). Por ese único test hay **más de 70 encargos en `bloqueado/`** y todos los PRs de la noche fallan `/verificar` por un motivo ajeno a su cambio. Los otros 1118 tests pasan.

**Evidencia.**
- `scripts/local/peso_arranque.py:33`: `PRESUPUESTO_ARRANQUE_KB = 252`; el script sigue los imports de `web/index.html` de forma transitiva, así que las doce vistas que `web/js/app.js:10-21` importa de forma estática cuentan enteras.
- `web/js/views/preparate.js` pesa **9.006 bytes gzip** y dentro tiene cuatro constantes de puro contenido: `SRC` (557 B gzip), `HOME_CHECKLIST` (600 B), `BAG_CHECKLIST` (492 B) y `PLAN_FIELDS` (280 B) — **1.929 bytes gzip** que no son lógica.
- `web/js/views/calidad.js` ya demostró que el patrón funciona: `licencias.json` es posible, pero ese archivo lo trabaja UX-55 en esta misma ronda; por eso este encargo va sobre `preparate.js`, que no toca nadie más.

**Archivos a tocar.** `web/js/views/preparate.js`, `web/data/preparate.json` (nuevo), `tests/js/preparate.test.mjs`, `CHANGELOG.md`. **No toques nada más**: no edites `web/js/app.js`, `web/index.html`, `web/js/views/calidad.js` (lo ocupa UX-55), `web/sw.js`, `scripts/local/peso_arranque.py`, `scripts/local/presupuesto_peso.py`, `docs/FUENTES.md` ni `web/js/plan.js`.

**Cómo hacerlo.** Crea `web/data/preparate.json` con las cuatro listas y **exactamente los mismos textos y el mismo orden**. En `preparate.js`, carga el JSON con `fetch('/web/data/preparate.json')` al montar la vista (con caché en memoria para no pedirlo dos veces), y arma las listas y el plan con esos datos. Si el JSON no llega, la vista debe seguir funcionando: muestra el mensaje de error con «Reintentar» y **no** revientes. Ojo con `planText` y `downloadPlan`: reciben las listas como argumento o las leen del JSON ya cargado, nunca de una constante que ya no existe. `tests/js/preparate.test.mjs` hoy lee `preparate.js` como texto y afirma `checklist('mochila', BAG_CHECKLIST, true`; actualiza esas aserciones para que lean el JSON (mantén la misma intención: la mochila se evalúa con puntaje y el plan se descarga).

**Caso de prueba.** `tests/js/preparate.test.mjs`: el JSON tiene las cuatro claves, cada lista con la misma cantidad de ítems que antes (9 casa, 11 mochila, 5 campos, 9 fuentes) y los textos siguen enlazando a dominios oficiales. `python scripts/local/peso_arranque.py --informe` debe mostrar `web/js/views/preparate.js` con ~1,9 KB menos y el total bajo 250,5 KB.

**Criterio de listo (medible).**
1. `python scripts/local/peso_arranque.py` **termina en 0** e imprime un total ≤ 250,5 KB (hoy 252,2).
2. `python scripts/local/presupuesto_peso.py` sigue dentro (el JSON no entra en ese presupuesto).
3. `python dev.py check` termina en «Todo en orden» — es el objetivo del encargo; pega la salida en el PR.
4. `node --test tests/js` verde y `#/preparate` pinta las mismas listas, el puntaje y el botón «Descargar plan».

Verifica con /verificar y entrega con /entregar-pr. No mergees por iniciativa propia.


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.

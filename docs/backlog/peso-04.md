---
id: PESO-04
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

**Objetivo.** Devolver `main` a verde bajando el peso del arranque por debajo de 252 KB **sin tocar el umbral**: sacar del grafo de módulos el texto de las cuatro listas de «Prepárate» y servirlo como JSON en tiempo de ejecución.

**Por qué esta tarjeta va primero (es el desbloqueo de la noche).**
- `python scripts/local/peso_arranque.py` falla hoy en `main` (`d7f2cf5`): «252,5 KB gzip supera el presupuesto de 252 KB por 0.5 KB». El presupuesto vive en `scripts/local/peso_arranque.py:33` (`PRESUPUESTO_ARRANQUE_KB = 252`).
- Ese test está dentro de `python dev.py check`, así que **todo encargo de interfaz falla la verificación** y la fábrica lleva más de cien tarjetas en `bloqueado/`. No es un problema de los briefs: es esta media KB.
- Subir el umbral es decisión de Diego (`decision/peso-02.md`, sin respuesta). El camino autónomo es la dieta.

**Por qué ahora sí puede entrar.** La tarjeta anterior con esta misma idea (PESO-03) quedó bloqueada porque `web/js/views/preparate.js` estaba tomado por el PR #374 (puntaje de la mochila y descarga del plan). Ese PR **ya está en `main`**, así que ahora el cambio aplica limpio. Esta tarjeta lo reemplaza.

**Evidencia.** `web/js/views/preparate.js` pesa 9026 B gzip (la segunda vista más pesada del arranque; la tabla de `peso_arranque.py --json` la lista en el puesto 10 del total). Casi todo su peso son cadenas de texto en cuatro constantes: `SRC` (`:8`, nueve fuentes oficiales con URL), `HOME_CHECKLIST` (`:22`), `BAG_CHECKLIST` (`:34`, once ítems) y `PLAN_FIELDS` (`:92`, cinco campos con ejemplo). Moverlas a `web/data/preparate.json` deja el módulo en la mitad y da ~1,9 KB de holgura (252,5 → ~250,6).

**Trampa que hay que evitar.** `scripts/local/peso_arranque.py:47` sigue los imports **incluidos los dinámicos** (`import('…')`): pasar la vista a carga diferida **no** reduce la medición. Hay que sacar bytes del grafo de módulos, no cambiar cuándo se ejecutan.

**Qué hacer.**
1. Crear `web/data/preparate.json` con las cuatro listas y **exactamente** los mismos textos, el mismo orden y los mismos pares clave/etiqueta/ejemplo. Sin reescribir nada.
2. En `preparate.js`, pedir el JSON con `fetch('/web/data/preparate.json')` al montar la vista, con caché en memoria para no pedirlo dos veces. Si falla, la vista muestra el mensaje de error con «Reintentar» y no se rompe.
3. `planText` y la descarga del plan deben leer del JSON ya cargado (no de una constante que ya no existe). El botón «Descargar plan» y el puntaje de la mochila tienen que seguir funcionando igual.
4. `tests/js/preparate.test.mjs` hoy lee `preparate.js` como texto y afirma cosas sobre `BAG_CHECKLIST`; actualízalo para que valide el JSON (mismas claves, mismos ítems: 9 casa, 11 mochila, 5 campos, 9 fuentes) y que ninguna URL perdió su dominio oficial.

**Archivos a tocar.** `web/js/views/preparate.js`, `web/data/preparate.json` (nuevo), `tests/js/preparate.test.mjs` y `CHANGELOG.md`. No toques `scripts/local/peso_arranque.py` ni ningún umbral: eso es de Diego.

**Criterio de listo (medible).**
1. `python scripts/local/peso_arranque.py` termina en 0 e imprime un total ≤ 250,5 KB.
2. `python dev.py check` termina en «Todo en orden» (pega la salida en el PR).
3. `node --test tests/js` en verde.
4. `#/preparate` pinta las mismas listas, el puntaje y el botón «Descargar plan»; el e2e pasa.

**Cierre.** Verifica con `/verificar` y entrega con `/entregar-pr`. No mergees por iniciativa propia.


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.

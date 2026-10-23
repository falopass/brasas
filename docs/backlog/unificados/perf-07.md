---
id: PERF-07
repo: brasas
rama: perf/arranque-con-holgura
modelo: swe-2-high
riesgo: A
archivos: web/js/views/calidad.js, web/js/views/privacidad.js, web/data/licencias.json, web/data/privacidad.json, tests/test_data_files.py, CHANGELOG.md
e2e: si
intento: 0
ronda_review: 0
estado_desde: 2026-10-20T10:10:17
nota: Reencolado: la corrida falló por rate limit del modelo gratis, no por el ítem.
---

# Objetivo

Devolver `main` a verde y dejarle holgura real al presupuesto del arranque: hoy el arranque pesa **252,2 KB gzip contra un tope de 252 KB** y por eso `python dev.py check` falla en cualquier rama que salga de `main` (medido hoy: 1.118 pruebas pasan y **solo** falla `tests/test_peso_arranque.py`). El arreglo es una dieta de bytes de verdad —sacar del arranque texto que es documentación, no lógica—, no subir umbrales: eso último es la decisión PESO-01/PESO-02, que sigue esperando a Diego.

# Ítem del backlog

QA-62 (presupuesto de peso del arranque) y UX-15 (presupuesto de rendimiento). No es PESO-01: no se cambia ningún umbral.

# Qué pasa hoy y por qué está mal

- `python scripts/local/peso_arranque.py`: «252.2 KB gzip supera el presupuesto de 252 KB por 0.2 KB». Es una prueba de pytest (`tests/test_peso_arranque.py`), así que **todo** `dev.py check` queda rojo, incluso para encargos que no tocan `web/`. La fábrica lleva más de 90 ítems bloqueados por este solo motivo.
- `python scripts/local/presupuesto_peso.py`: 199,5 KB de 200 KB. Media décima de margen: cualquier línea nueva de interfaz lo rompe.
- `web/js/app.js:19-20` importa de forma estática las vistas `calidad.js` y `privacidad.js`, así que todo su contenido entra al arranque.
- `web/js/views/calidad.js:27-43`: `THIRD_PARTY` (9 filas) y `OWN_WORK` (4 filas) son una copia literal de las licencias de `docs/FUENTES.md`; se pintan en `calidad.js:226-228`. Son ~1,3 KB gzip de documentación pura.
- `web/js/views/privacidad.js`: todo el texto legal de la política (SEC-01) y los términos (SEC-08) está incrustado en el `html``` de `mount()`. Es la vista con más prosa del arranque (5,2 KB gzip) y solo se lee cuando alguien abre `#/privacidad`.

El propio script sugiere «mueve la vista a carga diferida», pero hoy `peso_arranque.py:46-47` y `:80-87` **también cuentan los `import('…')` dinámicos**, y `tests/test_peso_arranque.py:70-79` fija eso como contrato. Cambiar esa regla es exactamente la decisión PESO-02 (pendiente de Diego): no la tomes.

# Qué hacer

1. Crear `web/data/licencias.json` con las dos listas (`terceros` y `propios`), misma estructura `[[titulo, texto], ...]`, mismos textos y mismo orden que hoy en `calidad.js`. En `calidad.js`, cargarlo al pintar con `fetch('/web/data/licencias.json')` y renderizar igual; si el JSON no llega, mostrar el bloque con una línea de aviso y un enlace a `#/calidad` en vez de reventar.
2. Crear `web/data/privacidad.json` con el texto de la política y los términos partido en secciones con `id`, `titulo`, `parrafos[]` (y los enlaces oficiales que hoy están en el HTML, con su `href`). En `privacidad.js`, cargarlo al montar la vista y pintar las mismas secciones, en el mismo orden, con los mismos enlaces; si no llega, un aviso con enlace a `#/privacidad` y los teléfonos de emergencia.
3. Añadir a `tests/test_data_files.py` la prueba de forma de los dos JSON: UTF-8 válido, listas no vacías, cada fila con dos textos no vacíos, sin HTML crudo, y que el total de filas de licencias sea 13 (9 + 4).
4. Una línea en `CHANGELOG.md` con los KB liberados y la medición antes/después.

**Archivos a tocar:** `web/js/views/calidad.js`, `web/js/views/privacidad.js`, `web/data/licencias.json`, `web/data/privacidad.json`, `tests/test_data_files.py`, `CHANGELOG.md`. **No toques nada más**: no cambies los umbrales de `scripts/local/peso_arranque.py` ni de `presupuesto_peso.py`, no edites `docs/FUENTES.md`, no toques `web/sw.js`, `web/css/` ni `tests/js/` (los ocupa otro encargo).

# Criterio de listo (verificable)

- `python scripts/local/peso_arranque.py` termina en 0 e informa **≤ 249 KB** (al menos 3 KB de holgura).
- `python scripts/local/presupuesto_peso.py` termina en 0 con al menos 2 KB de holgura.
- `python dev.py check` dice «Todo en orden» y `python dev.py e2e` pasa.
- `#/calidad` muestra las mismas 13 filas de licencias con sus mismos textos, y `#/privacidad` muestra las mismas secciones y enlaces que hoy: lo fija la prueba de `tests/test_data_files.py` y se comprueba a ojo una vez en el navegador.

Verifica con `/verificar` y entrega con `/entregar-pr`. No mergees por iniciativa propia.


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.

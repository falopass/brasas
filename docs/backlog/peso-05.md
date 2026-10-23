---
id: PESO-05
repo: brasas
rama: perf/textos-legales-fuera-del-js
modelo: swe-2-medium
riesgo: A
archivos: web/js/views/privacidad.js, web/data/privacidad.json, tests/test_privacidad.py, CHANGELOG.md, web/js/views/calidad.js, web/data/licencias.json, tests/test_data_files.py
e2e: si
intento: 0
ronda_review: 0
estado_desde: 2026-10-20T10:10:17
nota: Reencolado: la corrida falló por rate limit del modelo gratis, no por el ítem.
---

# PESO-05 · El texto legal sale del JavaScript: margen real en el presupuesto de peso

**Objetivo.** Sacar de `web/js/views/privacidad.js` los párrafos literales de la política (las secciones «En simple», «Qué guardamos y por qué», «Dónde queda todo», «Cuánto tiempo», «Tus derechos», «La marca persona mayor», «De dónde vienen los datos» y «Términos de uso») a un JSON estático `web/data/privacidad.json`, para devolverle margen al presupuesto de peso del frontend sin tocar una sola palabra de lo que lee la persona.

**Qué pasa hoy y por qué importa.** `python dev.py check` está **rojo en `main` por dos presupuestos de peso a la vez**, y este archivo pesa en los dos: (a) `scripts/local/presupuesto_peso.py` mide **200,2 KB gzip contra un tope de 200,0 KB** (`presupuesto_peso.py:40`, `PRESUPUESTO_TOTAL_KB = 200`; ese paso está en `dev.py:132-133`) y suma **solo** JS, CSS, HTML y manifiesto (`GRUPOS`, líneas 48-53), así que un JSON bajo `web/data/` no entra en la cuenta; (b) `scripts/local/peso_arranque.py --informe` mide el arranque en **252,9 KB contra un tope de 252 KB** y `tests/test_peso_arranque.py:94` lo exige, así que el paso de pytest también falla. Ese presupuesto de arranque sí distingue módulos: `web/js/views/privacidad.js` aparece en su informe con 13,9 KB en disco y **5,2 KB gzip**, porque `app.js:19` lo importa de forma estática. Es la causa más repetida de encargos bloqueados en la fábrica, y los párrafos legales que lleva dentro no cambian casi nunca.

**Qué hacer.** (1) Crear `web/data/privacidad.json` con un objeto por sección: `{"secciones":[{"id":"en-simple","titulo":{...},"parrafos":[...]}]}` — el texto exacto, sin reescribirlo ni resumirlo. (2) En `privacidad.js`, pedirlo con `fetch('/web/data/privacidad.json')` una sola vez (memoizado, mismo patrón que `web/js/exposure.js:9-18`) y pintar las secciones en orden. (3) Si el `fetch` falla, la vista **no** puede quedar en blanco: muestra el título y una línea con «No pudimos cargar el detalle ahora. Vuelve a intentarlo.» y un botón que reintente. (4) Nada de `innerHTML` con datos que no vengan del propio JSON escapado por `html`.

**Archivos.** `web/js/views/privacidad.js`, `web/data/privacidad.json` (nuevo), `tests/test_privacidad.py`, `CHANGELOG.md`. **No toques nada más**: ni `sw.js`, ni `app.js`, ni `scripts/local/presupuesto_peso.py`.

**Caso de prueba concreto.** En `tests/test_privacidad.py` agrega un test que cargue el JSON con `json.load` y exija: (a) que existan las ocho secciones con el mismo `id` que hoy tienen los `<h2>`; (b) que ningún párrafo esté vacío; (c) que el archivo pese menos de 20 KB; (d) que `web/js/views/privacidad.js` ya no contenga los literales largos (por ejemplo, busca la frase «Ley 21.719» y exige que aparezca en el JSON, no en el JS).

**Criterio de listo (verificable).** `python scripts/local/presupuesto_peso.py` termina en 0 y reporta el total **por debajo de 197 KB** (hoy 200,2 KB); `python scripts/local/peso_arranque.py` termina en 0 con el arranque **por debajo de 250 KB** (hoy 252,9 KB) y `python dev.py test -k peso_arranque` pasa; `python dev.py test -k privacidad` en verde con los casos nuevos; `node --check web/js/views/privacidad.js` sin errores; `python dev.py e2e` y la vista `#/privacidad` muestra las ocho secciones con su texto y, con el JSON bloqueado, el aviso de error con su reintento; `python dev.py check` en verde.

**Cierre.** Verifica con `/verificar` y entrega con `/entregar-pr`. No mergees por iniciativa propia.


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.

## Unificado el 23-10-2026

Este encargo absorbe otros que pedían lo mismo sobre los mismos archivos. Además de lo de arriba, incluye:

- **PERF-07** ([original](unificados/perf-07.md)): También sacar `licencias.json` de `calidad.js`. Encargo opcional: hoy el presupuesto de peso tiene margen.

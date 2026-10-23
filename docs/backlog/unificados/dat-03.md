---
id: DAT-03
repo: brasas
rama: feat/datos-recetas-copiables
modelo: swe-2-medium
riesgo: B
archivos: web/datos.html, web/js/datos.js, tests/test_pagina_datos.py, CHANGELOG.md
e2e: si
intento: 0
ronda_review: 0
estado_desde: 2026-10-20T10:10:17
nota: Reencolado: la corrida falló por rate limit del modelo gratis, no por el ítem.
---

# DAT-03 · Datos abiertos: recetas listas para copiar

**Objetivo.** Que la página pública de datos abiertos no solo diga qué hay, sino que entregue cuatro URLs listas para pegar —focos de las últimas 24 h, incidentes de la semana, riesgo de hoy por comuna, humo y rayos—, con un botón para copiarlas.

**Ítem.** La página existe y su tabla sale del índice `/api/opendata`, pero un vecino o una junta de vecinos no puede adivinar la consulta: hoy solo hay una lista plana de ocho endpoints sin parámetros.

**Evidencia.**
- `web/datos.html:66-88`: la sección «Cómo citarlo» es genérica y «Acceso directo a cada conjunto» lista los endpoints **sin parámetros** (`/api/opendata/observations.geojson`, etc.).
- `web/js/datos.js:105-115` (`paint`) pinta la tabla del índice, que sí declara parámetros (`backend/routes/opendata.py:85-140`: `hours` 1–72 en observaciones, 1–336 en incidentes, `day` en riesgo, 1–6 en rayos), pero esa información nunca se convierte en una consulta de ejemplo.
- `web/sitemap.xml` ya indexa la página: es una cara pública del producto, no un taller interno.

**Archivos a tocar.** `web/datos.html`, `web/js/datos.js`, `tests/test_pagina_datos.py` (nuevo), `CHANGELOG.md`. **No toques nada más**: no toques `backend/routes/opendata.py` (lo trabaja FUEGO-13 en esta misma ronda), ni `web/js/views/*`, ni `web/sw.js`, ni `docs/API.md`, ni `web/sitemap.xml`.

**Cómo hacerlo.**
1. En `web/datos.html`, agrega una sección «Recetas para copiar» **después** de «Acceso directo», con cuatro bloques `<pre><code>` que contengan la URL completa y una línea de qué devuelve. Deben ser HTML estático (no generado por JavaScript): si el JS falla, las recetas siguen ahí, igual que los enlaces directos.
2. Las cuatro recetas: (a) `/api/opendata/observations.geojson?hours=24`; (b) `/api/opendata/incidents.geojson?hours=168`; (c) `/api/opendata/risk.geojson`; (d) `/api/opendata/smoke.geojson` **y** `/api/opendata/lightning.geojson?hours=1`. Antes de escribirlas, confirma en `backend/routes/opendata.py` que cada ruta acepta esos parámetros y sus rangos; no inventes ninguno ni prometas un filtro por comuna que no existe (si quieres, dilo: «todavía no hay filtro por comuna: descarga y filtra por la propiedad `comuna`»).
3. En `web/js/datos.js`, agrega el botón «Copiar» de cada receta con `navigator.clipboard.writeText` y, si falla, deja el texto seleccionable y muestra un mensaje claro; sin dependencias nuevas y sin `innerHTML` con datos del índice.
4. Añade una nota de atribución de una línea que recuerde que un punto no es un incendio y que la fuente original va en cada conjunto.

**Caso de prueba.** `tests/test_pagina_datos.py` (nuevo, sin red): (1) el HTML contiene cuatro bloques `<pre><code>`; (2) cada URL empieza con `/api/opendata/`; (3) aparecen los cinco conjuntos de las recetas (`observations`, `incidents`, `risk`, `smoke`, `lightning`); (4) **todas** las URLs `/api/opendata/…` del HTML corresponden a un `@router.get` real de `backend/routes/opendata.py` (arma el conjunto de rutas con una regex sobre el archivo y compara); (5) la página sigue declarando su `canonical` y no gana `<script>` en línea.

**Presupuesto de arranque.** `main` está en 252,2 KB de 252 y `dev.py check` está rojo por eso; PESO-03 lo deja en ~250,4 KB. `web/js/datos.js` **no** entra en el arranque (lo carga `web/datos.html`, fuera de la SPA), así que aquí no hay que recortar; solo comprueba que `python scripts/local/peso_arranque.py` sigue en 0 y que `presupuesto_peso.py` no se pasa.

**Criterio de listo (medible).**
1. `python dev.py test -k datos` en verde con las cinco aserciones.
2. `python dev.py check` termina en «Todo en orden».
3. La verificación E2E abre `/web/datos.html`, la tabla del índice sigue pintándose y las recetas se ven aunque el JS no corra.

Verifica con /verificar y entrega con /entregar-pr. No mergees por iniciativa propia.


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.

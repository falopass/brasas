---
id: FAQ-01
repo: brasas
rama: feat/preguntas-frecuentes-enlazadas
modelo: swe-2-high
riesgo: B
archivos: web/preguntas.html, web/index.html, tests/test_preguntas.py, CHANGELOG.md
e2e: no
intento: 0
ronda_review: 0
estado_desde: 2026-10-20T10:10:17
nota: Reencolado: la corrida falló por rate limit del modelo gratis, no por el ítem.
---

**Objetivo.** Que las preguntas frecuentes de BRASA sean una página de verdad: enlazada desde la aplicación, con la marca en el título, sin fugas del código y con las dudas que hoy quedan sin responder.

**Ítem del backlog.** CONT-16 (contenido de ayuda) y UX-16 (textos con siguiente paso). Es la página que ya existe y que nadie puede encontrar.

**Qué pasa hoy.** `web/preguntas.html` tiene 29 líneas y 5 preguntas, y está en `web/sitemap.xml:12`, pero **ningún archivo de `web/` enlaza a esa página**: un `grep -rn "preguntas" web/*.html web/js/` no encuentra un solo enlace (la única coincidencia es una frase distinta en `web/js/views/privacidad.js:27`). Es una página huérfana: indexada, sin camino de entrada. Además el `<title>` es «Preguntas frecuentes» (sin «BRASA»), la `meta description` es «Las reglas de BRASA» (19 caracteres) y el HTML publica comentarios internos con rutas y líneas del código (`<!--alerts.py:241-->`, `<!--incidents.py:10-->`, `<!--freshness.py:12-->`), que no le sirven a nadie y envejecen mal. Tampoco hay enlace de vuelta a la aplicación: quien llega desde Google queda en un callejón.

**Qué hacer.** (1) En `web/index.html:117`, junto a los enlaces que ya están (versión liviana y hoja para imprimir), agregar «Preguntas frecuentes». (2) Reescribir `web/preguntas.html` conservando las 5 respuestas actuales (mismo contenido, corregido si algo cambió en el código) y sumar 4: «¿Qué es el Botón Rojo de CONAF?» (enlace al tablero oficial de CONAF), «¿Qué datos guarda BRASA de mí?» (enlace a `/#/privacidad`), «¿Puedo usar estos datos?» (enlace a `/web/datos.html`) y «¿Por qué mi comuna no aparece en el mapa?» (la regla real: sin detecciones ni incendios informados no hay nada que mostrar). (3) Cada sección con al menos un enlace a una fuente oficial o a la página que lo explica. (4) Quitar los comentarios con rutas del código; `title` con «BRASA» y una `description` de 60 a 160 caracteres. (5) Un enlace «Volver a BRASA» arriba y en el pie. (6) `tests/test_preguntas.py` (Python, sin navegador) que verifique: que `web/index.html` enlace la página; que cada `<section>` tenga al menos un enlace; que no queden comentarios con `.py:`; que el `title` contenga «BRASA» y la `description` tenga 60 caracteres o más; y que el archivo no pase de 4 KB.

**Reglas.** No inventes reglas: cada respuesta se apoya en el código actual (cítalo en el PR) o en una fuente oficial. No agregues ni cambies textos de emergencia (eso es delicado): las instrucciones siguen en «¿Qué hago si…?». Sin estilos nuevos, sin scripts y sin nuevas URLs.

**Archivos a tocar.** `web/preguntas.html`, `web/index.html`, `tests/test_preguntas.py`, `CHANGELOG.md`. No toques `web/datos.html` ni `web/js/datos.js` (otro ítem), ni `web/sitemap.xml` (no cambian URL), ni `web/admin.html`.

**Criterio de listo.** `python dev.py test -k preguntas` en verde con la prueba nueva, `python dev.py check` en «Todo en orden» y `web/preguntas.html` bajo 4 KB.

Verifica con `/verificar` y entrega con `/entregar-pr`. No mergees por iniciativa propia.


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.

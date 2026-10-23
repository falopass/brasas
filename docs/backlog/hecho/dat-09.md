---
id: DAT-09
repo: brasas
rama: feat/datos-abiertos-con-ejemplos
modelo: swe-2-high
riesgo: B
archivos: web/datos.html, web/js/datos.js, tests/test_datos_ejemplos.py, CHANGELOG.md
e2e: no
intento: 0
ronda_review: 0
estado_desde: 2026-10-20T10:10:17
nota: Reencolado: la corrida falló por rate limit del modelo gratis, no por el ítem.
---

**Objetivo.** Que la página de datos abiertos sirva para usarlos: un solo camino por conjunto y un ejemplo de llamada que se pueda copiar.

**Ítem del backlog.** DAT-04/DAT-05 (página de datos abiertos) y el foco de esta ronda («datos abiertos bien explicados»). El índice autodescriptivo ya existe (`GET /api/opendata`).

**Qué pasa hoy.** `web/datos.html:85-97` repite a mano las ocho URLs que el índice ya publica en la tabla de arriba (`:77-83`): dos sitios que hay que mantener y 268 bytes gzip de duplicación en una página cuyo presupuesto de peso está agotado. La tabla dice Conjunto, Parámetros, Geometría, Propiedades y Fuente, pero no responde las dos preguntas que trae cualquiera que quiere usar los datos: «¿para qué me sirve esto?» y «¿cómo lo pido?». Un periodista de Talca que quiere el riesgo de hoy de su comuna tiene que abrir `docs/API.md` y adivinar la sintaxis; la página está a un paso de servir y no sirve.

**Qué hacer.** (1) Quitar el bloque `<div id="directo">` completo (`datos.html:85-97`) con su lista de ocho URLs y reemplazarlo por una frase con un único enlace al índice `/api/opendata` («el índice describe cada conjunto; los enlaces de la tabla salen de ahí»). (2) En `web/js/datos.js`, al pintar la tabla, agregar una columna «Cómo se pide» con un ejemplo de una línea por conjunto, construido desde los campos del propio índice (nombre del conjunto y sus parámetros por defecto): `curl -s "https://…/api/opendata/<nombre>?<parámetros>"`. (3) Un bloque plegable «Ejemplo en 3 líneas» con un caso realista y copiable (riesgo de una comuna; detecciones de las últimas 24 h) y la advertencia de que son datos de solo lectura. (4) `tests/test_datos_ejemplos.py` (Python, sin red) que lea `web/datos.html` y `web/js/datos.js` y verifique: que ya no estén las ocho URLs duplicadas; que cada conjunto que declara el índice tenga su ejemplo; que todo ejemplo empiece con `curl` y use `https://`; y que la página siga avisando que BRASA no es oficial.

**Reglas.** Solo lectura, sin POST ni token. No cambies el contrato de `/api/opendata` (otro ítem está trabajando ahí: si el índice gana campos nuevos, tolerarlos y no editarlos). Sin JS en línea (CSP) ni dependencias nuevas; usa `textContent`/`util.js`, no `innerHTML` con datos de la API.

**Archivos a tocar.** `web/datos.html`, `web/js/datos.js`, `tests/test_datos_ejemplos.py`, `CHANGELOG.md`. No toques `backend/routes/opendata.py`, ni `docs/API.md`, ni `web/preguntas.html`.

**Criterio de listo.** `python dev.py test -k datos_ejemplos` en verde, `python dev.py check` en «Todo en orden» y `python scripts/local/presupuesto_peso.py` sin pasar de 199,6 KB (el cambio debe ser neutro o negativo en peso: quitas 268 bytes y agregas poco).

Verifica con `/verificar` y entrega con `/entregar-pr`. No mergees por iniciativa propia.


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.

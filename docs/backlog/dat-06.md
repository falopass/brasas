---
id: DAT-06
repo: brasas
rama: feat/graficos-con-fuente-y-csv
modelo: swe-2-high
riesgo: B
archivos: web/js/charts.js, tests/js/charts.test.mjs, CHANGELOG.md
e2e: si
intento: 0
ronda_review: 0
estado_desde: 2026-10-20T10:10:17
nota: Reencolado: la corrida falló por rate limit del modelo gratis, no por el ítem.
---

**Objetivo.** Que cada gráfico de BRASA se pueda descargar como CSV y muestre su fuente cuando el llamador la entrega, para que lo que se ve en pantalla se pueda guardar, citar y verificar sin copiar números a mano.

**Ítem del backlog.** UX-14 (descarga técnica del incidente) y DAT-05 (datos abiertos explicados): hoy solo el incidente se descarga —GeoJSON y KML—; las series que dibujan los gráficos no salen del navegador.

**Evidencia de que está pendiente.**
- `web/js/charts.js:60-72` (`timeChart`): el módulo solo dibuja los paneles y el resumen accesible; no expone la serie ni un botón de descarga.
- Los paneles llegan con `title`, `unit`, `series` y `threshold` (ver el llamador real en `web/js/views/incendio.js:198-206`), pero no hay ningún campo de fuente ni forma de sacar los valores.
- Quien necesita el dato (periodista, brigadista, municipio) hoy lo copia a mano del SVG, que además es `aria-hidden` (`charts.js:93`).
- `tests/js/charts.test.mjs` ya existe y está registrado en `tests/js/index.js:12`: no hace falta tocar el índice.

**Archivos a tocar.** `web/js/charts.js`, `tests/js/charts.test.mjs`, `CHANGELOG.md`. No toques nada más: **no edites las vistas** (`incendio.js`, `riesgo.js`, `casos.js` están tomadas por PRs abiertos) ni `tests/js/index.js`.

**Qué construir.**
1. Una función pura exportada `chartCsv(spec, { separator = ';' } = {})` que devuelva el CSV completo: primera columna `hora` con la marca ISO 8601 de cada instante de `spec.times`, después una columna por serie con su `label`; los `null`/`undefined`/`NaN` van como celda vacía; números con punto decimal; separador `;` (el que espera Excel en español) y BOM `\uFEFF` al inicio para que Excel respete las tildes.
2. Dentro de `timeChart`, un botón `Descargar CSV` por gráfico (no por panel) que arme el archivo con `chartCsv`, lo baje con un `Blob` y `URL.createObjectURL`, nombre `brasa-graficos-<AAAA-MM-DD>.csv`, y libere el objeto después de descargar. El botón debe ser un `<button type="button">` real, con texto visible y sin robar el foco del teclado al contenedor.
3. Un pie `spec.source` opcional: `{ label, url }` → una línea pequeña con `Fuente: <a>` al final del gráfico. Si el llamador no lo pasa, no se pinta nada (no inventes fuentes).

**Caso de prueba concreto.** En `tests/js/charts.test.mjs`: (1) 3 instantes y 2 series → cabecera `hora;GOES;VIIRS/MODIS` y 4 líneas, con la primera hora en ISO; (2) un `null` en medio → celda vacía y sin `NaN`; (3) `times` vacío → solo la cabecera, sin excepción; (4) el CSV empieza con `\uFEFF`; (5) el número `1234.5` sale con punto decimal y sin separador de miles.

**Criterio de listo.** `python dev.py check` en «Todo en orden» y `node --test tests/js/charts.test.mjs` en verde con las pruebas nuevas; `python dev.py run --demo` + `python dev.py e2e` sin errores JS ni textos cortados a 320/390/1280 px (el botón nuevo no debe romper el ancho del gráfico). Una línea «Para las personas» en `CHANGELOG.md`. Verifica con `/verificar` y entrega con `/entregar-pr`. No mergees por iniciativa propia.


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.

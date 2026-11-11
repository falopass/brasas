---
id: MOV-06
repo: brasas
rama: fix/estaticas-360
modelo: swe-2-high
riesgo: B
archivos: web/datos.html, web/js/datos.js, web/css/pantalla.css, web/lite.html, web/css/colegios.css, tests/test_pagina_datos.py, tests/test_lite_page.py, tests/test_movil_tactiles.py, docs/backlog/hecho/MOV-06.md, CHANGELOG.md
e2e: no
intento: 0
ronda_review: 0
estado_desde: 2026-11-11T00:00:00
nota:
---

# MOV-06 · Las páginas sueltas se leen y se tocan en el teléfono

**Objetivo.** Que las páginas estáticas sueltas cumplan en el teléfono los
mínimos táctiles y de lectura medidos en producción: la tabla de Datos
abiertos legible como ficha bajo 700 px, los enlaces de ruta con 44 px de
alto, el enlace a SENAPRED de la pantalla pública con 24 px (va dentro de una
frase) y ningún texto bajo 12 px en el modo liviano ni en la hoja de clase.

**Evidencia medida en producción** (Playwright, 360 y 390 px táctil,
11-nov-2026, `main` = c670a41). Ninguna de estas páginas tiene scroll
horizontal: eso ya estaba bien y no se tocó.

| Problema | Dónde | Medición |
|---|---|---|
| Tabla «Conjuntos disponibles» ilegible | `/web/datos.html` | 6+ columnas en 360 px; cada celda de pocas letras, ~8.500 px de alto |
| Enlaces de ruta bajo 44 px | `/web/datos.html` | `a` «/api/opendata/incidents.geojson» 218×16 px; «/api/opendata/observations.geojson» 244×16 px |
| Enlace bajo 24 px en frase | `/web/pantalla.html` | `a` «SENAPRED (senapred.cl)» 208×18 px |
| Etiquetas bajo 12 px | `/web/lite.html` | 8 `span` de `.phone` («CONAF · incendios forestales», «Bomberos», «SAMU · ambulancia»…) a 11,52 px |
| Texto bajo 12 px en pantalla | `/web/colegios.html` | `p.tiny` del pie a 11,33 px (8.5 pt) |

**Qué se hizo.**

1. `web/datos.html` + `web/js/datos.js`: bajo 700 px (`@media
   (max-width: 699px)`) la tabla sigue siendo `<table>` con sus `<th
   scope>` —el `thead` queda fuera de pantalla pero en el árbol de
   accesibilidad— y cada conjunto se lee como ficha: `display: block` en
   tabla/filas/celdas, cada `tr` como tarjeta y cada `td` con `data-label`
   (lo pone `celda()` en `fila()`) que `td::before` pinta como rótulo. El
   primer campo (nombre, ruta y «Abrir el archivo») queda arriba y «En
   palabras simples» ocupa todo el ancho; el resto son pares
   «etiqueta: valor». `overflow-wrap: anywhere` en las celdas para las rutas
   largas. En escritorio no cambia nada.
2. `web/datos.html` (mismo bloque móvil): el enlace de la ruta de cada
   conjunto lleva la clase `.ruta` y `display: inline-flex` con
   `min-height: 44px`, sin cambiar el tamaño de letra. «Abrir el archivo» ya
   medía 44 px (`.btn`).
3. `web/css/pantalla.css`: `.official-bar a` con `display: inline-flex`,
   `align-items: center` y `min-height: 24px` — el enlace va dentro de una
   frase del pie fijo, así que le basta el mínimo de enlace en línea.
4. `web/lite.html`: `.phone span` de `.72rem` (11,52 px) a `.75rem` (12 px).
   La página no tiene estilos de impresión que preservar.
5. `web/css/colegios.css`: `.tiny` gana `font-size: 12px` dentro de
   `@media screen`; el `.tiny` base sigue en 8.5 pt, así que la hoja
   impresa no cambia.
6. Pruebas: `tests/test_pagina_datos.py` fija el apilado móvil, los
   `data-label` de las 7 columnas y los 44 px de `.ruta`;
   `tests/test_lite_page.py` exige ≥12 px en `.phone span`;
   `tests/test_movil_tactiles.py` exige ≥24 px en `.official-bar a` y ≥12 px
   en el `.tiny` de pantalla de colegios.css con el impreso intacto.

**Supuestos.**

- Los enlaces `tel:` y los de ruta de `#directo-lista`/`#recetas` de
  datos.html quedan como enlaces en línea dentro de una frase (exentos del
  mínimo de 44 px, como en MOV-04); solo los de la tabla, que van solos en
  su línea, suben a 44 px.
- `.cifras .fuente` de colegios.html mide 12 px justos (9 pt) en pantalla:
  está en el mínimo, no bajo, y se dejó igual.
- La medición final a 360/390 px la repite el orquestador tras el despliegue.

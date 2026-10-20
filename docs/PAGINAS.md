# Páginas públicas de BRASA

Inventario de las páginas HTML que sirve el sitio, para quién es cada una, si se indexa y desde dónde se llega. `tests/test_paginas_publicas.py` lee esta tabla: **una página nueva no existe para el repo hasta que se agrega aquí**, y cambiar el `<meta name="robots">` de una página documentada sin actualizar la tabla rompe el CI.

| Ruta | Para quién | Indexable | Desde dónde se llega | Precache del service worker |
|---|---|---|---|---|
| `/` (`web/index.html`) | Público general: la app completa con mapa, lugares y avisos | indexable — es la portada canónica | Portada del dominio; única ruta en el sitemap | Sí: `/` y todo el `SHELL` de `sw.js` (JS de vistas, datos, iconos, fuentes) |
| `/web/lite.html` | Celulares de gama baja o conexiones malas: mismo estado de lugares sin mapa | noindex — es una versión alternativa de la app; la canónica es `/` | URL directa compartida; hoy también en el sitemap (el PR #299 la quita) | Sí: `lite.html` y `js/lite.js` |
| `/web/lista.html` | Quien quiere la hoja A4 imprimible de emergencia (refrigerador, velador) | noindex — utilitario imprimible, duplica contenido de la vista «Prepárate» | Enlace «Hoja para imprimir» en la vista Prepárate; también responde en `/lista.html` | Sí: `lista.html` y `css/lista.css` |
| `/web/pantalla.html` | Municipios, cuarteles de Bomberos y colegios: pantalla fija de solo lectura | noindex — página de exhibición rotativa, no pensada para buscadores | Solo por URL directa (la instala quien opera la pantalla) | No: se usa en pantallas conectadas, no precachea |
| `/web/respuesta.html` | Público general y prensa: tiempos de respuesta oficiales de CONAF, con fuentes | indexable — contenido editorial con datos propios, aporta al sitio | Enlace en el pie de `index.html` | Sí: `respuesta.html`, `js/respuesta.js` y `css/lista.css` (compartida) |
| `/web/admin.html` | La persona que modera reportes ciudadanos (pide token) | noindex — herramienta interna; `robots.txt` bloquea `/admin` y `/web/admin.html` | Solo por URL directa en `/admin` | No |

## Pendientes de documentar

PRs abiertos al momento de escribir esto; cada una se agrega a la tabla cuando se fusione:

- `datos.html` (PR #231)
- `embed.html` (PR #217)
- `plan.html` (PR #252)
- Una eventual página de preguntas frecuentes.

## Presupuesto de peso

El presupuesto de `scripts/local/presupuesto_peso.py` es de 165 KB gzip para el frontend propio y hoy la medición ya lo supera (≈165,3 KB en `main`, antes de este PR). Las páginas nuevas tienen que nacer livianas (HTML + CSS + un JS mínimo), y si precachean algo hay que medirlo contra el presupuesto antes de fusionar.

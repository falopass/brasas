# Páginas públicas de BRASA

Inventario de las páginas HTML que sirve el sitio, para quién es cada una, si se indexa y desde dónde se llega. `tests/test_paginas_publicas.py` lee esta tabla: **una página nueva no existe para el repo hasta que se agrega aquí**, y cambiar el `<meta name="robots">` de una página documentada sin actualizar la tabla rompe el CI.

| Ruta | Para quién | Indexable | Desde dónde se llega | Precache del service worker |
|---|---|---|---|---|
| `/` (`web/index.html`) | Público general: la app completa con mapa, lugares y avisos | indexable — es la portada canónica | Portada del dominio; única ruta en el sitemap | Sí: `/` y todo el `SHELL` de `sw.js` (JS de vistas, datos, iconos, fuentes) |
| `/web/lite.html` | Celulares de gama baja o conexiones malas: mismo estado de lugares sin mapa | noindex — es una versión alternativa de la app; la canónica es `/` | URL directa compartida | Sí: `lite.html` y `js/lite.js` |
| `/web/lista.html` | Quien quiere la hoja A4 imprimible de emergencia (refrigerador, velador) | noindex — utilitario imprimible, duplica contenido de la vista «Prepárate» | Enlace «Hoja para imprimir» en la vista Prepárate; también responde en `/lista.html` | Sí: `lista.html` y `css/lista.css` |
| `/web/pantalla.html` | Municipios, cuarteles de Bomberos y colegios: pantalla fija de solo lectura | noindex — página de exhibición rotativa, no pensada para buscadores | Solo por URL directa (la instala quien opera la pantalla) | No: se usa en pantallas conectadas, no precachea |
| `/web/respuesta.html` | Público general y prensa: tiempos de respuesta oficiales de CONAF, con fuentes | indexable — contenido editorial con datos propios, aporta al sitio | Enlace en el pie de `index.html` | Sí: `respuesta.html`, `js/respuesta.js` y `css/lista.css` (compartida) |
| `/web/admin.html` | La persona que modera reportes ciudadanos (pide token) | noindex — herramienta interna; `robots.txt` bloquea `/admin` y `/web/admin.html` | Solo por URL directa en `/admin` | No |
| `/web/datos.html` | Prensa, investigación y otras apps: el catálogo de los datos abiertos de la API | indexable — página editorial pública que describe `/api/opendata`; está en el sitemap | Sitemap y URL directa (`/datos.html` también responde) | No |
| `/web/preguntas.html` | Público general: dudas frecuentes sobre los avisos y de dónde salen los datos | indexable — contenido editorial; está en el sitemap | Sitemap y URL directa | No |
| `/web/plan.html` | Quien imprime su plan familiar de emergencia rellenado en la app | noindex — hoja imprimible con los datos del propio dispositivo | Botón «Imprimir plan» de la vista Prepárate | No |

## Pendientes de documentar

Nada: las nueve páginas HTML que sirve el sitio están en la tabla.

## Presupuesto de peso

El presupuesto de `scripts/local/presupuesto_peso.py` es de 240 KB gzip para el frontend propio (todo `web/` propio: JS, CSS, HTML y manifiesto). Las páginas nuevas tienen que nacer livianas (HTML + CSS + un JS mínimo), y si precachean algo hay que medirlo contra el presupuesto antes de fusionar.

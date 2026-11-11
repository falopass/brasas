---
id: UX-VISTAS
repo: brasas
rama: fix/vistas-estados
modelo: swe-2-high
riesgo: B
archivos: web/js/views/calidad.js, web/js/views/casos.js, web/js/views/preparate.js, web/js/errores.js, web/css/app.css, tests/js/calidad.test.mjs, tests/js/casos.test.mjs, tests/js/errores.test.mjs, tests/js/preparate.test.mjs, docs/backlog/hecho/UX-VISTAS.md, CHANGELOG.md
e2e: no
intento: 0
---

# UX-VISTAS · Calidad, Historia y Prepárate dicen qué falló y se leen a 360 px

**Objetivo.** Que las vistas Calidad (`#/calidad`), Historia (`#/casos`) y
Prepárate (`#/preparate`) nombren la consulta que falló, no se contradigan
cuando muestran una copia vieja del estado, y se lean apiladas en 360 px.

**Evidencia medida en producción** (Playwright, 360/390 px táctil y 1280 px,
11-nov-2026, `main` = 9b6f215): el diagnóstico de Calidad partía cada problema
en tres columnas de ~70 px; con `/api/status` caída el veredicto decía «Todo al
día» sobre una copia vieja y el aviso parcial afirmaba «Lo demás sigue al día»;
el texto gris del aviso amarillo medía contraste dudoso; los errores de Historia
y de «Comunas prioritarias» no nombraban la consulta; «¿Puedo quemar hoy?»
escondía el fallo de `/api/climate/quema` y la falta de comuna; los enlaces de
fuente de Prepárate se solapaban al partirse en dos líneas; y había enlaces sin
nombre accesible.

**Qué se hizo.**

1. **Diagnóstico de Calidad apilado en teléfono.** La lista del bloque lleva la
   clase `list-diag`; en la sección nueva `/* UX-VISTAS: calidad, historia y
   prepárate */` de `web/css/app.css` (inmediatamente antes de `/* VIS-02 */`),
   un `@media (max-width: 899px)` propio la pasa a columna: título, detalle y
   arreglo cada uno en su línea.
2. **Veredicto honesto con copia vieja.** `bloqueDiagnostico(status,
   sinActualizar)` dice «Último estado conocido (hace N min): sin problemas
   reportados» o «…: había algo que revisar», con la hora exacta
   (`fmtDateTime`) en la lectura técnica del `dual`. Con el estado al día no
   cambia nada. `sinActualizar` también se enciende cuando el service worker
   sirve la copia guardada de `/api/status` (respuesta 200 con
   `X-Brasa-Cached-At`, que `api.js` ya guarda en `storage('cached-at')`):
   sin esa revisión, sin conexión el veredicto seguía diciendo «Todo al día».
3. **`partialNotice` sin «al día» de más.** Con `sinActualizar` el aviso dice
   «Lo demás es del último estado conocido» en vez de «Lo demás sigue al día».
4. **Contraste del texto gris sobre el aviso amarillo.** Medido con los tokens:
   `--muted` sobre `color-mix(in srgb, --risk-moderado 18%, --surface)` da
   5,46:1 en oscuro (`#a39a8d` sobre `#2b260e`) y 5,24:1 en claro (`#5d554a`
   sobre `#e2dabd`) — ambos sobre 4,5:1, así que no se tocó ningún color.
5. **Historia.** `errorConSalida` acepta un `titulo` propio (sin cambiar el
   comportamiento por defecto): el catálogo dice «No se pudieron cargar los
   incendios históricos. Revisa tu conexión y vuelve a intentarlo.» y la ficha
   «No se pudo cargar este incendio histórico…», conservando «Reintentar» y los
   teléfonos. `#nom-comuna` lleva `enterkeyhint="search"`,
   `autocapitalize="off"`, `autocorrect="off"` y `spellcheck="false"`; el error
   de la lista de nominados pasa a `dual(sencillo, técnico)` con «Reintentar»
   (y `nominadosPromise = null` para que el reintento no reuse la promesa
   rechazada); sin resultados dice «Ningún incendio con nombre en «X». Prueba
   con otra comuna o borra la búsqueda.»; un filtro de región sin casos muestra
   el estado vacío con «Quita el filtro»; y el enlace «↗» de cada revisión de
   cifra lleva `aria-label="Abrir la fuente: <fuente>"`.
6. **Prepárate.** `puedoQuemar` recibe `consulta` ('ok' | 'fallo' |
   'sin-comuna'): con la consulta caída dice «No pudimos consultar las
   condiciones de hoy para tu comuna» y sin comuna «Guarda un lugar para ver
   las condiciones de tu comuna», siempre con «la autorización la da CONAF o el
   municipio»; si el store dice riesgo alto o Botón Rojo, «Hoy no quemes» sigue
   ganando. Los enlaces de `srcs` van en su propia línea en teléfono
   (`.srcs a` en flex, ≥24 px tocables, separador `.src-sep` oculto), sin
   solaparse. `priorityBlock` nombra la consulta: «No pudimos cargar la lista
   de comunas prioritarias.»
7. **Enlaces sin nombre accesible.** Los 22 de Prepárate eran falso positivo:
   son los `<a>` con texto de los `details` cerrados de «Si hay un incendio
   cerca» (17 de «Durante», 4 de «Después») y de «Denunciar» (1), donde
   `innerText` mide vacío. El de Historia (el «↗» de las revisiones) quedó con
   `aria-label`. Los 4 de Riesgo quedaron anotados en el PR (fuera de alcance).

**Verificación.** `node --check` en los cuatro `.js` tocados; `node --test` de
`calidad`, `casos`, `preparate` y `errores` (111 pruebas) y la suite JS
completa (919); `pytest` acotado sobre los tests que leen `app.css`,
`calidad.js`, `casos.js`, `preparate.js`, `errores.js` y `test_security.py`
(188).

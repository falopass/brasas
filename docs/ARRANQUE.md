# Peso del arranque (QA-62)

## Qué es

El **arranque** es lo que el navegador descarga antes de poder mostrar y usar
BRASA: la portada (`web/index.html`), las hojas de estilo y las fuentes
precargadas del `<head>`, el módulo de entrada (`web/js/app.js`) y los módulos
que este alcanza. Se separan dos conjuntos y no se esconde ninguno:

- **Bloqueante**: lo alcanzable por imports estáticos (`import … from`,
  `export … from` e `import '…'`). Es lo que el navegador descarga y parsea
  antes del primer pintado. Se mide contra el presupuesto de **180 KB**.
- **Diferido**: lo alcanzable solo por `import('…')` desde el arranque. No
  bloquea el primer pintado; se informa siempre y suma al total, que tiene su
  propio tope de **300 KB** para que no crezca sin control.

`zona.js` es la portada y viaja en el arranque. El resto de las vistas se piden
con `import()` desde el router de `app.js`, memorizando la promesa para no
descargarlas dos veces. `incendio.js` sigue en el bloqueante porque `zona.js`
importa de ahí el catálogo `INCIDENT`; el router igual lo pide con `import()`,
pero el navegador ya lo tiene. La tipografía de títulos (Anybody) ya no se
precarga (QA-62): `app.css` la declara con `font-display: swap` y llega después
del primer pintado.

Se diferencia del presupuesto total de `presupuesto_peso.py`, que suma todo
`web/` junto y no distingue lo que bloquea la primera pantalla de lo que se
descarga solo cuando se pide (las demás páginas HTML y sus scripts).

## Cómo se mide

```bash
python scripts/local/peso_arranque.py --informe   # tabla completa, siempre sale 0
python scripts/local/peso_arranque.py --json      # medición en JSON, con las dos secciones
python scripts/local/peso_arranque.py             # sale 1 si bloqueante > 180 KB o total > 300 KB
```

Solo stdlib. Cuenta el tamaño en disco y gzip-9 de cada archivo. Lo externo
(CDN, `https://…`) no se cuenta —no es nuestro— y `web/vendor` solo entra
cuando `index.html` lo referencia directo (las fuentes y el CSS de MapLibre sí
bloquean el primer pintado); los imports de módulos vendor no se siguen, igual
que en `tests/test_estaticas_guardas.py`.

## El número de hoy

Medido el 2026-10-20 sobre esta rama: **126,8 KB gzip** de bloqueante,
**80,6 KB** de diferido y **207,4 KB** de total. Presupuestos: **180 KB**
bloqueante (~29 % de holgura) y **300 KB** total, fijados en
`scripts/local/peso_arranque.py`.

Los cinco archivos más pesados del bloqueante (gzip):

| archivo | gzip |
|---|---|
| `web/vendor/fonts/public-sans-latin-wght-normal.woff2` | 26,2 KB |
| `web/css/app.css` | 13,9 KB |
| `web/js/ui.js` | 12,9 KB |
| `web/js/views/zona.js` | 12,2 KB |
| `web/vendor/maplibre/maplibre-gl.css` | 9,8 KB |

Anybody (títulos) sigue en `web/vendor/fonts` y declarada en `app.css`, pero ya
no se precarga: no cuenta en el arranque.

## Si se pasa del presupuesto

Recorta el arranque o mueve la vista a carga diferida (`import()` desde el
router, no arriba en `app.js`); no subas el umbral sin explicar el porqué en
el CHANGELOG. Si el diferido crece de más, revisa que no se esté pidiendo una
vista al abrir la portada.

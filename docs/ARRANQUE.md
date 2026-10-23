# Peso del arranque (QA-62) y de las páginas bajo demanda (DEBT-07)

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

Las **páginas bajo demanda** son lo propio que no viaja en el arranque: las
demás páginas HTML (`lite`, `lista`, `pantalla`, `respuesta`, `admin`, `datos`,
`preguntas`, `plan`), sus CSS y sus JS, más el manifiesto. Se miden aparte para
que una página nueva compita con las otras páginas y no con lo que bloquea el
primer pintado, que es el número que sufre una conexión rural (DEBT-07).

## Los topes

| presupuesto | qué incluye | script | tope |
|---|---|---|---|
| Arranque bloqueante | portada, CSS y fuentes precargadas, `app.js` y sus imports estáticos | `scripts/local/peso_arranque.py` | **180 KB** |
| Arranque total | lo bloqueante más lo que solo llega por `import()` | `scripts/local/peso_arranque.py` | **300 KB** |
| Páginas bajo demanda | las demás páginas, sus CSS y sus JS, y el manifiesto | `scripts/local/presupuesto_peso.py` | **75 KB** |
| Archivo suelto | cualquier archivo propio, también los del arranque | `scripts/local/presupuesto_peso.py` | **15 KB** |

Los dos scripts corren en `python dev.py check` y sus presupuestos suman todo lo
propio de `web/`, sin contar nada dos veces. El mensaje de error dice cuál de
los topes se pasó y cuál es el archivo más pesado de ese presupuesto.

## Cómo se mide

```bash
python scripts/local/peso_arranque.py --informe         # tabla completa, siempre sale 0
python scripts/local/peso_arranque.py --json            # medición en JSON, con las dos secciones
python scripts/local/peso_arranque.py                   # sale 1 si bloqueante > 180 KB o total > 300 KB
python scripts/local/presupuesto_peso.py --informe      # solo las páginas bajo demanda
python scripts/local/presupuesto_peso.py --json         # cada archivo con su presupuesto
python scripts/local/presupuesto_peso.py                # sale 1 si el total supera el umbral
```

Solo stdlib. Cuenta el tamaño en disco y gzip-9 de cada archivo. En el arranque,
lo externo (CDN, `https://…`) no se cuenta —no es nuestro— y `web/vendor` solo
entra cuando `index.html` lo referencia directo (las fuentes y el CSS de
MapLibre sí bloquean el primer pintado); los imports de módulos vendor no se
siguen, igual que en `tests/test_estaticas_guardas.py`. En las páginas bajo
demanda, `web/vendor` queda fuera y el tope por archivo suelto (15 KB) cubre
todo lo propio, también lo del arranque.

## El número de hoy

Medido el 2026-10-22 sobre main: **133,9 KB gzip** de bloqueante,
**104,7 KB** de diferido y **238,6 KB** de total, frente a **62,2 KB gzip** bajo
demanda. Presupuestos: **180 KB** bloqueante (~26 % de holgura) y **300 KB**
total, fijados en `scripts/local/peso_arranque.py`; **75 KB** bajo demanda
(~20 % de holgura), en `scripts/local/presupuesto_peso.py`. Antes de diferir las
vistas (#438) el arranque medía 252,9 KB gzip.

Los cinco archivos más pesados del bloqueante (gzip):

| archivo | gzip |
|---|---|
| `web/vendor/fonts/public-sans-latin-wght-normal.woff2` | 21,7 KB |
| `web/css/app.css` | 13,9 KB |
| `web/js/views/zona.js` | 13,5 KB |
| `web/js/ui.js` | 13,0 KB |
| `web/js/map.js` | 11,6 KB |

Anybody (títulos) sigue en `web/vendor/fonts` y declarada en `app.css`, pero ya
no se precarga: no cuenta en el arranque.

## Si se pasa del presupuesto

En el arranque: recorta o mueve la vista a carga diferida (`import()` desde el
router, no arriba en `app.js`); si el diferido crece de más, revisa que no se
esté pidiendo una vista al abrir la portada. En las páginas bajo demanda:
recorta la página o mueve a un módulo compartido lo que se repita. No subas el
umbral que corresponda sin explicar el porqué en el CHANGELOG.

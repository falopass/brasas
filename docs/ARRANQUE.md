# Peso del arranque (QA-62)

## Qué es

El **arranque** es todo lo que el navegador descarga antes de poder mostrar y
usar BRASA: la portada (`web/index.html`), las hojas de estilo y las fuentes
precargadas del `<head>`, el módulo de entrada (`web/js/app.js`) y **todos**
los módulos alcanzables desde él por imports relativos (`import … from`,
`import '…'`, `export … from` e `import()` dinámico). Hoy `app.js` importa las
once vistas de forma estática, así que todas viajan en el arranque aunque la
persona nunca las abra.

Se diferencia del presupuesto total de `presupuesto_peso.py`, que suma todo
`web/` junto y no distingue lo que bloquea la primera pantalla de lo que se
descarga solo cuando se pide (las demás páginas HTML y sus scripts).

## Cómo se mide

```bash
python scripts/local/peso_arranque.py --informe   # tabla completa, siempre sale 0
python scripts/local/peso_arranque.py --json      # medición en JSON
python scripts/local/peso_arranque.py             # sale 1 si el total supera el umbral
```

Solo stdlib. Cuenta el tamaño en disco y gzip-9 de cada archivo del arranque.
Lo externo (CDN, `https://…`) no se cuenta —no es nuestro— y `web/vendor`
solo entra cuando `index.html` lo referencia directo (las fuentes y el CSS de
MapLibre sí bloquean el primer pintado); los imports de módulos vendor no se
siguen, igual que en `tests/test_estaticas_guardas.py`.

## El número de hoy

Medido el 2026-10-20 sobre main con DET-16: **256,0 KB gzip** de arranque,
frente a 163,7 KB gzip de todo `web/` propio en el presupuesto general — el
arranque pesa más que el frontend entero porque incluye fuentes y vendor.
Presupuesto: **257 KB** (la capa de humo agrega `smoke.js` al grafo y dejó el
total 41 bytes sobre los 256 KB anteriores, fijado en
`scripts/local/peso_arranque.py`).

Los cinco archivos más pesados del arranque (gzip):

| archivo | gzip |
|---|---|
| `web/vendor/fonts/anybody-latin-standard-normal.woff2` | 55,6 KB |
| `web/vendor/fonts/public-sans-latin-wght-normal.woff2` | 26,2 KB |
| `web/css/app.css` | 13,6 KB |
| `web/js/ui.js` | 12,9 KB |
| `web/js/views/riesgo.js` y `web/js/views/zona.js` | 12,2 KB |

## Si se pasa del presupuesto

Recorta el arranque o mueve la vista a carga diferida (`import()` desde el
router, no arriba en `app.js`); no subas el umbral sin explicar el porqué en
el CHANGELOG.

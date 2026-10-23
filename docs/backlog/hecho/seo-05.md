---
id: SEO-05
repo: brasas
rama: feat/paginas-por-comuna
modelo: fusion-claude-opus-5-5-high-sidekick-swe-2-high
riesgo: C
archivos: web/comuna/, web/sitemap.xml, deploy/, backend/main.py, docs/SEO.md
e2e: si
intento: 0
ronda_review: 0
---

# SEO-05 · Páginas indexables por comuna (decisión de Diego)

## Por qué no se lanza
Toca **URLs indexadas**, el `sitemap.xml`, el enrutado del Worker y `deploy/`. Por la regla de riesgo C, esto no sale solo de noche: necesita el OK del dueño y el orden de fusión.

## La oportunidad
BRASA se adquiere por búsqueda, y hoy toda la aplicación vive en rutas con `#`, que ningún buscador indexa. El sitemap tiene **una** página útil (`/`; `lite.html` lo quita el PR #299) y el sitio no responde a la búsqueda más obvia de su categoría: «riesgo de incendio en <comuna>».

Los datos ya están: `/api/risk/{code}` (por comuna, público, sin token), `/web/data/comunas-index.json` (345 comunas con nombre, región, centro y caja) y `/web/data/historia-comunas.json` (PR #293). Ninguna pieza es nueva salvo la página y la ruta.

## Qué haría el encargo (si Diego dice sí)
1. Ruta estable `/comuna/<slug>` servida por el Worker (o HTML estático generado en el build) con riesgo del día, FWI, Botón Rojo, lluvia de la temporada, exposición (censo) y un enlace a la aplicación con esa comuna ya elegida.
2. `<title>`, `description`, `canonical` y JSON-LD por comuna; `noindex` para las que no tengan datos.
3. `sitemap.xml` generado desde `comunas-index.json` y guarda de que cada URL del sitemap existe.
4. Cache del borde y respeto del presupuesto de peso (ver la otra decisión).

## Riesgos
- 345 páginas finas si el riesgo viene vacío → hay que exigir contenido mínimo antes de indexar.
- Cambia el contrato del sitemap y del enrutado: conviene hacerlo después de fusionar #299 y #231.
- La licencia de los datos que se muestran debe estar resuelta (OFI-03 sigue abierto).

## Criterio de término (para /goal)
Al terminar: `curl` a tres comunas distintas devuelve 200 con riesgo del día y canonical propio; el sitemap las lista; `python dev.py check` y `-E2E` en verde; ninguna comuna sin datos queda indexable.

## Verificación y entrega
Verifica con /verificar y entrega con /entregar-pr. No mergees por iniciativa propia.


Aprobado por Hermes (20-10): Diego delegó la decisión. Pasa a cola.


Apartado por Diego (20-10): lo vistoso va después, con Fusion. No despachar todavía.

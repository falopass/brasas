---
id: MAPA-155
repo: brasas
rama: feat/capas-relieve-senapred
modelo: swe-2-high
riesgo: B
archivos: web/js/map.js, web/js/capas.js, docs/FUENTES.md, web/data/licencias.json, CHANGELOG.md
e2e: si
intento: 0
depende: INV-29 (licencia del DEM, docs/investigacion/INV-29-relieve.md), PR de MAPA-151..154
---

# MAPA-155 · Relieve sombreado opcional

**Por qué.** El fuego sube por las laderas y el viento se encajona en las quebradas. Hoy el mapa es plano: no se ve si el incendio está en un cerro sobre la casa o en el plano.

**Qué hacer.**
1. Capa opcional «Relieve» en `CAPAS` (apagada por defecto) con una capa `hillshade` de MapLibre sobre una fuente `raster-dem`, debajo de todo lo puntual y de las coropletas.
2. La fuente de teselas DEM es la que haya resuelto la investigación de relieve (`docs/investigacion/`): licencia abierta verificada, atribución y URL. **Si la investigación no encontró una licencia abierta verificable, no implementes la capa**: deja el encargo bloqueado con la razón.
3. Atribución visible en el control de atribución del mapa, fila en `docs/FUENTES.md` y entrada en `web/data/licencias.json`.
4. La CSP no cambia (`img-src https:` y `connect-src https:` ya lo permiten); verifica que `tests/test_security.py` siga pasando.
5. Que no pese en el arranque: la fuente se agrega solo cuando la capa se prende.

**Archivos.** `web/js/map.js`, `web/js/capas.js`, `docs/FUENTES.md`, `web/data/licencias.json` y `CHANGELOG.md`.

**Criterio de listo.** La capa se prende desde el control, se refleja en `#/mapa?capas=…,relieve`, tiene atribución y el CI pasa (incluido el presupuesto de peso).

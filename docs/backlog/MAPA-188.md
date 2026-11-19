---
id: MAPA-188
repo: brasas
rama: feat/pmtiles-r2-basemap-dpa-oficial
modelo: agente-alto
riesgo: A
archivos: deploy/cloudflare/src/index.ts, scripts/, web/js/map.js, web/data/licencias.json, docs/FUENTES.md, tests/
e2e: si
---

# MAPA-188 · Mapa base propio Protomaps/PMTiles en R2, DPA oficial completa y evaluación de VersaTiles

## Objetivo

Alojar un recorte propio de Chile en formato `.pmtiles` dentro del bucket R2 de BRASA (OSM actualizado + límites oficiales BCN/SUBDERE de alta precisión para zoom >= 11, límites provinciales y límite urbano + curvas de nivel vectoriales desde GLO-30) servido por el Worker como endpoint XYZ estándar (`/{z}/{x}/{y}.mvt` + TileJSON) sin añadir dependencias JS en el frontend, y evaluar VersaTiles (`tiles.versatiles.org`) como respaldo vectorial secundario frente a servidores comunitarios sin SLA.

## Contexto

- Hoy BRASA depende de OpenFreeMap (`tiles.openfreemap.org`) y OpenTopoMap sin SLA (`docs/FUENTES.md#L104`), y `web/data/comunas.geojson` está simplificado a ~450 m y se desvanece sobre zoom 10, impidiendo distinguir en zoom >= 11 límites comunales finos ni el límite urbano oficial (`mapa.md` §4.A.1–2 y §4.F.14).
- MapLibre GL JS v5.24.0 consume endpoints XYZ MVT directamente sin instalar `pmtiles.js`, cumpliendo la regla de «sin dependencias nuevas de frontend».
- El diseño debe seguir la guía oficial de Protomaps para Cloudflare Workers + R2 y mantener el fallback a OpenFreeMap/offline si el artefacto no está subido en entornos locales/demo.

## Archivos

- `deploy/cloudflare/src/index.ts` (ruta XYZ `/tiles/.../{z}/{x}/{y}.mvt` y TileJSON leyendo rangos desde R2 `BUCKET`)
- `scripts/` (pipeline reproducible de generación/extracción Chile con `pmtiles`, DPA SUBDERE/BCN y curvas de nivel)
- `web/js/map.js` (consumo de tiles propios/DPA completa/curvas de nivel y fallback opcional a VersaTiles o OpenFreeMap)
- `web/data/licencias.json`, `docs/FUENTES.md` y `tests/` (manteniendo paridad CSP en `test_security.py` si se agregan orígenes)

## Criterio de listo

- Con el archivo `.pmtiles` en R2 o mock en pruebas, el Worker responde teselas MVT con cabeceras de caché y rango válidas.
- Al acercar a zoom >= 11 se distinguen los límites comunales precisos y el límite urbano/provincial sin romper la vista en `--demo`.
- Atribución completa visible (`© OpenStreetMap contributors` ODbL, Protomaps, SUBDERE/BCN).
- CI en verde (`pytest`, `test_security.py`, revisión JS y `e2e`).

## Fuente y licencia

- **Nombre:** Protomaps / OpenStreetMap + DPA oficial BCN / SUBDERE / IDE Chile + VersaTiles (evaluación de respaldo).
- **Enlace:** <https://docs.protomaps.com/pmtiles/cloudflare> · <https://build.protomaps.com/> · <https://versatiles.org/> · <https://ide.subdere.gov.cl/> · <https://www.bcn.cl/siit/mapas_vectoriales>.
- **Licencia:** **ODbL** para datos OpenStreetMap (<https://www.openstreetmap.org/copyright>), **BSD-3-Clause / CC0** para Protomaps y esquema Shortbread **CC0** para VersaTiles; para los geoservicios/archivos DPA de SUBDERE / BCN / IDE Chile, **licencia por confirmar** en <https://ide.subdere.gov.cl/> y <https://www.geoportal.cl/> (verificar términos explícitos de redistribución antes de empaquetar).

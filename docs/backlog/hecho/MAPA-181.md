---
id: MAPA-181
repo: brasas
rama: feat/capa-infraestructura-critica
modelo: agente-alto
riesgo: B
archivos: backend/providers/overpass.py, scripts/, web/js/map.js, web/js/capas.js, web/js/views/mapa.js, web/data/licencias.json, docs/FUENTES.md, tests/
e2e: si
---

# MAPA-181 · Capa conmutable de infraestructura crítica en el mapa (OSM + MINSAL + MINEDUC)

## Objetivo

Exponer en el mapa (`web/js/map.js` y `web/js/views/mapa.js`) una capa opcional y conmutable (apagada por defecto, visible desde zoom >= 10) con cuarteles de bomberos, hospitales/CESFAM, escuelas (posibles albergues) y subestaciones/líneas eléctricas de alta tensión, combinando datos pre-extraídos de OpenStreetMap (Overpass) con los registros estatales de MINEDUC y MINSAL en zonas rurales donde OSM sea incompleto.

## Contexto

- Hoy `backend/providers/overpass.py` solo entrega datos bajo demanda para la lista de texto en `incendio.js` («a sotavento») y el modal de `zona.js`. No existe ninguna capa cartográfica de infraestructura crítica en `web/js/capas.js` ni `web/js/map.js`.
- Para no saturar la API pública de Overpass desde los navegadores de las personas usuarias, la capa debe servirse desde artefactos estáticos/PMTiles o caché en R2 generados periódicamente (`'self'`), evitando además exponer servidores estatales lentos en horas punta.
- En el informe `mapa.md` también se señalan las capas estatales de MINEDUC (`geoportal.cl/geoserver/Establecimientos_Educacion_Escolar/wms`) y MINSAL en IDE Chile como complemento rural.

## Archivos

- `scripts/` (exportación y simplificación periódica de infraestructura crítica OSM + MINEDUC/MINSAL a GeoJSON/PMTiles estático)
- `web/js/map.js` (capas de puntos/líneas por categoría desde zoom >= 10 con iconos/colores accesibles y popup informativo)
- `web/js/capas.js` y `web/js/views/mapa.js` (registro en `CAPAS`, interruptor en grupo Contexto, leyenda y atribución)
- `web/data/licencias.json`, `docs/FUENTES.md` y `tests/`

## Criterio de listo

- Al activar «Infraestructura crítica» en `#map-layers` con zoom >= 10 se muestran bomberos, salud, escuelas y líneas eléctricas sobre la vista sin consultar Overpass directamente desde el navegador.
- Al hacer clic en un elemento se muestra su tipo, nombre y fuente; la leyenda y atribución citan `© OpenStreetMap contributors` (ODbL) y la fuente estatal que corresponda.
- CI en verde (`pytest`, revisión JS y `e2e`).

## Fuente y licencia

- **Nombre:** OpenStreetMap (vía Overpass API) + MINEDUC y MINSAL vía Geoportal IDE Chile.
- **Enlace:** <https://overpass-api.de/> · `https://geoportal.cl/geoserver/Establecimientos_Educacion_Escolar/wms?request=GetCapabilities` · <https://www.geoportal.cl/>.
- **Licencia:** **ODbL** para OpenStreetMap (<https://www.openstreetmap.org/copyright>); para los geoservicios estatales de MINEDUC/MINSAL vía IDE Chile, **licencia por confirmar** en <https://www.geoportal.cl/> (verificar términos explícitos de redistribución antes de incorporarlos al artefacto nacional).

## Resolución (2026-11-24)

- **Fuentes con licencia verificada:** OpenStreetMap (extracto nacional de Geofabrik Chile, **ODbL**) para cuarteles de bomberos, escuelas, subestaciones y líneas eléctricas ≥ 110 kV, y **DEIS · MINSAL** en `datos.gob.cl` (**CC0 1.0**) para la red pública de salud (Hospitales, CESFAM, SAR, SAPU, SUR, CECOSF y Postas de Salud Rural); los hospitales OSM solo completan donde no hay registro DEIS a ≤ 500 m.
- **MINEDUC queda fuera por ahora:** el Directorio de Establecimientos de `datosabiertos.mineduc.cl` y el WMS de `geoportal.cl` no declaran licencia de redistribución explícita; quedan documentados en `docs/FUENTES.md` sin incorporación directa mientras no se confirme la licencia (criterio de este encargo), usando OSM ODbL para las escuelas.
- **Artefacto estático de carga diferida:** `scripts/local/build_infraestructura.py` genera `web/data/infraestructura/chile.json` recortado estrictamente al polígono comunal BCN exacto para OSM (con tolerancia costera de ~450 m solo para registros oficiales DEIS MINSAL en fiordos/islas; incluye Rapa Nui y Juan Fernández y excluye Antártica y fronteras de Perú, Bolivia y Argentina) con **17.219 elementos** (871 bomberos, 2.425 de salud, 10.943 escuelas, 971 subestaciones y 2.009 líneas AT ≥ 110 kV) en **296 KB gzip**; la capa se sirve desde el archivo estático (carga diferida al encenderla desde zoom ≥ 10), sin consultas directas a Overpass ni a servidores estatales desde el navegador.
- **Pruebas añadidas:** `tests/test_infraestructura.py` (metadatos y licencias, conteos contra `rows`/`lines`, forma y encuadre, y las funciones puras del generador), bloque de `tests/js/capas-abiertas.test.mjs` para el registro de la capa y sus exclusiones, y la política de frescura anual en `scripts/local/revisar_datos_versionados.py` (`infraestructura/chile.json`: 365 días).

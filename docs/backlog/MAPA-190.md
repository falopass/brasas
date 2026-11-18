---
id: MAPA-190
repo: brasas
rama: feat/exposicion-censo-vialidad-y-eval-grd
modelo: agente-alto
riesgo: B
archivos: scripts/, web/js/map.js, web/js/capas.js, web/js/views/mapa.js, web/js/views/incendio.js, web/data/licencias.json, docs/FUENTES.md, tests/
e2e: si
---

# MAPA-190 · Exposición poblacional fina (Censo 2024 manzana, WorldPop, GHSL), red vial MOP/OSM y evaluación SENAPRED GRD / CONAF cortafuegos

## Objetivo

Incorporar capas opcionales de exposición humana y accesibilidad vial alrededor de incendios: (1) densidad poblacional fina con **INE Censo 2024 por manzana/entidad**, **WorldPop 100 m** y **GHSL** (vía GWIS WMS `ghsl`), (2) estado de carpeta y caminos forestales con **Red Vial MOP** + vías sin pavimentar de **OSM**, y (3) completar la evaluación legal/UX antes de publicar capas de **SENAPRED Visor GRD** (`PUNTO_ENCUENTRO` / `VIAS_EVAC`) y **CONAF Cortafuegos**.

## Contexto

- Hoy `web/data/censo_2024.json` solo entrega totales comunales (`mapa.md` §4.E.12–13) y el mapa no distingue rutas pavimentadas de ripio/tierra o pistas forestales (`mapa.md` §4.J.22).
- **Reglas de prudencia obligatorias:**
  - Las capas de población censal son estrictamente agregadas por manzana/entidad o grilla, sin datos personales.
  - Según `INV-24` (`mapa.md` §4.G.16), `PUNTO_ENCUENTRO` y `VIAS_EVAC` de SENAPRED Visor GRD corresponden hoy a **tsunami y actividad volcánica**, NO a evacuación por incendio forestal, y carecen de licencia escrita explícita; no deben mostrarse sin autorización/licencia aclarada y sin rotulación inequívoca («Solo referencia tsunami/volcán; en incendio sigue la instrucción vigente de SENAPRED») para no inducir a error en una emergencia.
  - CONAF Cortafuegos carece de capa nacional única continua en GeoJSON/WMS; requiere verificar disponibilidad por temporada antes de publicar (`mapa.md` §4.G.17).
- Los datasets estáticos pesados (manzanas Censo 2024, WorldPop, Red Vial MOP) deben empaquetarse en PMTiles/GeoJSON en R2 (`'self'`).

## Archivos

- `scripts/` (preprocesamiento de manzanas Censo 2024, WorldPop/Red Vial MOP hacia PMTiles en R2)
- `web/js/map.js`, `web/js/capas.js` y `web/js/views/mapa.js` (capas opcionales GHSL/Censo/Vialidad en grupo Contexto/Exposición)
- `web/js/views/incendio.js` (estimación agregada de población cercana cuando exista dato fino)
- `docs/investigacion/` (seguimiento legal/técnico de `Visor GRD` y `Cortafuegos` antes de activarlos), `web/data/licencias.json`, `docs/FUENTES.md` y `tests/`

## Criterio de listo

- GHSL (vía GWIS WMS) y/o las capas preprocesadas en R2 se encienden de forma opcional con atribución completa y degradación limpia sin R2.
- Ningún dato de evacuación de tsunami/volcán (`Visor GRD`) se muestra como ruta de evacuación de incendio, ni se publica sin resolver su estado legal y advertencia UX.
- CI en verde (`pytest`, revisión JS y `e2e`).

## Fuente y licencia

- **Nombre:** INE Chile Censo 2024, WorldPop, Comisión Europea JRC GHSL (vía GWIS), Dirección de Vialidad MOP, OpenStreetMap, SENAPRED Visor GRD y CONAF Cortafuegos.
- **Enlace:** <https://censo2024.ine.gob.cl/resultados/> · <https://www.worldpop.org/> · <https://maps.effis.emergency.copernicus.eu/gwis> · `https://rest-sit.mop.gob.cl/arcgis/rest/services/VIALIDAD/Red_Vial_Chile/MapServer` · <https://visorchilepreparado.cl/> · <https://sit.conaf.cl/>.
- **Licencia:** **CC BY-SA 4.0** para INE Censo 2024 (<https://www.ine.gob.cl/terminos-de-uso-y-licencia-de-datos-abiertos>); **CC BY 4.0** para WorldPop; reutilización abierta Comisión Europea/JRC para GHSL; **ODbL** para OpenStreetMap; **licencia por confirmar** para Red Vial MOP en <https://geomop.mop.gob.cl/>, para SENAPRED Visor GRD en <https://visorchilepreparado.cl/> (pendiente consulta `INV-24`) y para CONAF Cortafuegos en <https://sit.conaf.cl/>.

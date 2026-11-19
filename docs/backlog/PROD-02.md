---
id: PROD-02
repo: brasas
rama: feat/salida-unica-y-puntos-agua-osm
modelo: agente-alto
riesgo: B
archivos: backend/providers/overpass.py, scripts/, web/js/views/incendio.js, web/js/views/zona.js, web/js/map.js, docs/FUENTES.md, tests/
e2e: si
---

# PROD-02 · Aviso de «salida única» (callejones sin salida) y puntos de agua cercanos al incendio (OSM)

## Objetivo

Identificar y mostrar en la ficha de incidente (`incendio.js`), «Mi zona» (`zona.js`) y como capa/marcadores opcionales en el mapa los tramos de **salida única / callejón sin salida** (`dead-ends` viales en interfaz urbano-forestal) y **puntos de agua** (grifos, estanques, reservorios, cuerpos de agua) cercanos al foco a partir de OpenStreetMap (`ODbL`).

## Contexto

- En sectores de interfaz rural/quebradas (como Viña del Mar, Quilpué o Santa Juana), quedar en un pasaje o camino forestal con un solo acceso es uno de los mayores riesgos durante una evacuación (`CONSOLIDADO.md` §4 y `mapa.md` §4.J.22).
- Asimismo, mostrar hidrantes (`emergency=fire_hydrant`), estanques (`emergency=water_tank`) y reservorios ayuda tanto a vecinos como a voluntarios a orientar el entorno.
- Debe presentarse siempre con lenguaje prudente (sin sustituir ni contradecir rutas de evacuación oficiales de SENAPRED) y cacheado/pre-extraído para no sobrecargar la API pública de Overpass.

## Archivos

- `backend/providers/overpass.py` y `scripts/` (extracción de nodos terminales de grado topológico 1 en zonas WUI y puntos de agua OSM)
- `web/js/views/incendio.js`, `web/js/views/zona.js` y `web/js/map.js` (aviso claro de vías con acceso único cercano y marcadores opcionales de agua)
- `docs/FUENTES.md` y `tests/`

## Criterio de listo

- Cuando existen datos pre-extraídos o cacheados en el radio del incidente/lugar, se advierten tramos de salida única y puntos de agua cercanos con atribución `© OpenStreetMap contributors` (ODbL).
- El texto deja explícito que la cobertura de OSM puede ser incompleta y que en emergencia rigen las indicaciones oficiales de SENAPRED y Carabineros.
- CI en verde (`pytest`, revisión JS y `e2e`).

## Fuente y licencia

- **Nombre:** OpenStreetMap (red vial `highway=*` y elementos `emergency=fire_hydrant` / `water_tank` vía Overpass / Geofabrik Chile).
- **Enlace:** <https://overpass-api.de/> · <https://download.geofabrik.de/south-america/chile.html>.
- **Licencia:** **ODbL** (<https://www.openstreetmap.org/copyright>).

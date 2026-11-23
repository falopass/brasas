---
id: MAPA-189
repo: brasas
rama: feat/terreno-3d-maplibre-y-aws-terrain
modelo: agente-alto
riesgo: B
archivos: web/js/map.js, web/js/capas.js, web/js/views/mapa.js, web/data/licencias.json, docs/FUENTES.md, tests/
e2e: si
---

# MAPA-189 · Terreno 3D nativo en MapLibre sobre Mapterhorn GLO-30 y respaldo AWS Terrain Tiles (z13–15)

## Objetivo

Habilitar terreno 3D opcional nativo en MapLibre GL JS v5.24.0 (`map.setTerrain`) aprovechando la fuente DEM de Mapterhorn (`Copernicus DEM GLO-30`, z0–12) ya cargada para `hillshade`, y añadir AWS Terrain Tiles (`s3.amazonaws.com/elevation-tiles-prod/terrarium`, z0–15) como respaldo automático y extensión de detalle entre zoom 13 y 15 en quebradas críticas (Valparaíso, Maule, Biobío), sin cargar CesiumJS.

## Contexto

- Hoy `web/js/map.js` utiliza Mapterhorn solo como sombreado plano (`hillshade`), a pesar de que MapLibre GL JS v5 soporta `setTerrain` de forma nativa (`mapa.md` §4.C.8).
- Permitir inclinar la vista en 3D ayuda a comprender pendientes de propagación del fuego y rutas de evacuación en quebradas, manteniendo un interruptor limpio (y apagado en modo ahorro de batería / 2D por defecto).
- Si se cierra la CSP en `SEC-15`, incluir `https://s3.amazonaws.com` en `img-src`/`connect-src` si se usa AWS Terrain Tiles.

## Archivos

- `web/js/map.js` (activación conmutable de `setTerrain`, inclinación suave y fallback DEM a AWS Terrain Tiles en z13–15 o ante error de Mapterhorn)
- `web/js/capas.js` y `web/js/views/mapa.js` (control en panel de relieve/capas y atribución)
- `web/data/licencias.json`, `docs/FUENTES.md` y `tests/`

## Criterio de listo

- Al activar relieve 3D en el mapa, el terreno toma elevación real sin instalar librerías externas y puede volver a plano 2D en un toque.
- Ante fallo simulado de Mapterhorn (o en zoom 13–15 si se habilita), el DEM conmuta limpiamente a AWS Terrain Tiles con atribución visible.
- CI en verde (`pytest`, revisión JS y `e2e`).

## Fuente y licencia

- **Nombre:** Mapterhorn (Copernicus DEM GLO-30) y AWS Terrain Tiles (Mapzen/Tilezen Joerd — SRTM/GMTED2010 USGS).
- **Enlace:** <https://mapterhorn.com/attribution/> · `https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png` (<https://registry.opendata.aws/terrain-tiles/>).
- **Licencia:** Copernicus DEM GLO-30 abierto con cita (`© Mapterhorn · Copernicus DEM GLO-30`) y dominio público USGS / atribución multi-fuente Tilezen Joerd para AWS Terrain Tiles (ver `docs/investigacion/INV-29-relieve.md`).

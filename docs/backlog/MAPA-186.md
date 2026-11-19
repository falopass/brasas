---
id: MAPA-186
repo: brasas
rama: feat/cicatrices-historicas-cr2-1984-2018
modelo: agente-alto
riesgo: C
archivos: scripts/, web/js/views/casos.js, web/js/map.js, web/data/licencias.json, docs/FUENTES.md, tests/
e2e: no
---

# MAPA-186 · Cicatrices históricas y severidad de quema CR2 (1984–2018)

## Objetivo

Incorporar la base histórica de más de 8.000 cicatrices de incendios reconstruidas con Landsat y severidad (`NBR`/`RdNBR`) del Centro de Ciencia del Clima y la Resiliencia (CR2, 1984–2018) como insumo para casos históricos (`casos.js`) y subcapa opcional de recurrencia multi-década en el mapa o R2.

## Contexto

- Los perímetros GEPRIF de CONAF (`MAPA-182`) cubren desde 2014; la base `(CR)2 Landscape Fire Scars Database Chile (1984–2018)` completa la historia previa a 2014 y añade severidad espectral de daño al suelo.
- Debe pre-procesarse en un script reproducible hacia GeoJSON simplificado o PMTiles en R2 para no superar los límites de tamaño del repositorio ni depender de descargas pesadas en tiempo real.

## Archivos

- `scripts/` (descarga, simplificación y verificación de esquema desde PANGAEA/DataClima hacia R2 o artefacto compacto)
- `web/js/views/casos.js` y `web/js/map.js` (subcapa histórica opcional o filtro por década cuando exista R2)
- `web/data/licencias.json`, `docs/FUENTES.md` y `tests/`

## Criterio de listo

- La cita académica (`Miranda et al. / (CR)2 · Landscape Fire Scars Database Chile (1984–2018)` y DOI) y la licencia verificada en el metadato del DOI quedan registradas en `docs/FUENTES.md` y `web/data/licencias.json`.
- El tamaño del arranque y vistas bajo demanda no crece por encima de los presupuestos del repo (`peso_arranque.py` y `presupuesto_peso.py`).
- CI en verde (`pytest`, revisión JS).

## Fuente y licencia

- **Nombre:** (CR)2 Landscape Fire Scars Database Chile (1984–2018), Miranda et al.
- **Enlace:** <https://doi.org/10.1594/PANGAEA.941127> (visor en <https://www.plataformadedatos.cl/> / <https://www.cr2.cl/dataclima/>).
- **Licencia:** Licencia por confirmar en el metadato exacto del DOI <https://doi.org/10.1594/PANGAEA.941127> (habitualmente CC BY 4.0 en PANGAEA; verificar antes de ingerir y publicar).

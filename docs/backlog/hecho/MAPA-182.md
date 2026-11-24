---
id: MAPA-182
repo: brasas
rama: feat/conaf-perimetros-reales-scars
modelo: agente-alto
riesgo: B
archivos: scripts/, web/data/scars.json, web/js/map.js, web/js/views/zona.js, web/js/views/casos.js, docs/FUENTES.md, tests/
e2e: si
---

# MAPA-182 · Perímetros reales de CONAF 2014–2024 en `scars.json` / PMTiles

## Objetivo

Reemplazar los cuadrados orientativos presentes en `web/data/scars.json` por los polígonos reales del servicio `PERÍMETROS_HISTORICOS_2014_2024_CON_SEMANA_DEL_AÑO` (y `PUNTOS_DE_INICIO_2002_2024_MAYOR_A_50_HA` como contexto para Historia/Casos) del catálogo público GEPRIF de CONAF, mejorando tanto la visualización de cicatrices en el mapa como la precisión del cruce espacial de riesgo de aluvión post-incendio.

## Contexto

- En `main`, `web/data/scars.json` contiene 11 entradas donde la mayoría son cuadrados aproximados (`El polígono es un cuadrado del orden de esa superficie`), lo que distorsiona la lectura en quebradas y laderas en `mapa.js` y en `terrenoNota` de `zona.js`.
- Los polígonos reales se exportan y simplifican a tolerancia adecuada hacia `web/data/scars.json` o PMTiles en R2 (`'self'`), evitando llamadas directas al servidor ArcGIS de CONAF en tiempo real.
- Mantener el presupuesto de peso de `web/data/` (o servir geometría pesada en R2/carga diferida bajo demanda).

## Archivos

- `scripts/` (script reproducible de descarga desde FeatureServer de CONAF, simplificación geométrica y generación de artefacto estático)
- `web/data/scars.json` (o índice compacto + polígonos en R2 si excede presupuesto del repo)
- `web/js/map.js`, `web/js/views/zona.js` y `web/js/views/casos.js`
- `docs/FUENTES.md` y `tests/test_data_files.py`

## Criterio de listo

- Ningún incendio 2014–2024 cubierto por el servicio oficial de CONAF se dibuja como cuadrado sintético cuando existe su perímetro real.
- El peso del arranque y vistas bajo demanda permanece dentro de los umbrales de `peso_arranque.py` y `presupuesto_peso.py`.
- La capa mantiene atribución visible a CONAF y enlace al catálogo GEPRIF.
- CI en verde (`pytest`, revisión JS y `e2e`).

## Fuente y licencia

- **Nombre:** Corporación Nacional Forestal (CONAF) — Catálogo GEPRIF (`PERÍMETROS_HISTORICOS_2014_2024_CON_SEMANA_DEL_AÑO` y `PUNTOS_DE_INICIO_2002_2024_MAYOR_A_50_HA`).
- **Enlace:** `https://services5.arcgis.com/A1ELWse9bRAi2JiV/arcgis/rest/services/PER%C3%8DMETROS_HISTORICOS_2014_2024_CON_SEMANA_DEL_A%C3%91O/FeatureServer/0/query` (<https://deigeprif.com/>).
- **Licencia:** Uso público citando a CONAF (criterio `OFI-03` documentado en [`docs/FUENTES.md`](../FUENTES.md) y [`PASOS_DUENO.md`](PASOS_DUENO.md)).

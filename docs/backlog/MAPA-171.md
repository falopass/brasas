---
id: MAPA-171
repo: brasas
rama: feat/conaf-wui-espacial-respaldo
modelo: agente-alto
riesgo: B
archivos: backend/providers/conaf.py, web/js/map.js, web/js/capas.js, web/js/views/mapa.js, web/data/licencias.json, docs/FUENTES.md, tests/
e2e: si
---

# MAPA-171 · Capa espacial Interfaz Urbano-Forestal (CONAF `riesgo_interfaz_tiled`) y respaldo `incendios_base`

## Objetivo

Incorporar al mapa la capa espacial de Zonas de Interfaz Urbano-Forestal (`riesgo_interfaz_tiled`) del catálogo GEPRIF de CONAF para visualizar directamente la franja donde la vegetación forestal toca áreas pobladas, y añadir `incendios_base` como respaldo automático en `backend/providers/conaf.py` por si falla la descarga de `incendios.csv`.

## Contexto

- Hoy `web/data/interfaz.json` guarda únicamente hectáreas y porcentaje agregado por comuna; en el mapa no se puede ver si un foco o vivienda cae exactamente en la zona WUI.
- En el catálogo público `A1ELWse9bRAi2JiV` ya documentado en `docs/FUENTES.md#L171`, `riesgo_interfaz_tiled` expone las teselas espaciales oficiales y `incendios_base` duplica la tabla de incendios activos cuando el CSV falla (`fuentes-meteologix-geprif.md`).
- Si se cierra la CSP en `SEC-15`, incluir `https://services5.arcgis.com` / `https://vectortileservices5.arcgis.com` (o servir una exportación simplificada desde R2/`'self'`).

## Archivos

- `web/js/map.js`, `web/js/capas.js` y `web/js/views/mapa.js` (capa opcional WUI bajo el grupo Prevención/Contexto con leyenda e indicación de fuente)
- `backend/providers/conaf.py` (fallback a `incendios_base` en caso de fallo del CSV público)
- `web/data/licencias.json`, `docs/FUENTES.md` y `tests/`

## Criterio de listo

- Al activar la capa de Interfaz Urbano-Forestal en el mapa se muestran las áreas WUI con atribución `CONAF · GEPRIF Zonas de Interfaz`.
- Ante un fallo simulado del CSV de incendios en pruebas unitarias, `conaf.py` recurre limpiamente a `incendios_base` conservando unidades y normalización de coordenadas.
- CI en verde (`pytest`, revisión JS y `e2e`).

## Fuente y licencia

- **Nombre:** Corporación Nacional Forestal (CONAF) — Tablero GEPRIF «Zonas Interfaz» (`riesgo_interfaz_tiled`) e `incendios_base`.
- **Enlace:** `https://services5.arcgis.com/A1ELWse9bRAi2JiV/arcgis/rest/services?f=pjson` (<https://deigeprif.com/>).
- **Licencia:** Uso público citando a CONAF (criterio `OFI-03` documentado en [`docs/FUENTES.md`](../FUENTES.md); el CSV público mantiene autorización formal escrita pendiente).

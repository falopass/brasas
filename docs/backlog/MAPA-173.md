---
id: MAPA-173
repo: brasas
rama: feat/uso-suelo-worldcover-y-catastro-conaf
modelo: agente-alto
riesgo: B
archivos: web/js/map.js, web/js/capas.js, web/js/views/mapa.js, web/data/licencias.json, docs/FUENTES.md, tests/
e2e: si
---

# MAPA-173 · Capas de uso de suelo y combustible: ESA WorldCover 10 m y Catastro CONAF (IDE Minagri)

## Objetivo

Añadir capas opcionales de contexto de combustible al mapa (`mapa.js` y `capas.js`): **ESA WorldCover 10 m** (`WORLDCOVER_2021_MAP` vía WMS Terrascope, continua y rápida) para visualizar cobertura arbórea, matorral y pastizal alrededor de un foco, y el **Catastro de Uso de Suelo y Vegetación de CONAF** (IDE Minagri / CIREN) para distinguir plantaciones forestales altamente inflamables (pino/eucalipto) de bosque nativo.

## Contexto

- Hoy el mapa no muestra el tipo de cobertura o combustible que rodea un foco activo, y el cálculo FWI trata todo Chile con el mismo modelo estándar de pastizal.
- ESA WorldCover 10 m responde por WMS `1.3.0` en `EPSG:3857` sin clave ni backend bajo **CC BY 4.0**.
- El WMS oficial de CONAF (`esri.ciren.cl/server/services/USOS_DE_LA_TIERRA__CONAF/MapServer/WMSServer`) puede sufrir latencia en servidores estatales; conviene evaluar latencia/CORS desde Cloudflare y, si no responde rápido en emergencia, generar teselas o PMTiles estáticos en R2.
- Si se cierra la CSP en `SEC-15`, incluir `https://services.terrascope.be` (y `https://esri.ciren.cl` si se consume directo).

## Archivos

- `web/js/map.js`, `web/js/capas.js` y `web/js/views/mapa.js` (capas opcionales apagadas por defecto en grupo Contexto/Combustible, con leyenda cromática clara y atribución)
- `web/data/licencias.json`, `docs/FUENTES.md` y `tests/`

## Criterio de listo

- Al encender ESA WorldCover en el mapa se muestran las coberturas sobre Chile con atribución completa `© ESA WorldCover project 2021` (CC BY 4.0).
- Si se integra el Catastro CONAF (directo o cacheado en R2), se distingue explícitamente bosque nativo frente a plantación forestal con fuente citada y degradación silenciosa ante lentitud del servidor.
- CI en verde (`pytest`, revisión JS y `e2e`).

## Fuente y licencia

- **Nombre:** ESA WorldCover 10 m (Terrascope WMS) y Catastro de Uso de Suelo y Recursos Vegetacionales de CONAF (IDE Minagri / CIREN).
- **Enlace:** `https://services.terrascope.be/wms/v2` (<https://esa-worldcover.org/>) · `https://esri.ciren.cl/server/services/USOS_DE_LA_TIERRA__CONAF/MapServer/WMSServer` (<https://ide.minagri.gob.cl/>).
- **Licencia:** **CC BY 4.0** para ESA WorldCover; para el servicio WMS de IDE Minagri / CIREN, **licencia por confirmar** en <https://ide.minagri.gob.cl/> (verificar términos del servicio CIREN antes de publicar consumo directo o copia en R2).

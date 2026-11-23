---
id: OFI-34
repo: brasas
rama: feat/gwis-capas-wms
modelo: agente-alto
riesgo: B
archivos: web/js/map.js, web/js/capas.js, web/js/views/mapa.js, web/data/licencias.json, docs/FUENTES.md, .github/scripts/fuentes_salud.py, tests/
e2e: si
---

# OFI-34 · GWIS en capas WMS (anomalía de peligro y área quemada reciente)

## Objetivo

Incorporar en el mapa capas raster opcionales del sistema global GWIS/EFFIS (`ecmwf.ranking` —y/o `ecmwf.fwi`— para mostrar qué tan inusual es el peligro de incendio de hoy frente a ~40 años de clima, y `nrt.ba` / `nrt.ba.poly.month` para área quemada reciente NRT), apagadas por defecto y sin consumo de backend ni clave. Los focos activos de GWIS no se integran porque republicarían NASA FIRMS con ~1 día de rezago.

## Contexto

- Investigación previa verificada en [`docs/investigacion/INV-27-gwis.md`](../investigacion/INV-27-gwis.md) y confirmada en `CONSOLIDADO.md`, `atmosfera.md` y `mapa.md`.
- El servicio MapServer WMS 1.1.1 en `https://maps.effis.emergency.copernicus.eu/gwis` responde con `Access-Control-Allow-Origin: *` y soporta `EPSG:3857` en tiles de 512 px (`STYLES=` obligatorio aunque vaya vacío).
- Debe ser mutuamente excluyente con las demás coropletas territoriales (`risk`, `rain`, `senapred`) en `web/js/capas.js`, mostrarse siempre rotulada como contexto externo («según GWIS/ECMWF», nunca como nivel propio de BRASA ni como alerta) y declarar fecha del parámetro `TIME` cuando aplique.
- Si se cierra la CSP en `SEC-15`, incluir `https://maps.effis.emergency.copernicus.eu` en `img-src` / `connect-src`.

## Archivos

- `web/js/map.js` (fuentes raster WMS `EPSG:3857` y capas bajo puntos)
- `web/js/capas.js` (registro en `CAPAS`, URL compartible y exclusiones entre coropletas)
- `web/js/views/mapa.js` (interruptores en el grupo Contexto, leyenda con fecha y atribución)
- `web/data/licencias.json` y `docs/FUENTES.md`
- `.github/scripts/fuentes_salud.py` (sonda semanal `GetCapabilities` para detectar renombres de capas)
- `tests/` (pruebas de `capas.js` y formato de URL WMS)

## Criterio de listo

- Al encender «Peligro GWIS (ECMWF)» o «Área quemada NRT (GWIS)» en el mapa se muestran las teselas sobre Chile, apagando las demás coropletas excluyentes.
- La leyenda y atribución muestran nombre de la fuente, enlace, licencia CC BY 4.0, declaración de que no modifica los datos y fecha consultada (`TIME` cuando corresponda).
- Un fallo del servidor WMS no rompe el mapa ni las demás capas.
- `.github/scripts/fuentes_salud.py` verifica `GetCapabilities` de GWIS.
- CI en verde (`pytest`, revisión JS y `e2e`).

## Fuente y licencia

- **Nombre:** Global Wildfire Information System (GWIS / EFFIS — Comisión Europea, JRC / Copernicus).
- **Enlace:** `https://maps.effis.emergency.copernicus.eu/gwis` (catálogo en <https://gwis.jrc.ec.europa.eu/applications/data-and-services>).
- **Licencia:** **CC BY 4.0** (<https://gwis.jrc.ec.europa.eu/about-gwis/data-license>), con atribución a la Unión Europea / GWIS y declaración de que las teselas no modifican el dato original.

---
id: MAPA-184
repo: brasas
rama: feat/mapa-offline-respaldo-precacheados
modelo: agente-alto
riesgo: B
archivos: web/js/map.js, web/js/views/mapa.js, web/js/mapa-offline.js, web/sw.js, tests/
e2e: si
---

# MAPA-184 · Modo sin conexión en el mapa: cambio a mapa guardado, bordes comunales y precaché de capas estáticas

## Objetivo

Mejorar la experiencia sin señal en terreno (`mapa.md` §5.6): ofrecer cambio directo (o automático ante fallo total del raster) hacia las teselas vectoriales guardadas cuando la persona usaba `Satélite` o `Topográfico`, dibujar siempre `comunas-line` como respaldo offline, precachear en segundo plano los JSON estáticos de terreno (`snaspe.json`, `scars.json`, `interfaz.json`, `localidades.json`) y dar acceso directo a «Guardar zona visible sin señal» desde `#map-layers`.

## Contexto

- Hoy `web/js/mapa-offline.js` guarda únicamente teselas de OpenFreeMap (`tiles.openfreemap.org`). Si la persona pierde conexión usando `Satélite` (EOxCloudless) o `Topográfico` (OpenTopoMap), `web/js/map.js:107-111` solo dibuja `offline-chile` (silueta de regiones) sin límites comunales ni botón de cambio rápido.
- En `web/sw.js:4-22`, archivos locales versionados en `/web/data/` como `snaspe.json`, `scars.json`, `localidades.json` e `interfaz.json` no están precacheados si la persona no abrió esas capas antes de salir a terreno.
- La descarga offline hoy solo se encuentra en Privacidad, oculta para quien está mirando el mapa antes de viajar.
- Recuerda la regla crítica de `AGENTS.md`: cualquier cambio en `web/sw.js` obliga a pasar en verde todas las pruebas de reportes y e2e en el CI.

## Archivos

- `web/js/map.js` (`comunas-line` visible en modo offline y manejo de cambio al mapa vectorial guardado)
- `web/js/views/mapa.js` (botón «Cambiar a mapa guardado sin señal» en `#capas-offline`/toast y acceso directo «Guardar zona visible sin señal» en `#map-layers`)
- `web/js/mapa-offline.js` (soporte para descargar/verificar teselas del área visible desde el mapa)
- `web/sw.js` (precaché diferido post-instalación para `snaspe.json`, `scars.json`, `interfaz.json` y `localidades.json` sin bloquear el evento `install`)
- `tests/`

## Criterio de listo

- Con teselas guardadas en `brasa-tiles`, al simular modo offline estando en `Satélite` o `Topográfico` se ofrece el cambio directo (o automático si falla el raster) al mapa guardado y permanecen visibles los límites comunales.
- Los archivos `snaspe.json`, `scars.json`, `interfaz.json` y `localidades.json` quedan disponibles offline tras instalar el Service Worker sin penalizar `install` ni el presupuesto de arranque.
- Desde `#map-layers` se puede iniciar o revisar la descarga offline de la zona visible.
- CI en verde (`pytest` incluidas pruebas de reportes y SW, revisión JS y `e2e`).

## Fuente y licencia

- **Nombre:** Auditoría UX y modo sin conexión del mapa (`mapa.md` §5.6 y `CONSOLIDADO.md` §3).
- **Enlace:** `web/sw.js`, `web/js/map.js`, `web/js/mapa-offline.js` y `web/js/views/mapa.js` en el repositorio.
- **Licencia:** N/A (código propio y datos ya versionados en el proyecto).

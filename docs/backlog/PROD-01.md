---
id: PROD-01
repo: brasas
rama: feat/paquete-sin-senal-comuna
modelo: agente-alto
riesgo: B
archivos: web/js/mapa-offline.js, web/js/views/privacidad.js, web/js/views/preparate.js, web/js/views/mapa.js, web/sw.js, tests/
e2e: si
---

# PROD-01 · «Paquete sin señal» por comuna

## Objetivo

Ofrecer en un toque la descarga del **«Paquete sin señal»** de una comuna o lugar guardado: geometría comunal y límite urbano, servicios cercanos (bomberos, salud, escuelas), puntos de agua si están disponibles y la guía práctica «¿Qué hago si…?» de `preparate.js`, para consultarlos en terreno sin cobertura celular.

## Contexto

- Hoy `web/js/mapa-offline.js` descarga teselas de OpenFreeMap desde Privacidad, pero no empaqueta en un solo flujo los datos de emergencia locales de la comuna ni la guía de autoprotección (`CONSOLIDADO.md` §4).
- Conviene integrarlo con `MAPA-172` (acceso rápido desde `#map-layers` y precaché de capas estáticas) respetando el presupuesto de almacenamiento del dispositivo y la regla de `AGENTS.md` sobre cambios en `web/sw.js` (todas las pruebas de reportes + e2e en verde).

## Archivos

- `web/js/mapa-offline.js` (descarga y seguimiento de tamaño del paquete comunal)
- `web/js/views/mapa.js`, `web/js/views/privacidad.js` y `web/js/views/preparate.js` (botón unificado «Guardar paquete sin señal» y consulta offline)
- `web/sw.js` y `tests/`

## Criterio de listo

- Una persona puede descargar en un paso el paquete sin señal de su comuna/lugar guardado con progreso visible y botón para borrarlo.
- En modo sin conexión se muestran los límites de la comuna, servicios guardados y la guía «¿Qué hago si…?».
- CI en verde (`pytest` incluidas pruebas de reportes y SW, revisión JS y `e2e`).

## Fuente y licencia

- **Nombre:** Propuesta de producto de la revisión interna (`CONSOLIDADO.md` §4), apoyada en datos comunales propios, guía `preparate.js` y servicios OSM (ODbL).
- **Enlace:** `web/js/mapa-offline.js` y `web/js/views/preparate.js` en el repositorio.
- **Licencia:** N/A (código propio del proyecto; infraestructura OSM bajo **ODbL** <https://www.openstreetmap.org/copyright>).

---
id: OFI-36
repo: brasas
rama: feat/dmc-lluvia-presion-ema
modelo: agente-alto
riesgo: B
archivos: backend/providers/dmc_stations.py, backend/services.py, backend/routes/personal.py, web/js/views/zona.js, docs/FUENTES.md, tests/
e2e: no
---

# OFI-36 · Lluvia medida y presión en estaciones EMA de DMC (más series de 12 h y olas de calor)

## Objetivo

Extraer la precipitación medida (`aguaCaida`) y presión atmosférica del payload que `backend/providers/dmc_stations.py` ya descarga de `getDatosRecientesRedEma` sin aumentar peticiones, y evaluar el consumo acotado de `getDatosRecientesEma/{codigoNacional}` (serie de 12 h para lluvia acumulada en 3 h/24 h) y `getOlasDeCalorRecientes` usando la credencial existente (`DMC_USUARIO`/`DMC_TOKEN`).

## Contexto

- Hoy `dmc_stations.py:51-76` lee solo temperatura, humedad relativa y viento de `getDatosRecientesRedEma`, descartando la lluvia medida que aporta verificación directa en terreno para el cruce de aluvión post-incendio (`AGUA-04`) y la calibración de humedad del FWI.
- Todo se apoya en las credenciales `DMC_USUARIO` / `DMC_TOKEN` y el caché compartido ya existentes en producción, sin peticiones por visita de usuario.

## Archivos

- `backend/providers/dmc_stations.py` (parseo de lluvia/agua caída y presión en `latest_network`, y métodos opcionales cacheados para serie 12 h / olas de calor)
- `backend/services.py` y `backend/routes/personal.py` (exponer lluvia medida de la estación cercana junto al aviso de aluvión y estación real en «Mi zona»)
- `web/js/views/zona.js` (mostrar «Lluvia medida en estación DMC a X km» cuando exista dato reciente)
- `docs/FUENTES.md` y `tests/`

## Criterio de listo

- `dmc_stations.latest_network` devuelve precipitación medida y presión cuando están presentes en el JSON de `getDatosRecientesRedEma`, sin fallar si vienen nulos o con guiones.
- En «Mi zona», el bloque de estación cercana y la sección de lluvia/aluvión muestran el acumulado medido real con nombre de estación, hora de Chile continental y enlace oficial.
- CI en verde (`pytest`).

## Fuente y licencia

- **Nombre:** Dirección Meteorológica de Chile (DMC) — Red de Estaciones Meteorológicas Automáticas (RE8011).
- **Enlace:** `https://climatologia.meteochile.gob.cl/application/servicios/getDatosRecientesRedEma` (<https://climatologia.meteochile.gob.cl/>).
- **Licencia:** Licencia por confirmar para los servicios JSON de Climatología (requieren registro gratuito con `usuario`/`token` y atribución obligatoria a DMC; verificar términos de reutilización abierta en <https://climatologia.meteochile.gob.cl/>; los avisos CAP 1.2 XML de `dmc.py` son de dominio público).

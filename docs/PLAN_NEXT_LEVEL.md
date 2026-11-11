# Plan «next level»: de puntos de calor a evidencia, riesgo explicado y decisiones seguras

Aprobado el 18 de octubre de 2026 a partir de cinco documentos de investigación (dos informes HTML interactivos, `Incendios_y_Clima_en_Chile.md`, `deep-research-report.md` y su PDF). Este archivo es la fuente de verdad del avance: marca ✅ lo terminado y anota cualquier desvío del plan original. Última sincronización con `main`: 11 de noviembre de 2026; evidencia de la ola del 4 al 8 de noviembre en `docs/cierre-brasa-2026-11-08.md` y del barrido del 11-11 en su última sección.

## Contexto

Los documentos coinciden en tres ideas que BRASA v0.5 no resolvía:

1. **Un punto de calor no es un incendio**, un incendio no es un perímetro y un perímetro no es una predicción. Hacía falta el **incidente**: agrupar evidencia, darle un estado y mostrar su línea de tiempo y procedencia.
2. **El riesgo debe separarse y explicarse:** ignición ≠ propagación ≠ exposición. El Niño 2026-27 no es «más incendios» en línea recta: la *paradoja hidro-pirológica* (lluvia de invierno y primavera → más pasto → se seca en verano) eleva el riesgo de enero-febrero de 2027 entre Valparaíso y Los Lagos.
3. **Multiamenaza:** después del fuego vienen los **aluviones** (lluvia intensa e isoterma 0 °C alta sobre suelo quemado), justo en el otoño de 2027.

Ante una evacuación, la aplicación debe dejar el análisis y responder solo: ¿estoy dentro?, ¿qué dijo la autoridad?, ¿a qué hora?, ¿qué hago?

### Datos de los documentos que se corrigieron o se verificaron antes de usar

- **Valparaíso 2024:** los informes HTML decían 11.349 ha y 135 víctimas. Verificado: **138 fallecidos** (Fiscalía, mayo de 2025). La superficie depende del balance: más de 8.500 ha el complejo Las Tablas y más de 10.000 ha en total (CONAF, citada por la prensa). Ambas se muestran con fuente y fecha.
- **Botón Rojo:** no se publica un umbral propio; se usa directamente el pronóstico oficial de CONAF.
- **Mochila:** 2 L de agua por persona al día durante 2 a 3 días (antes decía 4 L).
- Los hechos «recientes» de los documentos generados (protocolos, aluviones, geoportales) no se citan sin una fuente oficial.

## Fase 1 — antes de diciembre: incidentes, modo emergencia y datos correctos ✅

| # | Entrega | Estado | Dónde |
|---|---|---|---|
| 1.1 | **Motor de incidentes:** tablas `incidents` e `incident_observations`, agrupación espacio-temporal según la resolución de cada sensor, fusión de incidentes, estados, vencimiento a las 24 h y fuentes fijas. Respaldo horario de `work.db` en R2. Los avisos mencionan el incidente y omiten las fuentes fijas. | ✅ | `backend/incidents.py`, `backend/storage.py`, `backend/alerts.py` |
| 1.2 | **Ficha de incidente** `#/incendio/<id>`: estado en palabras sencillas, evidencia por satélite con su latencia, reproducción hora a hora con el motor de los casos. Lista de posibles incendios y enlace desde cada punto del mapa. | ✅ | `web/js/views/incendio.js`, `backend/routes/public.py` |
| 1.3 | **Fuentes oficiales:** Botón Rojo de CONAF (pronóstico a 5 días por comuna) e incendios informados por CONAF (única vía a «confirmado»), con avisos «CONAF informa». | ✅ | `backend/providers/conaf.py`, `docs/FUENTES.md` |
| 1.4 | **Modo emergencia** en Mi zona y contenido de evacuación de SENAPRED en Prepárate. | ✅ | `web/js/views/zona.js`, `web/js/views/preparate.js` |
| 1.5 | **Historia:** `scope` y cifras como revisiones con fuente; Valparaíso 2024 corregido; casos nuevos: Penco–Lirquén 2026 (6.957 detecciones reales de GOES-19), Valparaíso 2014 y Torres del Paine 2011-12. | ✅ | `web/data/cases.json`, `web/js/views/casos.js` |

**Desvíos respecto del plan original**
- **Máscara de fuentes fijas:** en vez de un script sobre el archivo FIRMS 2023-2025, se usan los volcanes activos conocidos (`web/data/persistent_hotspots.json`, con su fuente) y una regla dinámica: celda de ~2 km con calor en ≥ 8 días distintos de los últimos 30. El script `scripts/build_persistent_mask.py` con FIRMS SP ya está en main (DET-05, PR #80 mergeado).
- **SENAPRED:** no tiene un servicio público de alertas. Su página usa una API GraphQL interna con credenciales incrustadas, que no se usa. El modo emergencia enlaza a senapred.cl. **Pendiente:** pedir acceso oficial.
- **Mapa:** los incidentes se listan y enlazan, su huella se ve en la ficha y el contorno se puede encender en el mapa principal (capa «Huellas de calor», `incident-hulls`; DET-10, PR #336).
- **Backtesting:** el banco de reproducción ya existe (QA-02, `scripts/replay_case.py`, PR #53) y la medida de Viña 2024 (cuándo el incidente pasa a «posible») está publicada en «Calidad de los datos» (QA-03, PR #290; datos en `web/data/cases/vina-del-mar-2024.goes.json`).

**Lo que no está en `main`:** el acceso oficial a las alertas de SENAPRED y la máscara de fuentes fijas revisada a mano y publicada (DET-05: el script está, falta la máscara).

## Fase 2 — diciembre a enero: riesgo explicado (BRASA Risk)

| # | Entrega | Estado |
|---|---|---|
| 2.1 | **FWI propio** (sistema canadiense): `backend/fwi.py` con FFMC, DMC, DC, ISI, BUI y FWI a partir de Open-Meteo diario (T y HR a las 13 h, viento, lluvia de 24 h), inicializado con el archivo desde el inicio de la temporada (1 de junio). Pruebas con los valores de referencia de Van Wagner. Se muestra junto al 30-30-30, no en su reemplazo, y el nivel de condiciones del día los combina (`risk.combine`: manda el más alto y, si los dos llegan a «alto», sube un paso). | ✅ | `backend/fwi.py`, `backend/risk.py`, `backend/providers/weather.py`, `web/js/views/riesgo.js` |
| 2.2 | **«Hay más pasto que se secará»:** anomalía de lluvia de junio a octubre de 2026 frente a la normal 1991-2020 por comuna (Open-Meteo archive/ERA5), con una frase sencilla y un mapa. | ✅ normales 1991-2020 versionadas en `web/data/rain_normals.json` (FIX-25, PR #88) y capa «Lluvia de la temporada» en el mapa (RISK-15, PR #142) | `backend/rain.py`, `web/data/rain_normals.json`, `web/js/views/mapa.js` |
| 2.3 | **Riesgo en 3 capas:** condiciones (FWI, 30-30-30, viento, Botón Rojo), combustible (anomalía de lluvia, cicatrices previas) y exposición (población INE 2024 e interfaz CONAF). Ranking «probabilidad × exposición» rotulado como aproximación de BRASA. Candidatas oficiales para «condiciones»: capas PI, HC, VV, HR y TP de CONAF (`docs/FUENTES.md`). | ✅ la ficha de comuna muestra las tres capas («1. Condiciones del día», «2. Combustible acumulado», «3. Exposición territorial») y el ranking conmuta a «Peligro × Exposición (estimación BRASA)», que pondera el puntaje por viviendas del Censo 2024, interfaz CONAF y campamentos del catastro MINVU (`web/js/views/riesgo.js`, `web/js/exposure.js`, PR #789 mergeado el 4-11). Las capas PI/HC/VV/HR/TP de CONAF ya informan «condiciones» (OFI-18). |
| 2.4 | **Panel El Niño en palabras:** estado ENSO del NOAA CPC (boletín semanal) y una explicación no lineal, sin la regla «El Niño = más incendios». | ✅ RISK-06 mergeado (PR #132): panel «El Pacífico y esta temporada» | `backend/providers/noaa.py`, `backend/routes/climate.py`, `web/js/views/riesgo.js` |
| 2.5 | **Viento animado:** capa de partículas en MapLibre con una grilla de Open-Meteo. | ✅ RISK-07, PR #700: `backend/windgrid.py`, `/api/wind/grid`, `web/js/viento.js` e interruptor «Viento». Desvío aprobado: grilla de 1° y refresco cada 6 h, cediendo cupo al pronóstico y FWI; flechas estáticas con movimiento reducido o ahorro de batería. |
| 2.6 | **Canales:** Telegram (requiere crear el bot con @BotFather) y evaluación de SMS para quien no tiene teléfono inteligente (requiere proveedor y presupuesto). | ⏳ Telegram **descartado** por el dueño el 3-11 (ALR-01); SMS y WhatsApp siguen pendientes de proveedor y presupuesto (ALR-06, ALR-07) |
| 2.7 | **Avisos de la DMC** (CAP 1.2, dominio público): calor extremo y viento por zona en el lugar y en Riesgo. Fuente: `archivos.meteochile.gob.cl/portaldmc/rss/rss.php`. | ✅ | `backend/providers/dmc.py`, `web/js/views/riesgo.js`, `web/js/views/zona.js` |

**Notas sobre el FWI (2.1)**
- Se usan las **tablas del hemisferio sur** (`ell03`/`ell04` y `fl02` de la formulación de Van Wagner): enero es verano en Chile. La variante «sin ajuste por latitud» que aparece en muchos ejemplos publicados supone el verano del norte y habría invertido las estaciones.
- El **DC usa el factor estacional** de la misma formulación; sin él, la sequía profunda se subestima en verano y se sobreestima en invierno.
- **Referencia de las pruebas:** los 48 días del ejemplo publicado, con los valores que reproduce el paquete `cffdrs` 1.9.2 (tabla de 40-55°N, sin ajuste). Copiarlos a mano habría metido erratas: se copiaron con suma SHA-256 comparada.
- **Constante:** el FFMC se convierte con `250 · 59,5 / 101 = 147,2772`, no con el 147,2 redondeado de los libros. Con 147,2 el código se desvía unas centésimas por día.
- **Límite de Open-Meteo:** el archivo de la temporada por 345 comunas exige volumen y cupo diario. El FWI se actualiza una vez al día en tandas de hasta 100 comunas por ciclo, con reintento tras 30 minutos si falla; el cron continúa el avance guardado. El 30-30-30 se recalcula por separado y no depende de que termine el FWI.

**Canales pendientes:** Telegram quedó descartado por el dueño el 3-11; SMS y WhatsApp esperan proveedor y presupuesto. El viento animado ya está en `main`.

## Fase 3 — febrero a abril: aluviones después del fuego (BRASA Agua) y transparencia

| # | Entrega | Estado |
|---|---|---|
| 3.1 | **Riesgo de aluvión:** huellas de calor, pendiente y pronóstico horario de lluvia con isoterma 0 °C. Umbrales calibrados el 11-11-2026; ver `docs/ALUVIONES.md` y `docs/aluvion-calibracion.md`. | ✅ el cruce de `/api/climate/lluvia` y «Mi zona» usa **huellas de los últimos 180 días a ≤ 5 km** del punto (`_scar_ha`, `backend/routes/climate.py`, PR #790), lluvia e isoterma (AGUA-03A, PR #186) y pendiente Copernicus **GLO-90** vía Open-Meteo (AGUA-02; desvío del GLO-30 previsto, PR #701). Las cicatrices históricas 2014-2024 de #796 se muestran como contexto separado: **no alimentan este cálculo**. El **aviso por lugar guardado ya está entregado** (AGUA-04): preferencia `aluvion_alerts` (#831), `alerts.evaluate_aluvion` con su pasada horaria y `lluvia.criterio_aviso` (#840), ida y vuelta por `/api/places` (#851). El criterio salió de la calibración con 180 días de lluvia real y **un solo evento de control** (Quebrada Honda, 8-oct-2026), con sus límites declarados en `docs/aluvion-calibracion.md` (#838). |
| 3.2 | **Página «Calidad de los datos»:** latencia p50/p90 por fuente, ingestas fallidas, frescura, incidentes y descartes. La ficha de incidente ya calcula la latencia por sensor. | ✅ página en `main` (`web/js/views/calidad.js`): estado por fuente (QA-05, PR #112), radar de respuesta oficial de CONAF (QA-21, PR #153), cumplimiento y latencia por fuente (QA-05, PR #201), medida de adelanto de Viña 2024 (QA-03, PR #290), cupo de FIRMS (DAT-01, PR #353) y Open-Meteo (CALIDAD-02, PR #499), desde el 4-11 la latencia p50/p95 por ruta de la última hora y la concordancia comuna-día del índice con CONAF (CALIDAD-OBS, RISK-09, PR #791; `/api/observability/routes` y `/api/observability/concordancia`), y los descartes por fuente (`/api/observability/descartes`, QA-3.2): lo que el parser dejó fuera por fuente y por qué, guardado por corrida en `ingest_runs.discards`. |
| 3.3 | **API pública de solo lectura** (incidentes, observaciones, riesgo por comuna) en GeoJSON, documentada. | ✅ sirve `/api/opendata` (`backend/routes/opendata.py`: incidentes, observaciones, riesgo, rayos GLM, cicatrices de la temporada y respuesta oficial en GeoJSON) y está documentada en `docs/API.md` con un test que la mantiene al día (PR #99) |

**Lo que no está en `main`:** el dNBR de Sentinel-2 y los caudales de la DGA.

## Fuera de alcance por ahora

- PostGIS, bus de eventos y STAC: correctos a escala nacional; hoy SQLite + shapely alcanza. Reevaluar con la API pública y más de 50 usuarios activos.
- Predicción de propagación: solo después de backtesting con 2017, 2023, 2024 y 2026, y siempre como «escenario estimado».
- Ubicación de brigadas o aeronaves: solo con un convenio oficial.

## Verificación de cada entrega

- Pruebas: `python dev.py check` (pytest, sintaxis JS y reglas de diseño).
- Navegador: `python dev.py e2e` (errores, CSP y textos cortados en 320, 390 y 1280 px).
- Producción: workflow **Diagnóstico de Cloudflare** después de cada despliegue: ciclo completo, `backup: true`, sin `failed_sources`, incidentes y fuentes de CONAF presentes.

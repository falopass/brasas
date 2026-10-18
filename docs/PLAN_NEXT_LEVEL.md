# Plan «next level»: de puntos de calor a evidencia, riesgo explicado y decisiones seguras

Aprobado el 18 de octubre de 2026 a partir de cinco documentos de investigación (dos informes HTML interactivos, `Incendios_y_Clima_en_Chile.md`, `deep-research-report.md` y su PDF). Este archivo es la fuente de verdad del avance: marca ✅ lo terminado y anota cualquier desvío del plan original.

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
- **Máscara de fuentes fijas:** en vez de un script sobre el archivo FIRMS 2023-2025, se usan los volcanes activos conocidos (`web/data/persistent_hotspots.json`, con su fuente) y una regla dinámica: celda de ~2 km con calor en ≥ 8 días distintos de los últimos 30. **Pendiente:** `scripts/build_persistent_mask.py` con FIRMS SP para sumar industrias conocidas.
- **SENAPRED:** no tiene un servicio público de alertas. Su página usa una API GraphQL interna con credenciales incrustadas, que no se usa. El modo emergencia enlaza a senapred.cl. **Pendiente:** pedir acceso oficial.
- **Mapa:** los incidentes se listan y enlazan, y su huella se ve en la ficha. **Pendiente:** dibujar el contorno de cada incidente en el mapa principal.
- **Backtesting:** reproducir Viña 2024 midiendo cuándo el incidente pasa a «posible» sigue **pendiente** (los datos ya están en `web/data/cases/vina-del-mar-2024.goes.json`).

## Fase 2 — diciembre a enero: riesgo explicado (BRASA Risk)

| # | Entrega | Estado |
|---|---|---|
| 2.1 | **FWI propio** (sistema canadiense): `backend/fwi.py` con FFMC, DMC, DC, ISI, BUI y FWI a partir de Open-Meteo diario (T y HR a las 13 h, viento, lluvia de 24 h), inicializado con 60 días de archivo. Pruebas con los valores de referencia de Van Wagner. Se muestra junto al 30-30-30, no en su reemplazo, y el nivel de condiciones del día los combina (`risk.combine`: manda el más alto y, si los dos llegan a «alto», sube un paso). | ✅ | `backend/fwi.py`, `backend/risk.py`, `backend/providers/weather.py`, `web/js/views/riesgo.js` |
| 2.2 | **«Hay más pasto que se secará»:** anomalía de lluvia de junio a octubre de 2026 frente a la normal 1991-2020 por comuna (Open-Meteo archive/ERA5), con una frase sencilla y un mapa. | 🔧 código y pruebas listos (`backend/rain.py`); normales 1991-2020 construyéndose por celda de 0,5° (trabajo único, `scripts/local/build_rain_normals.py`); ⏳ capa en el mapa | `backend/rain.py`, `scripts/local/build_rain_normals.py` |
| 2.3 | **Riesgo en 3 capas:** condiciones (FWI, 30-30-30, viento, Botón Rojo), combustible (anomalía de lluvia, cicatrices previas) y exposición (población INE 2024 e interfaz CONAF). Ranking «probabilidad × exposición» rotulado como aproximación de BRASA. Candidatas oficiales para «condiciones»: capas PI, HC, VV, HR y TP de CONAF (`docs/FUENTES.md`). | ⏳ |
| 2.4 | **Panel El Niño en palabras:** estado ENSO del NOAA CPC (boletín semanal) y una explicación no lineal, sin la regla «El Niño = más incendios». | ⏳ |
| 2.5 | **Viento animado:** capa de partículas en MapLibre con una grilla de Open-Meteo (0,25°). | ⏳ |
| 2.6 | **Canales:** Telegram (requiere crear el bot con @BotFather) y evaluación de SMS para quien no tiene teléfono inteligente (requiere proveedor y presupuesto). | ⏳ decisión de la persona dueña |
| 2.7 | **Avisos de la DMC** (CAP 1.2, dominio público): calor extremo y viento por zona en el lugar y en Riesgo. Fuente: `archivos.meteochile.gob.cl/portaldmc/rss/rss.php`. | ✅ | `backend/providers/dmc.py`, `web/js/views/riesgo.js`, `web/js/views/zona.js` |

**Notas sobre el FWI (2.1)**
- Se usan las **tablas del hemisferio sur** (`ell03`/`ell04` y `fl02` de la formulación de Van Wagner): enero es verano en Chile. La variante «sin ajuste por latitud» que aparece en muchos ejemplos publicados supone el verano del norte y habría invertido las estaciones.
- El **DC usa el factor estacional** de la misma formulación; sin él, la sequía profunda se subestima en verano y se sobreestima en invierno.
- **Referencia de las pruebas:** los 48 días del ejemplo publicado, con los valores que reproduce el paquete `cffdrs` 1.9.2 (tabla de 40-55°N, sin ajuste). Copiarlos a mano habría metido erratas: se copiaron con suma SHA-256 comparada.
- **Constante:** el FFMC se convierte con `250 · 59,5 / 101 = 147,2772`, no con el 147,2 redondeado de los libros. Con 147,2 el código se desvía unas centésimas por día.
- **Límite de Open-Meteo:** el archivo de 60 días por 345 comunas pesa más que el límite por minuto de la API (429). Los lotes van espaciados y con reintento; por eso el FWI corre en su propio bucle, fuera del ciclo del cron (que tiene 30 s).

## Fase 3 — febrero a abril: aluviones después del fuego (BRASA Agua) y transparencia

| # | Entrega | Estado |
|---|---|---|
| 3.1 | **Riesgo de aluvión:** cicatrices de incendios (huellas de incidentes y FIRMS SP), pendiente (DEM Copernicus GLO-30), pronóstico horario de lluvia y `freezing_level_height` de Open-Meteo. Umbral inicial documentado: lluvia diaria > P95 local e isoterma > P90 (zona central: 79,5 mm y 3.954 m) → aviso por lugar guardado. Ver `docs/ALUVIONES.md`. | ⏳ |
| 3.2 | **Página «Calidad de los datos»:** latencia p50/p90 por fuente, ingestas fallidas, frescura, incidentes y descartes. La ficha de incidente ya calcula la latencia por sensor. | ⏳ |
| 3.3 | **API pública de solo lectura** (incidentes, observaciones, riesgo por comuna) en GeoJSON, documentada. | ⏳ |

## Fuera de alcance por ahora

- PostGIS, bus de eventos y STAC: correctos a escala nacional; hoy SQLite + shapely alcanza. Reevaluar con la API pública y más de 50 usuarios activos.
- Predicción de propagación: solo después de backtesting con 2017, 2023, 2024 y 2026, y siempre como «escenario estimado».
- Ubicación de brigadas o aeronaves: solo con un convenio oficial.

## Verificación de cada entrega

- Pruebas: `python dev.py check` (pytest, sintaxis JS y reglas de diseño).
- Navegador: `python dev.py e2e` (errores, CSP y textos cortados en 320, 390 y 1280 px).
- Producción: workflow **Diagnóstico de Cloudflare** después de cada despliegue: ciclo completo, `backup: true`, sin `failed_sources`, incidentes y fuentes de CONAF presentes.

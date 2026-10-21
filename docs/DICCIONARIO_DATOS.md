# Diccionario de datos publicados

Los archivos JSON de `web/data/` son datos abiertos: la app los consume y cualquiera puede
bajarlos. Esta es su referencia campo a campo, y `tests/test_diccionario_datos.py` la mantiene
pegada a los archivos: si un JSON nuevo aparece o un campo nuevo sale en alguno, el test falla
hasta que el campo quede explicado aquí.

Convenciones salvo que se diga lo contrario: superficies en hectáreas (ha), fechas y marcas en
ISO 8601 en UTC (`AAAA-MM-DDTHH:MM:SSZ`), coordenadas WGS84 en grados (lon/lat en ese orden en
las listas), y el código de comuna es el CUT oficial (el `code` de `comunas-index.json`).
Las secciones van en orden de tamaño descendente. No se documentan `comunas.geojson`,
`regiones.geojson` ni `web/data/cases/` (perímetros y series por caso): son GeoJSON estándar o
artefactos por caso, no fichas de datos.

## `rain_normals.json` (~635 KB)

Normal climática diaria de lluvia por comuna (promedio 1991-2020): contra ella se compara la
lluvia de la temporada en curso para el nivel de combustible.

- **Lo consume** el backend: `backend/services.py` siembra la tabla `rain_normal` desde este
  archivo si falta (`FIX-25`) y `backend/rain.py` usa las normales para el cociente
  lluvia/normal. La web no lo pide directo.
- **Lo genera** `python scripts/local/build_rain_normals.py --export` (vuelca `rain_normal`).
- **Fuente**: `source` = «Open-Meteo archive (ERA5)».

| Campo | Tipo | Qué es |
|---|---|---|
| `generated_at` | texto | Marca ISO 8601 UTC de la exportación. |
| `source` | texto | Fuente declara­da: «Open-Meteo archive (ERA5)». |
| `period` | texto | Período de la normal climática: «1991-2020». |
| `cells` | objeto | Mapa código CUT de comuna (texto, p. ej. «1101») → lista de 365 números: mm de lluvia normal de cada día, en el orden `MM-DD` de un año no bisiesto (`backend/rain.py: DAY_KEYS`). |

**Si falta**: una comuna sin la normal completa se omite de `cells` — mejor faltar en el
archivo que publicar una normal coja; el backend la completa después con `build_rain_normals`.

## `incendios-nominados.json` (~348 KB)

Puntos de inicio de incendios de 50 ha o más con nombre, temporadas 2002-2003 a 2023-2024.

- **Lo consume** `web/js/views/casos.js` (mapa de incendios históricos nombrados).
- **Lo genera** `scripts/local/build_incendios_nominados.py`.
- **Fuente**: `source` = `name` «CONAF-GEPRIF», `url` «…/PUNTOS_DE_INICIO_2002_2024_MAYOR_A_50_HA/FeatureServer/0/query»,
  `attribution` «Datos de uso público; citar a CONAF como fuente (declaración de los ítems
  ArcGIS de GEPRIF-DEI, https://deigeprif.com)», `fetched_at` marca ISO UTC de la descarga.

| Campo | Tipo | Qué es |
|---|---|---|
| `source` | objeto | Procedencia de la capa: `name`, `url`, `attribution`, `fetched_at`. |
| `note` | texto | «Puntos de inicio de incendios de 50 ha o más registrados por CONAF-GEPRIF, temporadas 2002-2003 a 2023-2024. La superficie es la registrada en la capa para ese punto de inicio. La capa repite algunas claves nombre+temporada+comuna (71 registros): se publica una fila por clave, la de mayor superficie.» |
| `items` | lista | Un objeto por incendio (3.214 hoy). |
| `name` | texto | Nombre del incendio en la capa (en `items[]`). |
| `comuna` | texto | Nombre de la comuna del punto de inicio (en `items[]`). |
| `season` | texto | Temporada «AAAA-AAAA», p. ej. «2002-2003» (en `items[]`). |
| `ha` | número | Superficie en hectáreas registrada en la capa para ese punto de inicio (en `items[]`). |
| `lat` / `lon` | número | Punto de inicio, WGS84 (en `items[]`). |

**Si falta**: los incendios menores de 50 ha no entran en la capa y por tanto no están; tampoco
es el total de superficie quemada de la temporada.

## `snaspe.json` (~146 KB)

Polígonos del Sistema Nacional de Áreas Silvestres Protegidas del Estado.

- **Lo consume** `backend/geo.py` (`_snaspe_areas`) para cruzar evidencias con áreas protegidas.
- **Lo genera** `scripts/local/build_snaspe.py`.
- **Fuente**: `source` = `name` «CONAF-GEPRIF», `url` «…/SNASPE/FeatureServer/0/query»,
  `attribution` «Datos de uso público; citar a CONAF como fuente (declaración de los ítems
  ArcGIS de GEPRIF-DEI, https://deigeprif.com)», `fetched_at` marca ISO UTC de la descarga.

| Campo | Tipo | Qué es |
|---|---|---|
| `source` | objeto | Procedencia de la capa: `name`, `url`, `attribution`, `fetched_at`. |
| `note` | texto | «Polígonos del Sistema Nacional de Áreas Silvestres Protegidas del Estado (SNASPE): parques nacionales, reservas nacionales y monumentos naturales de Chile. La capa repite algunas áreas con partes separadas (3 registros): se publica una entrada por nombre con todos sus polígonos.» |
| `items` | lista | Un objeto por área protegida (99 hoy). |
| `name` | texto | Nombre del área (en `items[]`). |
| `category` | texto | «Parque Nacional», «Reserva Nacional» o «Monumento Natural» (en `items[]`). |
| `region` | texto | Nombre de la región (en `items[]`). |
| `geometry` | objeto | Polígono GeoJSON del área: `type` («Polygon» o «MultiPolygon») y `coordinates` (en `items[]`). |

## `historia-comunas.json` (~121 KB)

Historia de incendios grandes por comuna: cuántos hubo, cuántas hectáreas sumaron y cuáles
fueron los mayores.

- **Lo consume** `web/js/views/riesgo.js` (historia de la comuna en la vista Riesgo).
- **Lo genera** `scripts/local/build_historia_comunas.py`.
- **Fuente**: `source` = `name` «CONAF-GEPRIF», `url` «…/PUNTOS_DE_INICIO_2002_2024_MAYOR_A_50_HA/FeatureServer/0/query»,
  `attribution` «Datos de uso público; citar a CONAF como fuente (declaración de los ítems
  ArcGIS de GEPRIF-DEI, https://deigeprif.com)», `fetched_at` marca ISO UTC.

| Campo | Tipo | Qué es |
|---|---|---|
| `comunas` | objeto | Mapa nombre de comuna normalizado (minúsculas, sin tildes ni eñes: «alhue», «canete») → ficha de la comuna. |
| `comuna` | texto | Nombre oficial de la comuna (en cada ficha). |
| `temporadas` | lista | Una entrada por temporada con incendios ≥50 ha: `season` («AAAA-AAAA»), `n` (número de incendios), `ha` (hectáreas sumadas) (en cada ficha). |
| `top` | lista | Los mayores incendios de la comuna: `name`, `season`, `ha` (en cada ficha). |
| `total_ha` | número | Hectáreas sumadas de sus incendios ≥50 ha (en cada ficha). |
| `total_incendios` | número | Cuántos incendios ≥50 ha registró la capa en la comuna (en cada ficha). |
| `note` | texto | «Incendios de 50 ha o más con punto de inicio registrado por CONAF-GEPRIF, temporadas 2002-2003 a 2023-2024, agrupados por la comuna del registro. Son los incendios grandes que quedaron en la capa, no el total de incendios ni de superficie quemada de la comuna: los menores de 50 ha no entran. La superficie es la registrada en la capa para cada punto de inicio.» |
| `source` | objeto | Procedencia de la capa: `name`, `url`, `attribution`, `fetched_at`. |

**Si falta**: una comuna sin incendios de 50 ha o más en la capa no aparece en `comunas`; no
significa que nunca haya quemado nada, solo que no quedaron puntos grandes registrados.

## `censo_2024.json` (~105 KB)

Población, viviendas y hogares por comuna según el Censo 2024.

- **Lo consume** `web/js/exposure.js` («Lo que hay alrededor» de una comuna).
- **Lo genera** `scripts/local/build_censo.py`.
- **Fuente y licencia**: `source` apunta al servicio ArcGIS «CENSO2024_V2_gdb» del INE;
  `license` = «CC BY-SA 4.0, reconocimiento al Instituto Nacional de Estadísticas (INE):
  https://www.ine.gob.cl/terminos-de-uso-y-licencia-de-datos-abiertos». Las `notes` citan la
  capa (`COMUNA_DPA_INDICADORES`, censo de derecho), las variantes de nombre del INE
  («Marchihue» = Marchigüe, «Trehuaco» = Treguaco) y la omisión de 12202 Antártica.

| Campo | Tipo | Qué es |
|---|---|---|
| `source` | texto | URL del servicio ArcGIS del Censo 2024 (INE). |
| `license` | texto | Licencia declarada del dato (texto completo arriba). |
| `fetched_at` | texto | Marca ISO 8601 UTC de la descarga. |
| `totals` | objeto | Totales país: `poblacion` (personas), `viviendas`, `hogares` (conteos). |
| `notes` | lista | Notas metodológicas en texto (qué capa es, qué se omitió). |
| `comunas` | lista | Una ficha por comuna (345 hoy). |
| `code` | número | Código CUT de la comuna (en `comunas[]`). |
| `name` | texto | Nombre de la comuna (en `comunas[]`). |
| `poblacion` | número | Personas contadas (en `comunas[]`). |
| `viviendas` | número | Viviendas contadas (en `comunas[]`). |
| `hogares` | número | Hogares contados (en `comunas[]`). |
| `source` | texto | URL de la consulta concreta de esa comuna (en `comunas[]`). |
| `fetched_at` | texto | Marca ISO 8601 de la descarga de esa comuna (en `comunas[]`). |

**Si falta**: una comuna sin ficha en `comunas` no tiene cifras (la vista no las inventa);
12202 Antártica se omite a propósito por estar fuera del territorio de BRASA.

## `temporada-2526.json` (~57 KB)

Acumulado de la temporada 2025-2026 por región y por comuna, desde el reporte público de CONAF.

- **Lo consume** `web/js/views/zona.js` (tarjeta de temporada de «Mi zona»).
- **Lo genera** `scripts/local/build_temporada_2526.py`.
- **Fuente y licencia**: `source` es el CSV «incendios_totales_25_26.csv» del repo público de
  GEPRIF-DEI; `license` = «Datos de CONAF GEPRIF, uso público con cita a CONAF; ver
  docs/research/fuentes-meteologix-geprif.md».

| Campo | Tipo | Qué es |
|---|---|---|
| `source` | texto | URL del CSV de origen. |
| `license` | texto | Licencia declarada del dato (texto completo arriba). |
| `fetched_at` | texto | Marca ISO 8601 UTC de la descarga. |
| `temporada` | texto | Temporada cubierta: «2025-2026». |
| `totales` | objeto | Totales país: `incendios` (conteo), `hectareas` (ha), `mes_peak` (mes con más superficie, «AAAA-MM»), `comuna_top` (nombre de la comuna con más superficie). |
| `regiones` | lista | Una ficha por región: `name`, `incendios`, `hectareas`, `mes_peak`, `comuna_top`. |
| `comunas` | lista | Una ficha por comuna: `code` (CUT, número), `name`, `region`, `incendios` (conteo), `hectareas` (ha quemadas), `mes_peak` («AAAA-MM»), `max_ha` (ha del mayor incendio de la comuna). |
| `sin_comuna` | lista | Registros del CSV sin comuna resoluble; hoy viene vacía. |

**Si falta**: una comuna sin incendios en el reporte no aparece en `comunas`; `sin_comuna`
vacía significa que todo registro se pudo ubicar.

## `comunas-index.json` (~42 KB)

Índice liviano de las 345 comunas: nombre, región, centro y caja — para los buscadores sin
procesar `comunas.geojson` completo.

- **Lo consumen** `web/js/pantalla.js`, `web/js/app.js` y `web/js/respuesta.js` (el índice se
  precarga para resolver «mi comuna» por nombre o por punto).
- **Lo genera** `python scripts/build_territory.py` junto a `comunas.geojson` y
  `regiones.geojson`, a partir de los mapas vectoriales de la Biblioteca del Congreso Nacional
  (vía https://github.com/caracena/chile-geojson).

| Campo | Tipo | Qué es |
|---|---|---|
| `code` | número | Código CUT de la comuna (elemento de la lista raíz). |
| `name` | texto | Nombre de la comuna. |
| `region` | texto | Nombre de la región. |
| `center` | lista | `[lon, lat]` del centro de la comuna, WGS84. |
| `bbox` | lista | `[min_lon, min_lat, max_lon, max_lat]` de la comuna, WGS84. |

**Si falta**: el índice es la lista raíz del archivo (no hay envoltorio); una comuna ausente
aquí no se puede elegir ni ubicar en la app.

## `cases.json` (~29 KB)

Catálogo curado de casos históricos reconstruidos con detecciones reales y reanálisis: cada
cifra declara quién la informó y cuándo.

- **Lo consume** `backend/cases.py` (lo sirve en `GET /api/cases` y `GET /api/cases/{id}`,
  `backend/routes/community.py`); la vista `web/js/views/casos.js` lo pide por esas rutas. Los
  artefactos por caso (perímetro, serie GOES) viven aparte en `web/data/cases/`.
- **Lo mantiene** curaduría manual; los artefactos los generan `scripts/build_case_goes.py` y
  `scripts/local/build_perimetros_casos.py`.
- **Nota del archivo**: «Catálogo curado de casos históricos. Cada cifra va con quién la
  informó y cuándo: las cifras cambian a medida que avanzan los balances, y muchas veces la
  prensa cita a CONAF, SENAPRED o la Fiscalía. «Por verificar» marca lo que aún no se contrasta
  con una fuente. Las detecciones y el clima se obtienen de fuentes satelitales y de
  reanálisis, nunca se inventan.»

| Campo | Tipo | Qué es |
|---|---|---|
| `note` | texto | La declaración de método citada arriba. |
| `cases` | lista | Una ficha por caso histórico. |
| `id` | texto | Identificador del caso, p. ej. «vina-del-mar-2024» (en `cases[]`). |
| `title` / `subtitle` | texto | Nombre del caso y su subtítulo geográfico (en `cases[]`). |
| `region` | texto | Región principal del caso (en `cases[]`). |
| `scope` | texto | Escala del caso: «fire», «episode» o «complex» (en `cases[]`). |
| `start_utc` / `end_utc` | texto | Ventana del caso, ISO 8601 UTC (en `cases[]`). |
| `bbox` | lista | `[min_lon, min_lat, max_lon, max_lat]` del caso (en `cases[]`). |
| `camera` | lista | `[lon, lat, altura_m]` para encuadrar el caso en el mapa (en `cases[]`). |
| `goes` | objeto o null | Satélite GOES del archivo FDC usado: `satellite` («G16»/«G19») y `cadence_min` (minutos entre pasadas); null si el caso no tiene archivo GOES (en `cases[]`). |
| `goes_note` | texto | Opcional: por qué falta o qué sustituye al archivo GOES (en `cases[]`). |
| `firms_sources` | lista | Instrumentos FIRMS usados, p. ej. «VIIRS_SNPP_SP» (en `cases[]`). |
| `figures` | lista | Cifras del caso: `key`, `label` y `revisions` — cada revisión con `value` (texto), `source`, `url`, `date` y `kind` («oficial», «prensa» o «estudio») (en `cases[]`). |
| `context` | lista | Relato verificado: objetos `text` + `verified` (bool) (en `cases[]`). |
| `references` | lista | Fuentes del caso: `label` + `url` (en `cases[]`). |
| `lessons` | lista | Lecciones del caso: `text`, y cuando hay fuente `source` + `url` (en `cases[]`). |
| `perimeter` | bool | Cuando es true existe `web/data/cases/<id>.perimeter.json` con el perímetro (en `cases[]`). |

**Si falta**: `goes` en null (o `goes_note`/`perimeter` ausentes) significa que el caso no trae
ese artefacto — la vista lo omite, no lo inventa.

## `interfaz.json` (~26 KB)

Hectáreas en zona de interfaz urbano-forestal por comuna: dónde las casas y la vegetación se
tocan.

- **Lo consume** `web/js/exposure.js` (franja de interfaz en «Lo que hay alrededor»).
- **Lo genera** `scripts/local/build_interfaz.py`.
- **Fuente y licencia**: `source` es la capa «riesgo_dissolve_point» del catálogo ArcGIS de
  GEPRIF-DEI (`catalog` y `dashboard` apuntan al catálogo y al tablero «Zonas Interfaz»);
  `license` = «Datos de uso público, citando a CONAF como fuente — declaración del tablero
  «Zonas Interfaz» (ítem ArcGIS 09532374973a495bb185fcbe55711cd3, GEPRIF-DEI); la capa no
  declara licencia propia y el permiso formal sigue la puerta de OFI-03.» Las `notes` explican
  la metodología (cada registro disuelto por comuna, clase de interfaz y nivel de riesgo; la
  comuna es el `dpa_cod` oficial) y listan las comunas del índice sin zonas de interfaz.

| Campo | Tipo | Qué es |
|---|---|---|
| `source` | texto | URL de la capa ArcGIS de origen. |
| `catalog` | texto | URL del catálogo ArcGIS de GEPRIF-DEI. |
| `dashboard` | texto | URL del tablero «Zonas Interfaz». |
| `license` | texto | Licencia declarada del dato (texto completo arriba). |
| `fetched_at` | texto | Marca ISO 8601 UTC de la descarga. |
| `notes` | lista | Notas metodológicas en texto. |
| `comunas` | objeto | Mapa código CUT de comuna (texto, p. ej. «1101») → superficie en interfaz. |
| `ha_interfaz` | número | Hectáreas de la comuna en zona de interfaz urbano-forestal (en cada ficha). |
| `pct_comuna` | número | Porcentaje de la superficie de la comuna que es interfaz (en cada ficha). |

**Si falta**: una comuna ausente de `comunas` no tiene zonas de interfaz en la capa (las
`notes` listan los códigos omitidos) — la vista no muestra la cifra.

## `persistent_hotspots.json` (~12 KB)

Fuentes de calor fijas conocidas (volcanes, industrias): si toda la evidencia de un incidente
cae dentro de su radio, BRASA no envía aviso automático.

- **Lo consume** `backend/incidents.py` al agrupar evidencias; `scripts/build_persistent_mask.py`
  lo usa para la máscara persistente sin modificarlo.
- **Lo mantiene** curaduría manual.
- **Nota del archivo**: «Fuentes de calor fijas conocidas: si toda la evidencia de un incidente
  cae dentro de su radio, BRASA no envía aviso automático (el punto se sigue mostrando). Las
  industrias se detectan solas: una celda de ~2 km con detecciones en 8 o más días distintos en
  30 días. Coordenadas aproximadas de los cráteres; radio holgado. Cada punto puede llevar
  `valid_from` y/o `valid_to` (fechas ISO AAAA-MM-DD, inclusivas): fuera de esa ventana no
  silencia, para que una instalación apagada no tape un incendio; sin fechas, vale siempre.
  Regla de siempre: sin `coordinate_source` no se publica un punto. Ver
  docs/investigacion/INV-16-industria-antorchas.md.»

| Campo | Tipo | Qué es |
|---|---|---|
| `note` | texto | La regla de uso citada arriba. |
| `sources` | lista | Una ficha por fuente fija de calor (60 hoy). |
| `name` | texto | Nombre del punto (en `sources[]`). |
| `kind` | texto | Tipo de fuente; hoy solo «volcan» (en `sources[]`). |
| `lat` / `lon` | número | Coordenadas aproximadas del punto, WGS84 (en `sources[]`). |
| `radius_km` | número | Radio en km dentro del cual el punto silencia el aviso (en `sources[]`). |
| `source` | texto | Atribución textual de las coordenadas (en `sources[]`). |

**Si falta**: un punto sin `valid_from`/`valid_to` silencia siempre; fuera de esa ventana, no.
Las ventanas y `coordinate_source` están previstos en la nota aunque hoy ningún punto los traiga.

## `prioritarias.json` (~1,4 KB)

Listado de comunas prioritarias para la prevención de incendios forestales, temporada 2026-2027.

- **Lo sirve** `GET /api/priority-comunas` (`backend/routes/public.py`), que lo lee tal cual;
  **lo consume** `web/js/views/preparate.js` (`api.priorityComunas`).
- **Lo mantiene** curaduría manual sobre el anuncio oficial de CONAF.

| Campo | Tipo | Qué es |
|---|---|---|
| `title` | texto | «Comunas prioritarias para la prevención de incendios forestales (temporada 2026-2027)». |
| `source` | texto | «CONAF». |
| `source_url` | texto | URL del anuncio oficial en conaf.cl. |
| `verified` | bool | false mientras el listado no salga en un documento oficial. |
| `fetched_at` | texto | Fecha de revisión, ISO AAAA-MM-DD. |
| `note` | texto | «CONAF informó 90 comunas prioritarias en el COGRID del 10-sep-2026 y entregó los planes preventivos a los municipios, pero al 19-oct-2026 no ha publicado el listado en un documento oficial. Revisado: noticias de conaf.cl al 19-oct-2026 (la presentación del Programa de Empleo del 23-sep-2026 no incluye anexo; las notas regionales nombran cifras sin listado — Valparaíso anuncia 19 comunas sin detallarlas y La Araucanía reparte cupos en sus 32 comunas), el gestor documental conafprevencionincendios.cl (solo hay resolución de quemas), el catálogo ArcGIS de GEPRIF y la prensa (solo cita Quilpué, Tomé, Hualqui, Collipulli y Santa Bárbara). La lista se incorporará solo desde el documento oficial; no se completa con estimaciones. Para agregarla: llena 'comunas' con objetos {"cod_comuna": "05602", "nombre": "Algarrobo"} usando el código comunal BCN/SUBDERE (el 'code' de comunas-index.json con cero a la izquierda) y cambia 'verified' a true.» |
| `comunas` | lista | Vacía hoy: cuando CONAF publique el listado oficial, lleva objetos `cod_comuna` (CUT con cero a la izquierda, texto) y `nombre`. |

**Si falta**: `comunas` vacía (o `verified` en false) significa que el listado oficial aún no
sale; la vista muestra la `note` en vez de una lista inventada.

## `calibracion.json` (~1 KB)

Medición del adelanto de BRASA: cuántos minutos pasan entre la primera detección satelital
agrupada y que el incidente pase a «posible».

- **Lo consume** `web/js/views/calidad.js` (vista Calidad).
- **Lo genera** `scripts/local/medir_adelanto.py` reproduciendo el caso con
  `scripts/replay_case.py` sobre una base desechable.
- **Fuente**: `source` = «NOAA GOES-16 FDC · dominio público»; `method` = «Minutos desde la
  primera detección satelital agrupada hasta que el incidente pasa a «posible» con la regla de
  agrupación vigente, medidos reproduciendo el caso (scripts/replay_case.py) sobre una base
  desechable.»

| Campo | Tipo | Qué es |
|---|---|---|
| `case_id` | texto | Caso usado para medir, p. ej. «vina-del-mar-2024». |
| `generated_at` | texto | Marca ISO 8601 UTC de la medición. |
| `source` | texto | Fuente de las detecciones (texto completo arriba). |
| `method` | texto | Qué se midió y cómo (texto completo arriba). |
| `incidents` | lista | Un objeto por incidente del caso. |
| `id` | texto | Hash del incidente en `work.db` (en `incidents[]`). |
| `first_seen_at` | texto | Primera detección agrupada, ISO 8601 UTC (en `incidents[]`). |
| `min_to_posible` | número | Minutos hasta «posible» (en `incidents[]`). |
| `n_obs` | número | Detecciones que tuvo el incidente (en `incidents[]`). |
| `summary` | objeto | Resumen: `n_incidents`, `median_min` y `max_min` (minutos). |

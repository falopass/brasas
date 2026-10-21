# API pública — BRASA Chile

Referencia de la API HTTP de BRASA (`backend/main.py`, routers en `backend/routes/`). Está escrita
a mano y `tests/test_api_doc.py` comprueba que no se separe del código: toda ruta documentada aquí
existe en la app con ese método, y toda ruta GET bajo `/api/` está documentada.

- Base: `https://brasa-chile.ddiegosebastianbb.workers.dev` (o `http://127.0.0.1:8000` en local).
- Las rutas se escriben como las declara FastAPI: `{param}` es un parámetro de ruta.
- Respuestas JSON UTF-8 salvo que se indique otro tipo (`application/geo+json`, JPEG).
- Errores: `422` con `{"detail": ...}` para parámetros inválidos; `429` con
  `{"detail": {"code": "RATE_LIMITED", "limit": N, "window_s": S, "retry_after_s": T}}` y cabecera
  `Retry-After` en los límites por IP. `/api/explore` responde `422` con `code: EXPLORE_DAILY_LIMIT`
  por decisión de producto.
- BRASA no es fuente oficial: las detecciones satelitales son señales de calor, no incendios
  confirmados. «Confirmado» solo viene de CONAF. Fuentes y licencias completas: `docs/FUENTES.md`.

## Acceso

| Cabecera | Para | De dónde sale |
|---|---|---|
| `X-Brasa-Token` | Datos del dispositivo (lugares, avisos, reportes propios) | `POST /api/subscribers` (gratis, sin cuenta) |
| `X-Admin-Token` | Cola, decisiones y equipo de moderación | El `ADMIN_TOKEN` del servidor o el token individual de cada moderador (se crea en `POST /api/admin/moderators`) |

Las rutas sin cabecera son públicas. Los límites por IP son en memoria por proceso
(`backend/routes/common.py`, `RateLimiter`):

| Ruta | Límite |
|---|---|
| `POST /api/subscribers` | 20 por hora |
| `POST /api/reports` | 6 por hora |
| `POST /api/alerts/test` | 5 cada 10 minutos |
| `GET /api/shared/{token}` | 240 por hora |
| `GET /api/explore` | `EXPLORE_DAILY_LIMIT` por día (200 por defecto; responde 422) |

Quedan fuera de esta referencia las rutas de operación `/api/internal/tick` y
`/api/internal/backup` (POST, exigen `X-Internal-Token`; en producción el Worker las bloquea) y
`/api/telegram/webhook` (POST, solo para servidores de Telegram con `X-Telegram-Bot-Api-Secret-Token`).

## Estado y configuración

#### `GET /api/health`
Sin parámetros. Devuelve `{"status", "name", "version", "time_utc"}`. Público. Sin fuente externa.

#### `GET /api/config`
Sin parámetros. Configuración pública para la interfaz: versión, zonas, niveles de riesgo, clave
pública VAPID, llaves públicas de Cesium/Turnstile y banderas de fuentes configuradas. Nunca devuelve
secretos. Público.

#### `GET /api/status`
Parámetros: `history` entero 0–50 (0 por defecto); con N>0 agrega las últimas N ejecuciones por
producto. Devuelve el estado de cada fuente de ingesta (`runs`), frescura de datos, últimos barridos
GOES y conteo de incidentes abiertos. `failures_24h` resume por producto las corridas de las últimas
24 h: `{"runs", "failed", "last_failed_at", "last_error"}` con el último mensaje de error de la
ingesta recortado a 160 caracteres (`null` si no hubo fallos). Público. Fuentes: procedencia interna
de NASA FIRMS y NOAA GOES (dominio público).

#### `GET /api/quality/feedback`
Sin parámetros. Devuelve `{"total", "counts": {"sirvio", "no_sirvio", "quema"}, "since"}`: la
opinión agregada sobre los avisos entregados («me sirvió», «no me sirvió», «era una quema»; una
opinión por aviso). `since` es el `created_at` del aviso opinado más antiguo y sale en `null`
mientras nadie haya respondido. Solo conteos globales: sin dispositivos, lugares, comunas ni ids
de aviso. Público, caché de 60 s. Fuente: opiniones de las personas usuarias de BRASA.

## Observabilidad

#### `GET /api/observability/routes`
Sin parámetros. Devuelve `{"window_min": 60, "desde", "aviso", "routes"}`: por cada ruta bajo
`/api/` pedida en los últimos 60 minutos, `{"path", "n", "p50_ms", "p95_ms", "errors_4xx",
"errors_5xx", "max_ms"}`, ordenadas por `p95_ms` de mayor a menor. `path` es la ruta plantillada
(`/api/incidents/{incident_id}`), nunca la URL con el id; las peticiones que no calzan con ninguna
ruta se agrupan en `/api/sin-ruta`. `desde` es el inicio de la ventana en UTC
(`AAAA-MM-DDTHH:MM:SSZ`), `n` cuenta todas las respuestas y los tiempos van en milisegundos
enteros. Público, sin fuente externa.

Entran todas las rutas bajo `/api/`, también las internas y las de administración: se publica el
agregado por ruta, sin identificadores de quién pidió ni de qué pidió.

La medición es **por proceso**: vive en memoria, se reinicia con el contenedor y cada instancia
mide solo su propio tráfico. No reemplaza los registros de Cloudflare ni sobrevive a un reinicio.
Guarda solo ruta, código y tiempo: nunca IP, query string, cabeceras ni cuerpos.

## Detecciones e incidentes

#### `GET /api/observations`
Parámetros: `hours` entero 1–336 (48 por defecto); `bbox` texto `oeste,sur,este,norte` (opcional);
`reliable` booleano (falso por defecto: solo confianza nominal/alta en VIIRS-MODIS, alta/media en
GOES). Devuelve `{"points": [...]}` de detecciones térmicas satelitales, hasta 20 000 filas
(`truncated` avisa si el tope recortó la lista). Cada punto lleva exactamente `id`, `lat`, `lon`,
`observed_at`, `source` (producto de origen), `sensor`, `satellite`, `resolution_m`, `frp_mw`,
`confidence`, `comuna_code`, `comuna`, `region` y, cuando la detección pertenece a un incidente,
`incident_id`, `incident_status`, `incident_n` e `incident_fixed` (`null` si no). Las columnas
internas de la tabla (`run_id`, `ingested_at`, `alerts_evaluated_at`, `confidence_raw`,
`brightness_k`) no se publican. Público.
Fuente: NASA FIRMS (VIIRS/MODIS) y NOAA GOES — dominio público.

#### `GET /api/incidents`
Parámetros: `hours` entero 1–336 (48); `include_fixed` booleano (falso: incluye volcanes e industria
probables). Devuelve `{"incidents": [...]}`, hasta 500: agrupaciones de detecciones con estado
(`anomalia` → `confirmado`), sensores y caja. Solo sale lo que está en territorio chileno: un
incidente sin comuna chilena pasa a `descartado` en el ciclo de cierre y no se publica (queda en la
tabla para auditoría hasta la purga normal), salvo que traiga `official_ref` de CONAF. Público.
Fuente: NASA FIRMS y NOAA GOES agrupados por BRASA (reglas en `FUENTES.md`).

#### `GET /api/incidents/{incident_id}`
`{incident_id}` es el id del incidente (12 caracteres hex). Devuelve ficha completa: evidencia por
detección con latencia, línea temporal horaria, incendio oficial asociado si lo hay y `spread`, el
escenario estimado de propagación. `spread` puede ser `null`: sin comuna, sin FFMC en `fwi_daily`
o sin viento en `risk_hourly` no hay escenario y la ficha no muestra el bloque. Cuando existe trae
`kind` (`escenario_estimado`), `ffmc` y `ffmc_date`, `wind_kmh` y `wind_deg` (velocidad en km/h y
dirección desde la que sopla), `wind_at`, `slope_deg` y `aspect_deg` (`null` hoy: BRASA no tiene
modelo de elevaciones), `effective_wind_kmh`, `isi`, `speed_m_min` y `speed_kmh` (velocidad de
avance en m/min y km/h), `direction_deg` (rumbo hacia el que avanza; `null` si no hay dirección de
viento), `fuel` y `reference` (combustible de referencia O-1b y fuente del FBP), `assumptions`
(supuestos a la vista) y `note`. El viento sale de `risk_hourly` (pronóstico del centro de la
comuna, hora más cercana a ahora) y el FFMC de `fwi_daily`; la velocidad y la dirección, del ajuste
viento + pendiente del FBP canadiense (FCFDG 1992, ST-X-3, ecs. 39-51; Wotton et al. 2009). **Es un
escenario estimado, no es una predicción ni un perímetro**: usa el clima del centro de la comuna,
no del punto del fuego, y un combustible de referencia que no es el matorral chileno. 404 si no
existe o fue fusionado sin alias. Público. Fuentes: NASA/NOAA (dominio público) y CONAF cuando hay
`official_fire`.

#### `GET /api/incidents/{incident_id}/reports`
Parámetros: `hours` entero 1–168 (48); `km` número 1–10 (3). Devuelve `{"reports": [...],
"radius_km", "hours", "truncated"}` con hasta 20 reportes ciudadanos **verificados** dentro del
radio del incidente, más recientes primero, cada uno con `distance_km`. Un id fusionado se resuelve
al incidente vigente; 404 si no existe. Público. Fuente: reportes ciudadanos de BRASA.

#### `GET /api/official-fires`
Parámetros: `hours` entero 1–336 (48). Devuelve `{"fires": [...]}` con los incendios del reporte
público de CONAF (estado oficial, superficie, comuna) y su `source`. Público. Fuente: CONAF — la
información es de CONAF y el reporte no declara licencia; se cita con enlace (`FUENTES.md`).

#### `GET /api/panorama`
Parámetros: `season` texto `AAAA-AAAA` (la más reciente en la tabla por defecto). Devuelve
agregados de la temporada: `totals` (incendios, hectáreas, en combate, controlados, extinguidos),
`by_region`, `by_comuna` (las 12 comunas con más superficie, cada una con `comuna`, `region`,
`n`, `ha`, `en_combate` y `comuna_code` cuando el nombre o el punto calza con el territorio
BCN; `null` si no), `seasons` (temporadas presentes en la tabla, de la más nueva a la más
antigua), `boton_rojo_days` (días guardados con pronóstico Botón Rojo), `unknown_status`
(cuántos incendios traen un estado que BRASA no interpreta, con hasta 5 textos tal cual
vinieron: `{"n", "values": [{"raw", "n"}]}`; hace visible un cambio de formato de CONAF
que de otro modo se contaría en silencio como «en combate», sin alterar los totales),
`source` y `updated_at`.
Sin filas para la temporada responde 200 con ceros y listas vacías. Público. Fuentes: CONAF
(reporte GEPRIF y Botón Rojo); solo agregados, sin datos de personas.

#### `GET /api/explore`
Consulta directa al archivo FIRMS. Parámetros: `zone` (una zona de `/api/config`, `chile` por
defecto); `mode` `recent` | `historical` (`recent`); `days` entero 1–10 (3); `start` fecha
AAAA-MM-DD (obligatoria en `historical`, no anterior a noviembre de 2000 ni futura). Devuelve
`{"points": [...]}` de detecciones con `notices`. Público, con tope diario por IP (ver tabla).
Requiere `FIRMS_MAP_KEY` en el servidor o responde 503 `FIRMS_KEY_MISSING`. Fuente: NASA FIRMS —
dominio público.

## Riesgo, clima y territorio

#### `GET /api/risk`
Parámetros: `day` fecha AAAA-MM-DD (hoy en Chile por defecto). Devuelve el mapa de riesgo por comuna:
nivel 30-30-30, nivel combinado con FWI, Botón Rojo de CONAF, avisos DMC vigentes y anomalía de
lluvia. Público. Fuentes: Open-Meteo (pronóstico, uso gratuito no comercial), CONAF Botón Rojo
(propiedad de CONAF), DMC en CAP (dominio público), ERA5 vía Open-Meteo; niveles calculados por BRASA.

#### `GET /api/risk/{code}`
`{code}` es el código de comuna (entero). Devuelve detalle de la comuna: días de pronóstico, horas
30-30-30, FWI diario, Botón Rojo, lluvia y avisos DMC. 404 si la comuna no existe. Público. Fuentes:
las mismas de `/api/risk`.

#### `GET /api/risk/{code}/trend`
Parámetros: `weeks` entero 1–8 (1). Compara el pronóstico vigente de la comuna con el emitido
`weeks` semanas antes (`{"rows", "summary"}`). 404 si la comuna no existe. Público. Fuente: cálculo
propio de BRASA sobre sus pronósticos archivados.

#### `GET /api/weather`
Parámetros obligatorios: `lat` (-90 a 90), `lon` (-180 a 180). Devuelve condiciones actuales
modeladas en el punto. Público, caché de 10 min. Fuente: Open-Meteo.

#### `GET /api/locate`
Parámetros obligatorios: `lat` (-90 a 90), `lon` (-180 a 180). Devuelve la comuna del punto y su
riesgo de hoy (`{"comuna": null}` fuera de Chile). Público. Territorio: BCN (ver `FUENTES.md`).

#### `GET /api/nearby-services`
Parámetros obligatorios: `lat`, `lon` (números). Devuelve puntos de encuentro, hospitales y
cuarteles cercanos con distancia y dirección. Público, caché de 24 h. Fuente: OpenStreetMap vía
Overpass (© OpenStreetMap); cobertura rural incompleta.

#### `GET /api/priority-comunas`
Sin parámetros. Devuelve la lista de comunas prioritarias (`web/data/prioritarias.json`). Público.

#### `GET /api/comuna/{code}`
`{code}` es el código de comuna (entero). Devuelve la ficha de la comuna en un solo JSON:
`comuna` (código, nombre, provincia, región), `risk` (días de hoy a +5 con nivel 30-30-30,
nivel combinado, puntaje, FWI), `boton_rojo` (días CONAF), `exposicion` (población, viviendas
y hogares del Censo 2024, `null` si no hay dato) e `incendios_oficiales` (incendios CONAF de la
comuna en los últimos 30 días). Cada bloque lleva su `source`. 404 si la comuna no existe.
Público, caché de 5 min. Fuentes: BRASA (riesgo, estimación no oficial), CONAF (Botón Rojo e
incendios), INE Censo 2024 (CC BY-SA 4.0), territorio BCN.

#### `GET /api/climate/enso`
Sin parámetros. Devuelve el estado ENSO vigente según el índice ONI: `phase` (`nino` |
`nina` | `neutral`, por el umbral del CPC de ±0,5 °C), `oni`, `season` (trimestre móvil,
p. ej. `JAS`), `year`, `updated_at` (cuándo lo consultó BRASA), `source` y `source_url`.
Si la NOAA no responde devuelve la última lectura guardada; sin ninguna, los campos salen
en `null` (nunca un valor inventado). Público, caché de 6 h. Fuente: NOAA CPC (dominio
público, gobierno de EE. UU.).

#### `GET /api/climate/fwi/percentile/{code}`
`code` es el código de comuna (entero). Devuelve el FWI vigente de la comuna leído contra
su propia historia del último año: `{"comuna_code", "value", "level", "percentile", "days",
"since", "source", "note"}`. `percentile` es el porcentaje de esa historia con FWI menor o
igual (los empates cuentan la mitad) y sale en `null` mientras haya menos de 10 días
guardados; `days` dice cuántos hay y `since` es la fecha más antigua. Sin historial
responde 404 `SIN_HISTORIAL`. Público, caché de 1 h. Fuente: FWI calculado por BRASA
(Van Wagner) sobre Open-Meteo.

## Reportes ciudadanos

#### `POST /api/reports`
Cuerpo `multipart/form-data`: `lat` (-60 a -17) y `lon` (-110 a -66) obligatorios; `kind` uno de
`humo` | `llamas` | `quema` | `otro` (`humo`); `description` texto hasta 600 caracteres; `photo`
imagen hasta 8 MB (se re-codifica a JPEG sin metadatos); `cf-turnstile-response` token antibot si el
servidor tiene Turnstile. Cabecera `X-Brasa-Token` opcional (vincula el reporte al dispositivo).
Devuelve `{"id", "status": "no_verificado"}` (201) o `{"duplicate": true}` (200) si ya hay uno
equivalente en revisión. Nada se publica sin revisión humana. Límite: 6 por hora por IP.

#### `GET /api/reports`
Parámetros: `hours` entero (72 por defecto; se acota a 1–336); `limit` entero 1–2000 (500).
Devuelve `{"reports": [...], "truncated"}` solo con reportes **verificados**, ubicación redondeada
a ~100 m; `truncated` avisa si el `limit` recortó la lista. Público. Fuente: reportes ciudadanos de
BRASA.

#### `GET /api/reports/{report_id}/photo`
Devuelve el JPEG del reporte. Pública si el reporte está `verificado`; en otro estado exige
`X-Admin-Token`. 404 sin foto.

#### `GET /api/reports/mine`
Devuelve los reportes enviados por el dispositivo, con su estado y nota del moderador. Exige
`X-Brasa-Token`. Fuente: datos del propio dispositivo.

#### `GET /api/admin/reports`
Parámetros: `status` uno de `no_verificado` | `verificado` | `descartado` (`no_verificado`). Cola de
moderación (hasta 200), con ubicación exacta; aplica caducidad antes de listar. Exige
`X-Admin-Token`.

#### `POST /api/admin/reports/batch`
Cuerpo JSON `{"ids": [...], "status", "note"}`: hasta 200 ids, `status` válido y `note` hasta 300
caracteres. Modera en lote; los que pasan a `verificado` generan avisos. Exige `X-Admin-Token`.

#### `POST /api/admin/reports/{report_id}`
Cuerpo JSON `{"status", "note"}` (nota hasta 300 caracteres). Aprueba o descarta un reporte y
recalcula los incidentes cercanos si cambia la verificación. Exige `X-Admin-Token`. Cada decisión
queda en `moderation_log` con quién la tomó.

#### `GET /api/admin/me`
Sin parámetros. Devuelve `{"name", "superuser"}`: quién entró al panel (`administración` y
`superuser: true` con el token maestro; el nombre del moderador y `false` con un token
individual). Exige `X-Admin-Token`.

#### `GET /api/admin/moderators`
Sin parámetros. Devuelve `{"moderators": [...]}` con id, nombre, alta y revocación de cada
moderador. Solo el superusuario (`ADMIN_TOKEN`); un token individual recibe 403.

#### `POST /api/admin/moderators`
Cuerpo JSON `{"name"}`. Crea un moderador y devuelve `{"id", "name", "token"}` (201): el token se
muestra una sola vez, en la base queda solo su SHA-256. Solo el superusuario.

#### `POST /api/admin/moderators/{moderator_id}/revoke`
Sin cuerpo. Revoca el token: deja de funcionar al instante y las decisiones pasadas conservan el
nombre. 404 si no existe o ya estaba revocado. Solo el superusuario.

#### `GET /api/admin/moderation-log`
Sin parámetros. Devuelve las últimas 200 decisiones `{"log": [...]}` con acción, reporte, nota,
fecha y quién la tomó (`administración` = token maestro). Exige `X-Admin-Token`.

## Dispositivo, lugares y avisos (sin cuentas)

#### `POST /api/subscribers`
Sin cuerpo. Crea el dispositivo y devuelve `{"token"}` (201): es la llave de acceso, viaja en
`X-Brasa-Token` y no se puede recuperar. Límite: 20 por hora por IP.

#### `GET /api/me`
Devuelve resumen del dispositivo: canales activos (push, Telegram) y número de lugares. Exige
`X-Brasa-Token`.

#### `GET /api/me/export`
Descarga JSON (`Content-Disposition: attachment`) con todo lo guardado del dispositivo: lugares,
avisos, suscripción push, chat de Telegram (Ley 21.719). El identificador del dispositivo no viaja
en el archivo. Exige `X-Brasa-Token`.

#### `DELETE /api/me`
Borra el dispositivo y en cascada sus lugares, avisos y suscripciones. Exige `X-Brasa-Token`.

#### `GET /api/places`
Devuelve `{"places": [...]}` con los lugares guardados del dispositivo. Exige `X-Brasa-Token`.

#### `POST /api/places`
Cuerpo JSON `PlaceIn`: `name` 1–60 caracteres; `kind` uno de `casa` | `parcela` | `familia` |
`trabajo` | `colegio` | `otro`; `lat` -60 a -17; `lon` -110 a -66; `radius_km` 1–50 (10 por
defecto); `older_adult` booleano. Máximo 10 lugares por dispositivo. Devuelve `{"id", "comuna"}`
(201). Exige `X-Brasa-Token`.

#### `PATCH /api/places/{place_id}`
Mismo cuerpo `PlaceIn` que el alta. 404 si el lugar no es del dispositivo. Exige `X-Brasa-Token`.

#### `DELETE /api/places/{place_id}`
Borra el lugar. 404 si no es del dispositivo. Exige `X-Brasa-Token`.

#### `GET /api/places/{place_id}/summary`
Devuelve el resumen del lugar: estado (`tranquilo` | `riesgo` | `aviso` | `urgente`), viento, focos
cercanos con distancia y dirección, incendios CONAF cercanos, riesgo de la semana y avisos DMC.
Exige `X-Brasa-Token`. Fuentes: las de riesgo y detecciones más arriba.

#### `GET /api/places/{place_id}/history`
Historial del lugar: `{"days", "incidents": [{"id", "status", "distance_km", "first_seen_at",
"last_seen_at", "n_obs", "comuna"}]}` — los incidentes no fijos dentro de 2× el radio en los
últimos `days` días (30 por defecto, 1–90), del más reciente al más antiguo, hasta 10. 404 si el
lugar no es del dispositivo. Exige `X-Brasa-Token`. Fuente: la tabla de incidentes (detecciones
agrupadas), que sobrevive a la retención de observaciones.

#### `POST /api/places/{place_id}/share`
Crea o devuelve `{"token"}` del enlace público de solo lectura del lugar. Exige `X-Brasa-Token`.

#### `DELETE /api/places/{place_id}/share`
Corta el enlace: quien lo tenga deja de ver el lugar. Exige `X-Brasa-Token`.

#### `GET /api/shared/{token}`
Vista pública del lugar compartido: el mismo resumen de `places/{id}/summary`, sin datos de quien lo
guardó. Público (el token es la autorización). Límite: 240 por hora por IP.

#### `POST /api/push/subscribe`
Cuerpo JSON `{"endpoint", "keys": {"p256dh", "auth"}}`: `endpoint` de 10 a 1000 caracteres y debe
empezar por `https://`. Registra la suscripción Web Push del dispositivo. Exige `X-Brasa-Token`.

#### `DELETE /api/push/subscribe`
Quita la suscripción Web Push del dispositivo. Exige `X-Brasa-Token`.

#### `POST /api/telegram/link`
Devuelve `{"url"}` con el enlace `t.me` de un solo uso para vincular Telegram. 503 si el servidor no
tiene bot configurado. Exige `X-Brasa-Token`.

#### `GET /api/alerts`
Parámetros: `limit` entero 1–200 (50); `before` texto hasta 64 caracteres (cursor `next_before` de
la página anterior, «<created_at>|<id>»; un `created_at` a secas también se acepta). Devuelve
`{"alerts", "total", "has_more", "next_before"}`: historial de avisos del dispositivo. Exige
`X-Brasa-Token`.

#### `POST /api/alerts/test`
Envía una notificación de prueba por los canales activos y devuelve `{"channels": [...]}`. Exige
`X-Brasa-Token`. Límite: 5 cada 10 minutos por IP.

## Casos históricos

#### `GET /api/cases`
Sin parámetros. Devuelve el catálogo de casos históricos reconstruidos (`{"cases": [...]}`).
Público. Fuente: NOAA GOES-16 FDC (dominio público) y FIRMS SP.

#### `GET /api/cases/{case_id}`
Devuelve el caso con su línea temporal horaria, barridos GOES y si tiene capa polar cargada. 404 si
no existe. Público. Fuentes: NOAA GOES y NASA FIRMS (dominio público).

#### `GET /api/cases/{case_id}/polar`
Devuelve `{"points": [...]}`: las detecciones VIIRS/MODIS ya descargadas del archivo FIRMS para el
caso. Público. Fuente: NASA FIRMS SP (dominio público).

#### `POST /api/cases/{case_id}/polar`
Descarga (una vez) esas detecciones y devuelve `{"count", "notices"}`. 503 `FIRMS_KEY_MISSING` si el
servidor no tiene clave FIRMS. Público. Fuente: NASA FIRMS SP.

#### `GET /api/cases/{case_id}/weather`
Devuelve el reanálisis horario ERA5 en el centro del caso. Público, caché permanente. Fuente:
ERA5 (Copernicus) vía Open-Meteo Archive.

#### `GET /api/cases/{case_id}/export.csv`
Descarga las detecciones del caso en CSV (RFC 4180, UTF-8 con BOM): una fila por observación con
`observed_at_utc`, `observed_at_chile`, `lat`, `lon`, `sensor`, `satellite`, `confidence`, `frp`
y `source` (`goes`/`polar`). 413 si el caso supera 50 000 filas. Público. Fuentes: NOAA GOES y
NASA FIRMS.

## Datos abiertos (`/api/opendata`)

Ocho conjuntos de solo lectura, sin registro ni clave, con caché corta (60–600 s). Los GeoJSON y
`boton-rojo.json` son `FeatureCollection` con `source` y `not_official`, hasta 5 000
features. El índice los autodocumenta. Licencia (índice): los datos de origen conservan su
condición — CONAF es de CONAF, DMC dominio público, NASA/NOAA dominio público — y el cálculo de
BRASA se reusa citando la fuente.

Cada conjunto informa `count` (elementos entregados), `limit` (el tope, 5 000) y `truncated`: si
sale en `true` hubo más elementos que el tope y la respuesta viene recortada — pide una ventana más
corta (`hours` menor) o filtra por `source`. Ejemplo:

```json
{"type": "FeatureCollection", "count": 5000, "limit": 5000, "truncated": true, "features": []}
```

#### `GET /api/opendata`
Índice de los conjuntos: qué hay, con qué parámetros y qué significa cada campo. JSON. Público.

#### `GET /api/opendata/incidents.geojson`
Parámetros: `hours` entero 1–336 (48); `include_fixed` booleano (falso). Incidentes abiertos con
estado, conteos y caja. GeoJSON, caché 60 s. Fuente: NASA FIRMS y NOAA GOES agrupados por BRASA.

#### `GET /api/opendata/observations.geojson`
Parámetros: `hours` entero 1–72 (6); `source` texto hasta 64 caracteres (producto, p. ej.
`VIIRS_NOAA20_NRT`). Detecciones satelitales recientes. GeoJSON, caché 60 s. Fuente: NASA FIRMS y
NOAA GOES (dominio público).

#### `GET /api/opendata/risk.geojson`
Parámetros: `day` AAAA-MM-DD (hoy en Chile). Riesgo por comuna en el centroide: nivel 30-30-30,
nivel combinado, score y FWI. GeoJSON, caché 600 s. Fuente: Open-Meteo y BRASA.

#### `GET /api/opendata/lightning.geojson`
Parámetros: `hours` entero 1–6 (1). Destellos del GLM de GOES-19 sobre Chile. GeoJSON, caché 60 s
(ventana calculada cada 5 min). 503 si el proveedor no responde. Fuente: NOAA GOES-19 GLM —
dominio público.

#### `GET /api/opendata/smoke.geojson`
Parámetros: `hours` entero 1–6 (1). Polígonos de humo que GOES-19 detecta sobre Chile; humo de
satélite no es incendio confirmado. GeoJSON, caché 60 s (ventana calculada cada 5 min). 503 si el
proveedor no responde. Fuente: NOAA GOES-19 ABI-L2-ADPF — dominio público.

#### `GET /api/opendata/scars.geojson`
Parámetros: `days` entero 1–180 (90). Cicatrices de la temporada: un polígono por comuna con la
unión de las huellas de detecciones de sus incidentes no descartados ni fijos (`ha`,
`n_incidentes`, `desde`, `hasta`). No es perímetro oficial ni área quemada medida. Se une a lo
sumo 300 incidentes, los más recientes; si hubo más, `incidents_note` lo avisa. GeoJSON, caché
600 s. Fuente: huella BRASA de detecciones satelitales.

#### `GET /api/opendata/response.json`
Parámetros: `season` AAAA-AAAA (la más reciente por defecto). Medianas de los tiempos de respuesta
oficial (detección, aviso, despacho) de la temporada. JSON, caché 600 s. Fuente: reporte público de
CONAF (sin licencia declarada; se cita con enlace).

#### `GET /api/opendata/boton-rojo.json`
Parámetros: `day` AAAA-MM-DD (un solo día); `days` entero 1–14 (14 por defecto: los días más
recientes presentes en la tabla, que guarda hasta 14). Pronóstico oficial Botón Rojo de CONAF por
comuna y día: horas en condición, superficie que la cumple y proporción de la comuna, en el
centroide de la comuna. FeatureCollection de puntos servido como `application/json`, caché 600 s.
Con la tabla vacía responde 200 con `count: 0`. Fuente: CONAF (la información es de CONAF y se
republica citándola).


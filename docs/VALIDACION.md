# Validación de la detección contra CONAF (QA-03)

`scripts/validar_deteccion.py` responde con números la pregunta central del proyecto:
**¿qué porcentaje de los incendios que informa CONAF detectó BRASA, por tamaño, y con cuántos
minutos de ventaja o atraso?**

```bash
python scripts/validar_deteccion.py --db work.db [--km 3] [--before-h 24] [--after-h 6] [--season 2025-2026] [--json salida.json]
```

`--db` apunta a una copia de `work.db` (la base de observaciones, incidentes e incendios
oficiales; no a `brasa.db`, que tiene los datos de las personas). El script copia el archivo
a un directorio temporal con la API de respaldo de SQLite y abre la copia en solo lectura:
nunca escribe en el original, sirve aunque la base esté en WAL y no llama a la red.

## Qué mide

- Para cada incendio del reporte público de CONAF (GEPRIF), guardado en `official_fires`,
  busca el **incidente** de BRASA con la primera detección más temprana a `--km` km o menos
  del punto del reporte, dentro de la ventana `[ancla − --before-h, ancla + --after-h]`.
  Si existe, el incendio cuenta como **detectado**.
- **Ancla**: `detected_at` (`f_deteccion`) cuando CONAF la informa; si falta, `started_at`
  (`f_inicio`). Es el campo más comparable a la primera detección de BRASA. Los incendios
  **sin `f_deteccion`** se evalúan igual pero se cuentan **aparte**, en la sección
  «Sin hora de CONAF»: sin hora oficial de detección no se puede medir ventaja contra ella.
  En el JSON, cada incendio lleva `started_at` y `detected_at`, así las dos horas se ven
  cuando difieren.
- La «primera detección» de un incidente es la más antigua de sus observaciones enlazadas
  (`incident_observations` → `observations`); si un incidente no tiene enlaces se usa su
  `first_seen_at`.
- **Ventaja** = primera detección BRASA − hora CONAF, en minutos, calculada contra
  `f_deteccion` y contra `f_aviso`. **Negativo = BRASA llegó antes**. La tabla muestra
  p50 y p90 solo sobre los incendios detectados con esa hora informada.
- **Tasa de detección por superficie**: `<1 ha`, `1-10`, `10-100`, `>=100 ha` y
  `sin superficie`, sobre los incendios con `f_deteccion`.
- **Candidatos a falsa alarma**: incidentes abiertos («anomalía»/«posible», los estados sin
  confirmación oficial) sin ningún incendio de CONAF a ≤ 5 km en ±24 h alrededor del ancla.
  Es un proxy, no una certeza (ver límites).
- **Incendios de CONAF sin incidente cercano**: la lista de los no detectados.
- **Comuna**: el nombre que publica CONAF se resuelve a código territorial con
  `backend.geo.territory()` (coincidencia exacta tras normalizar tildes y mayúsculas). Los
  nombres que no calzan —o que calzan con más de una comuna— se listan en «Sin comuna
  reconocida» y la fila no se descarta.
- Con `--season` se evalúa solo una temporada (por ejemplo `2025-2026`); sin él, todas.
- Con `--json RUTA` se guarda el mismo contenido estructurado (un incendio por fila, con el
  incidente que lo detectó, la distancia y ambas ventajas). Si la base no tiene incendios,
  el script lo dice y sale con código 2 (no imprime una tabla vacía).

## Por qué esas ventanas

`--before-h 24`: BRASA suele ver el foco antes de que el reporte llegue a CONAF —esa es la
ventaja que se quiere medir— y el satélite geoestacionario pasa cada 10 minutos. 24 h hacia
atrás cubre incluso los focos que ardieron un día entero sin que nadie los reportara.
`--after-h 6`: si BRASA no vio nada hasta 6 horas después de la detección oficial, ya no
adelantó nada; pasado ese plazo la correspondencia es dudosa. `--km 3`: el punto del reporte
es el foco inicial, no el perímetro; el píxel GOES tiene ~2 km de resolución y un radio
mayor infla los aciertos con detecciones de focos vecinos.

## Qué NO mide

- **Falsos positivos reales.** Un incidente sin CONAF cerca es solo un *candidato*: puede
  ser una quema autorizada, una fuente de calor industrial, un reflejo o un incendio real
  que CONAF aún no informa (o que quedó fuera de su reporte). Separarlos exige revisión
  caso a caso; el número es una cota, no una tasa de error.
- **Incendios que CONAF no informó.** La validación solo cubre lo que está en el CSV
  oficial; BRASA podría estar detectando focos que nunca entran al registro y el script no
  los contaría como aciertos (entran como candidatos).
- **Causalidad.** Que un incidente coincida en espacio y tiempo con un incendio no prueba
  que sea el mismo foco; con `--km` grande o en zonas de quemas la coincidencia puede ser
  casual.
- **Calidad espacial.** La correspondencia es por distancia al punto del reporte, no al
  perímetro: un incendio grande detectado en su borde puede quedar fuera del radio, y una
  observación cercana puede venir de otro foco.
- **La superficie real.** `area_ha` es la cifra que publica CONAF en el parte y puede ser
  preliminar (los incendios en combate crecen después del reporte).
- **Todo el espectro temporal.** Si BRASA solo veía el incendio fuera de la ventana
  (−24 h / +6 h por omisión), cuenta como no detectado aunque haya observaciones.

## Cómo correrlo sobre un respaldo de producción

`work.db` **no contiene datos personales**: las personas, sus lugares y sus avisos viven en
`brasa.db`. El respaldo de `work.db` (el que se sube a R2 cada hora) tiene solo
observaciones satelitales, incidentes, riesgo por comuna y los reportes oficiales, así que
se puede bajar y analizar sin precauciones de datos personales.

```bash
# En la máquina con el respaldo (o tras bajar work.db / work.db.gz de R2):
python scripts/validar_deteccion.py --db work.db --json validacion.json
```

El script copia el archivo a un temporal antes de abrirlo, así que también funciona sobre
un `work.db` en uso por el servidor.

## Por qué solo cubre la temporada en curso

El CSV que CONAF publica en GitHub (`deigeprif/public`, `reporte/incendios.csv`) contiene
únicamente la temporada vigente (julio a junio): cuando empieza una temporada nueva el
archivo se reinicia. `official_fires` conserva lo que la ingesta vio en vivo, así que la
validación da una temporada completa solo después de que BRASA estuvo corriendo toda la
temporada. Las temporadas anteriores no se pueden reconstruir desde esta fuente; para eso
están los casos precalculados de `scripts/replay_case.py` (QA-02), que miden tiempos
internos pero no comparan contra CONAF.

## Medida del caso Viña del Mar 2024

El megaincendio de Valparaíso de febrero de 2024 ya está en el repo con sus 433 barridos
GOES-16 (2.667 filas, `web/data/cases/vina-del-mar-2024.goes.json`). El banco de
reproducción (`scripts/replay_case.py`, QA-02) las reinyecta sobre una base desechable y
mide cuántos minutos pasan entre la primera detección de cada incidente y su llegada a
«posible». Es la medida pendiente de `docs/PLAN_NEXT_LEVEL.md`: cuánto tarda el salto de
«anomalía» a «posible» sobre un incendio chileno real ya ocurrido.

```bash
python scripts/replay_case.py vina-del-mar-2024 --json vina.json
```

Resultado de la corrida (los números salen del comando, no de una estimación):

| incidente | primera detección | min→posible | obs | estado |
|-----------|-------------------|------------:|----:|--------|
| bad775c1  | 2024-02-02 15:10  |          10 | 2225 | posible |
| 9301f7e0  | 2024-02-02 17:00  |          20 |  325 | posible |
| 767b23b3  | 2024-02-03 12:20  |          10 |   89 | posible |
| 274ce482  | 2024-02-03 16:00  |          60 |   28 | posible |

4 incidentes · 4 fusiones · 2.667 detecciones. Resumen `minutos_hasta_posible`:
mín 10 · mediana 15 · máx 60 min (los 4 incidentes llegaron a «posible»).

Esta cifra **no prueba** el tiempo de aviso real: la reproducción corre sin la latencia
de red ni el ciclo de ingesta en vivo, y «posible» es criterio de la agrupación de BRASA,
no de CONAF — mide cuánto tarda el motor con las detecciones ya en mano, no cuándo el
vecino recibiría el aviso ni cuándo SENAPRED lo emitió.

## Cómo leer los números

- Un `%` alto con `p50` negativo es el escenario ideal: BRASA ve casi todo y antes que el
  parte oficial. `f_deteccion` es cuando el foco se reportó a CONAF (un testigo, una
  brigada, un avistamiento), no cuando el fuego empezó: una ventaja negativa grande no es
  necesariamente sospechosa.
- Los tramos chicos (`<1 ha`, `1-10`) se apagan o se reportan rápido y tienen menos
  píxeles: una tasa menor ahí es esperable y no equivale a fallar en incendios peligrosos.
- Si el número de candidatos crece mucho en el norte, revisar DET-08 del backlog
  (`docs/BACKLOG_MAESTRO.md`): desiertos, minería y plantas solares calientan de día.

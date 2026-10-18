# Features nuevas: investigación y plan

Fecha: 18 de octubre de 2026. Este documento existe para no inventar: cada dato que BRASA sume
tiene que venir de una fuente oficial o de una práctica contrastada, con su enlace. Lo que no se
pudo verificar queda listado al final como pendiente, no como hecho.

## Qué se verificó y cómo

Se leyó el portal oficial de la DMC y se contrastaron los productos con lo que BRASA ya usa.
Las citas son las páginas que se abrieron, no resúmenes de terceros.

## Fuentes oficiales

| Fuente | Qué aporta | Estado en BRASA |
|---|---|---|
| **DMC · Portal de Servicios Climáticos** — [climatologia.meteochile.gob.cl](https://climatologia.meteochile.gob.cl/application/index/menuTematicoJson) | Publica **recursos JSON y GeoJSON** para consumir por aplicaciones («Web Services», producto RE8011) y datos de **estaciones automáticas al minuto** (RE5006) y **horarios de 48 h** (RE5027). | Verificado en el portal. **No integrado todavía**: candidato para frescura en tiempo real (ver feature 1). |
| **DMC · Avisos CAP 1.2** — `archivos.meteochile.gob.cl/portaldmc/rss/rss.php` | Avisos, alertas y alarmas oficiales de viento y calor extremo por zona. | **En uso** (`backend/providers/dmc.py`): 4 avisos vigentes en producción al 18-10-2026. |
| **CONAF · Botón Rojo** (ArcGIS) y **reporte público de incendios (GEPRIF)** | Pronóstico oficial de condiciones favorables e incendios informados. | **En uso**. Producción: 94 registros de Botón Rojo y 162 incendios informados. La información es de CONAF y se muestra sin modificarla. |
| **SENAPRED** | Alertas y mensajes de emergencia a la población (incluye SAE/cell broadcast). | **Sin API pública verificada.** Su sitio no expone un servicio de alertas abierto; el proyecto ya documenta que su API interna no se usa. Pendiente de acceso formal. |

## Prácticas contrastadas

| Práctica | Fuente | Qué se toma |
|---|---|---|
| **Comparar el FWI contra su estacionalidad y promedios semanales**, no contra un número suelto | [Caribbean Fire Weather Monitor (RCC)](https://rcc.cimh.edu.bb/caribbean-fire-weather-monitor/) | La comparación semanal contra la climatología es una práctica publicada por un centro climático regional; respalda el comparador semana a semana (feature 3). |
| **Reportes ciudadanos con estructura y revisión explícita** | [Smoke Sense (EPA), vía Europe PMC](https://europepmc.org/article/MED/32159029) | El reporte ciudadano sirve cuando se pide lo mínimo (qué, dónde, cuándo, foto) y se devuelve al usuario qué pasó con su reporte; respalda la cola de moderación con estados (feature 4). |
| **La latencia es parte del dato** en productos de fuego activo por satélite | [Metacsat / producto FIR (UJA)](https://ruja.ujaen.es/server/api/core/bitstreams/37bfc98f-c321-4443-89da-8f3a443225e0/content) y [pipeline con latencia típica ~300 min](https://napier-repository.worktribe.com/OutputFile/4895321) | Un aviso sin edad del dato se lee como si fuera de ahora. BRASA ya muestra `data_as_of`; la feature 1 lo hace visible en tiempo real. |

> Nota de lectura: los dos últimos enlaces se consultaron como referencia de práctica, no como
> fuente de cifras para la interfaz. BRASA no publica números que no pueda sostener con su propia
> medición (latencia p50/p90 por fuente, que ya se calcula en la ficha de incidente).

## Features: decisión y plan

### 1. Aviso de frescura de datos en tiempo real — **implementado (backend + interfaz)**

- **Qué:** `/api/status` publica ahora `freshness: {last_ingest_at, age_seconds, stale_after_s, stale}`.
  La interfaz usa ese contrato (no hace aritmética propia) y el pill de cabecera muestra la edad
  del dato, con `aria-live` para que se anuncie cuando cambia de estado.
- **Regla:** 30 minutos, la misma que ya usan Mi zona, la ficha de incidente y el modo vecino.
- **Por qué así:** el dato que manda es la última ingesta satelital (`last_ingest_at`), no la hora
  del pronóstico. Si se cae una fuente, el pill lo dice y el mapa de focos se lee como incompleto.
- **Siguiente paso (documentado, no hecho):** sumar la estación DMC más cercana (RE5006) para
  mostrar observación real junto al pronóstico. Requiere verificar el endpoint JSON concreto y su
  frecuencia de actualización.

### 2. Historial de alertas recibidas — **implementado (backend + vista)**

- **Qué:** `/api/alerts` acepta `limit` (1–200, por defecto 50) y `before` (paginación por fecha),
  y devuelve `total`. Vista nueva `#/alertas` con todas las alertas del dispositivo, agrupadas por
  día, con nivel, lugar, distancia, canales por los que salió (push/Telegram) y enlace al mapa.
- **Datos:** ya existían (`alerts` por lugar y suscriptor). No se agregó tabla ni se duplica nada.
- **Privacidad:** la identidad sigue siendo el token aleatorio del dispositivo; no hay cuentas ni
  correos. El historial se borra con los datos de la persona (retención de 45 días de observaciones
  ya vigente para el trabajo; las alertas viven con el suscriptor).

### 3. Comparador de riesgo semana a semana — **documentado, no implementado**

- **Problema:** hoy `risk_daily` guarda el pronóstico **de hoy en adelante**. Cuando el cron
  recalcula, sobrescribe esos días: no queda «qué pronosticábamos hace siete días para el mismo
  día». Sin ese histórico no hay comparación honesta.
- **Diseño propuesto:** tabla `risk_snapshot(snapshot_date, comuna_code, target_date, level,
  level_combined, score)` escrita **una vez al día** (primer ciclo después de las 06:00 de Chile),
  y endpoint `/api/risk/{code}/trend` que compare el pronóstico de hoy para `target_date` con el de
  `snapshot_date = target_date - 7`. La frase es la de la práctica citada: «esta semana el
  pronóstico para el viernes está más alto que la semana pasada» — nunca «va a haber un incendio».
- **Costo:** ~2.400 filas/día (345 comunas × 7 días). Con retención de 90 días son ~216 mil filas:
  entra sin problema en `work.db` (que se respalda comprimido en R2).
- **Riesgo:** confundir pronóstico con observación. La etiqueta tiene que decir «pronóstico», y el
  comparador no debe existir para comunas sin snapshot previo (se muestra «sin semana anterior»).

### 4. Comunidad con moderación ágil — **parcial (ya operable) y plan**

- **Ya está:** reporte ciudadano con foto saneada (sin EXIF ni GPS), cola de moderación con
  `ADMIN_TOKEN`, estados `no_verificado → verificado/descartado`, y la foto servida solo con token
  mientras no esté aprobada. Verificado de punta a punta: sin token 403, con token 200.
- **Qué falta para que sea «ágil»** (propuesta, no implementada):
  1. **Caducidad**: un reporte de humo sin moderar en 6 h ya no le sirve a nadie. Marcar
     `descartado` por vencimiento con motivo «caducado», sin borrar.
  2. **Lote**: aprobar/descartar varios de una vez (el cuello es humano, no técnico).
  3. **Devolver el estado al autor**: hoy no sabe qué pasó con su reporte. Requiere que el token
     del dispositivo pueda consultar su propio reporte (`GET /api/reports/mine`).
  4. **Anti-abuso**: ya hay tope de 6 reportes/hora por IP; falta revisar duplicados por cercanía y
     ventana (una quema denunciada cinco veces no debe ocupar cinco lugares en la cola).

## Lo que NO se pudo verificar (queda pendiente, no se usa)

1. **API de alertas de SENAPRED**: no se encontró servicio público. Se mantiene el enlace a su
   sitio y el acceso formal sigue pendiente por decisión de la persona dueña.
2. **Endpoint JSON exacto de la DMC**: el portal es una aplicación que arma el menú por JavaScript;
   los productos RE8011/RE5006 existen, pero la ruta del JSON y su frecuencia hay que confirmarlas
   con una petición real antes de integrarlas.
3. **Marco legal de datos personales** (Ley 21.719 y su calendario): no se verificó en esta ronda.
   No se afirma nada sobre plazos ni obligaciones; antes de publicar fotos con personas identificables
   hay que revisarlo.
4. **Cifras de latencia de terceros**: las de los papers citados son de sus sistemas, no de BRASA.
   BRASA mide las suyas (latencia por sensor en la ficha de incidente) y no publica las ajenas.

# Arquitectura — BRASA Chile

## v0.2: lo que está implementado

```mermaid
flowchart LR
  G["NOAA GOES-19 FDC<br/>AWS S3, cada 10 min"] --> I
  F["NASA FIRMS<br/>VIIRS NOAA-20/21"] --> I
  I["Ingesta asíncrona<br/>services.py"] --> DB[("SQLite<br/>esquema espejo PostGIS")]
  OM["Open-Meteo<br/>pronóstico 7 días"] --> R["risk.py<br/>30-30-30 por comuna"] --> DB
  DB --> A["alerts.py<br/>radio + barlovento + deduplicación"]
  OM -. viento actual .-> A
  A --> TG[Telegram]
  A --> WP[Web Push VAPID]
  DB --> API["FastAPI /api/*"]
  C[("Casos: GOES-16 precalculado<br/>+ FIRMS SP + ERA5")] --> API
  API --> PWA["PWA sin compilación<br/>MapLibre 2D · Cesium 3D bajo demanda<br/>service worker sin conexión"]
  U[Reportes ciudadanos] --> API
  API --> MOD["/admin<br/>moderación humana"]
```

- **Un solo proceso** (uvicorn) con tareas asíncronas: ingesta cada `INGEST_INTERVAL_MIN` (10), riesgo cada `RISK_INTERVAL_MIN` (180) y sondeo de Telegram. Una falla de un proveedor se registra en `ingest_runs` y no detiene el resto. Al arrancar se rellenan las últimas 6 horas de GOES.
- **Idempotencia**: cada observación tiene un id estable por producto (`GOES19_FDCF:YYYYMMDDHHMM:fila:col`, `VIIRS_NOAA21_NRT:fecha:hhmm:lat:lon`); reingerir no duplica observaciones ni alertas.
- **Procedencia**: `ingest_runs` guarda el proveedor, el producto, la referencia de origen (clave S3 o descripción de la consulta, nunca la MAP_KEY), la hora y los conteos. `/api/status` lo expone y la interfaz muestra la antigüedad de cada fuente.
- **Territorio**: `geo.py` indexa las 345 comunas con `shapely.STRtree` (punto→comuna en microsegundos) y calcula la distancia geodésica, el rumbo y la regla de barlovento.
- **Identidad sin cuentas**: cada dispositivo recibe un token aleatorio (`POST /api/subscribers`) que viaja en `X-Brasa-Token`. No se piden correos ni teléfonos. Telegram se vincula con un código de un solo uso.
- **Frontend**: módulos ES sin compilación; un único estado (`store.js`) y, en los casos, un único reloj que sincroniza el mapa, el 3D, los gráficos y los eventos. MapLibre (servido localmente) es la base; Cesium solo se descarga al pedir 3D. El service worker deja la interfaz y los últimos datos disponibles sin conexión.
- **Seguridad**: secretos solo en el servidor; cabeceras `nosniff`, `Referrer-Policy`, `Permissions-Policy` y `X-Frame-Options`; límites por IP en las altas de dispositivos, los reportes y las pruebas de alerta; fotos re-codificadas sin metadatos; token de moderación comparado en tiempo constante; todo el HTML dinámico pasa por la plantilla con escape de `util.js`.

### Reconstrucción de casos

1. `scripts/build_case_goes.py` descarga cada barrido FDCF del período (433 en Viña 2024 y 1.007 en 2023), recorta la caja del caso y guarda los píxeles en un JSON compacto.
2. `backend/cases.py` construye la línea temporal horaria: detecciones por hora y sensor, FRP máxima, la **huella acumulada** (unión de medio píxel de radio por sensor, en un plano local en km), cuadros simplificados para el mapa y eventos derivados (primera detección, calor a más de 5 km de la huella, mayor expansión, FRP máxima y hora más activa). `scripts/build_case_timeline.py` la deja precalculada.
3. Si hay `FIRMS_MAP_KEY`, `POST /api/cases/{id}/polar` agrega VIIRS/MODIS del archivo científico y la línea temporal se recalcula. El reanálisis ERA5 se obtiene una vez y queda en caché.

## Diseño objetivo para producción

```mermaid
flowchart TD
  A[NASA FIRMS] --> I[Workers Python de ingesta]
  B[IDE Minagri / CONAF] --> I
  C[Copernicus Sentinel-2 / STAC] --> J[Worker ráster + COG]
  D[Open-Meteo] --> M[Adaptador meteorológico]
  I --> V[Validación + normalización + procedencia]
  V --> P[(PostgreSQL + PostGIS)]
  J --> O[(Object Storage / COG)]
  P --> F[FastAPI / API de consultas]
  O --> F
  M --> F
  F --> W[PWA: MapLibre + Cesium bajo demanda]
  W --> U[Exploración / filtros / línea temporal]
```

Migración desde la v0.2: el esquema SQLite replica las tablas de abajo, así que pasar a PostGIS consiste en reemplazar `db.py` y las consultas espaciales (`ST_Intersects` contra `admin_areas` en lugar de `STRtree`). Las tareas de ingesta pasan a un worker separado cuando haya más de una instancia web. Para el frontend, la recomendación cambia respecto de la v0.1: **MapLibre 2D como base** (celulares con mala señal rural) y Cesium solo para explorar en 3D.

## Entidades del dominio

- **Observation**: medición puntual del satélite, con producto, timestamp UTC, coordenadas, FRP, brillo, calidad/confianza, descarga y origen.
- **Incident**: incendio nombrado con estado, ID de origen, entidad que lo confirma y evolución de estados temporalmente versionada. Las observaciones pueden *no* pertenecer a un incidente.
- **BurnedArea**: geometría final o parcial, fecha de producción del polígono, temporalidad representada, superficie, método, calidad y fuente.
- **HistoricalSnapshot**: vista de un incidente en un instante/intervalo; solo existe con datos observados para ese momento.
- **WeatherObservation/WeatherEstimate**: medición o salida de modelo, fecha válida, modelo/estación, resolución y coordenada.
- **SourceRevision**: captura inmutable de la procedencia, URL, licencia, versión, descarga y hash.
- **AdministrativeArea**: límite poligonal oficial para filtrar por comuna y región, con origen/versionado.

## SQL base (orientativo para PostGIS)

```sql
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE data_sources (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  provider TEXT NOT NULL,
  product TEXT NOT NULL,
  original_url TEXT,
  retrieved_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  licence_note TEXT,
  source_hash TEXT,
  UNIQUE(provider, product, source_hash)
);

CREATE TABLE fire_observations (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  source_id BIGINT NOT NULL REFERENCES data_sources(id),
  provider_record_key TEXT NOT NULL,
  observed_at TIMESTAMPTZ NOT NULL,
  location GEOMETRY(Point, 4326) NOT NULL,
  frp_mw DOUBLE PRECISION,
  brightness_kelvin DOUBLE PRECISION,
  confidence_raw TEXT,
  quality_flags JSONB NOT NULL DEFAULT '{}',
  ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(source_id, provider_record_key)
);
CREATE INDEX obs_location_gist ON fire_observations USING GIST(location);
CREATE INDEX obs_time_btree ON fire_observations(observed_at DESC);

CREATE TABLE admin_areas (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  area_code TEXT NOT NULL,
  area_type TEXT NOT NULL,
  name TEXT NOT NULL,
  geom GEOMETRY(MultiPolygon,4326) NOT NULL,
  source_id BIGINT REFERENCES data_sources(id),
  UNIQUE(area_type, area_code)
);
CREATE INDEX admin_geom_gist ON admin_areas USING GIST(geom);

CREATE TABLE fire_incidents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  official_id TEXT,
  official_status TEXT,
  status_valid_at TIMESTAMPTZ,
  source_id BIGINT REFERENCES data_sources(id),
  confirmed BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE incident_polygons (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  incident_id UUID REFERENCES fire_incidents(id),
  source_id BIGINT NOT NULL REFERENCES data_sources(id),
  geom GEOMETRY(MultiPolygon,4326) NOT NULL,
  valid_at TIMESTAMPTZ,
  shape_kind TEXT NOT NULL CHECK(shape_kind IN ('final_burned_area','observed_perimeter','estimated_area')),
  method TEXT NOT NULL,
  uncertainty_note TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX incident_polygons_gist ON incident_polygons USING GIST(geom);
```

Nota: al indexar datos NOAA, usar identificadores de fuente coherentes para que reprocesamientos no dupliquen detecciones. La capa `data_sources` aquí modela lotes; en producción separar catálogo de producto y lote de ingestión. Asociar un hotspot a un incidente únicamente con criterios definidos, registrando incertidumbre. El SQL de arriba es **borrador de arquitectura**, no migración del MVP implementado.

## Endpoints objetivos

```text
GET /v1/observations?bbox=...&from=...&to=...&source=...
GET /v1/observations/stats?region_code=...&from=...&to=...
GET /v1/incidents?season=...&region_code=...
GET /v1/incidents/{id}/timeline
GET /v1/areas/{id}/perimeters?at=...
GET /v1/satellite/assets?bbox=...&from=...&cloud_max=...
GET /v1/meteo?lat=...&lon=...&at=...&kind=forecast|historical
GET /v1/sources/{id}/provenance
```

Respuestas recomendadas: GeoJSON o esquema de puntos binario/vector tiles para grandes volúmenes; cada endpoint debe exponer `data_as_of`, `source_product`, `acquisition_at`, `ingested_at`, `valid_at`, `limitations` y `licence` cuando sea relevante. Permitir `bbox` validado, límites temporales y paginación; no ofrecer búsquedas sin límite.

## Ingesta y trazabilidad

1. Scheduler regular consulta NOAA-21/NOAA-20 por región, con caché y límites. No sincronizar una solicitud externa con cada pan/zoom de usuario.
2. Retener copia del CSV original (object storage), checksum, fecha/hora de adquisición y metadatos.
3. Normalizar unidades y observaciones en WGS84 (EPSG:4326). Para región usar `ST_Intersects` / `ST_Covers` contra contorno oficial, no cajas aproximadas.
4. Upsert idempotente que tolere productos corregidos y reingestas.
5. Generar agregados y GeoJSON de baja densidad o vector tiles para frontend. Nunca usar el total de puntos de un periodo como el número oficial de incendios.
6. Anexar la actualización actual del proveedor sin borrar resultados históricos si el servidor externo falla.

## Sentinel-2 y escenarios históricos

La API STAC de Copernicus sirve para *buscar* productos, no para interpretar automáticamente un polígono de quemado. El pipeline separado debe seleccionar imágenes comparables antes/después, verificar nubosidad y geometría, reproyectar y producir mosaicos/COG. `NBR = (NIR-SWIR)/(NIR+SWIR)` y `dNBR = NBR_pre-NBR_post` son indicadores que requieren umbrales contextualizados y validación; **no** equivalen por sí solos a delimitación oficial.

El reporte debe mostrar fecha de cada imagen, escala/ resolución, máscara de nubes, método y grado de incertidumbre. Los polígonos de CONAF pueden describir extensión total final; nunca se les atribuyen timestamps de propagación que no fueron observados.

## Diseño, experiencia y accesibilidad

- Interfaz editorial cartográfica con visualización 3D como foco, filtros a la izquierda y observaciones a la derecha.
- Colores de puntos por FRP son **simbología ilustrativa**, no escala de gravedad validada.
- Modo de reproducción día a día con timestamp visible; más adelante animación intradía si observaciones reales lo permiten.
- No añadir drones, recursos terrestres ni telemetría simulada en el tablero de datos reales.
- Aplicar clustering/tiled vector layers progresivos. Un mapa 3D potente no justifica bloquear dispositivos modestos.
- Mantener fallback 2D y modo bajo consumo; idioma español de Chile, timezone `America/Santiago`, UTC en almacenamiento.

## Infraestructura y responsabilidades

- **Frontend producción:** Next.js / React + CesiumJS (bundle local, no depender de CDN público en producción), hosting estático o híbrido.
- **Backend:** FastAPI, endpoints geoespaciales y autenticación de administradores.
- **Persistencia:** Supabase PostgreSQL + PostGIS al principio; más adelante Postgres administrado si crece el dataset.
- **Ingesta:** proceso Python programado o queue worker (fuera de límites de serverless request). Separado de rendering.
- **Rásteres:** buckets compatibles con S3, Cloud Optimized GeoTIFF + servicio de teselas, CDN y política de expiración.
- **Observabilidad:** uptime, alertas por falta de novedades, tasa de fallos proveedor, últimas observaciones y tiempo de procesamiento.
- **Seguridad:** credenciales privadas del servidor, tokens de mapas públicos y restringidos por dominio, CORS controlado, rate limiting, backups y mínimo acceso.

## Riesgos principales

| Riesgo | Mitigación |
|---|---|
| Detección térmica mal interpretada | Etiquetas y metodologías; no usar `incendio activo` sin confirmación |
| Ausencia de paso satelital útil | Mostrar cobertura y latencia; no inferir que no existen incendios |
| Coordenadas fuera del territorio chileno | Límites oficiales, geometría multipoligonal, pruebas en fronteras e islas |
| Datos oficiales sin API | Integración pactada o carga programada permitida; jamás scraping agresivo |
| Productos NOAA/S-NPP discontinuados | Priorizar NOAA-21/20 y monitorizar changelogs |
| Falso contorno temporal | Representar sólo observaciones georreferenciadas con fecha real |
| Altos costos de mapas/ráster | Cache, bbox tiles, cuotas, presupuestos y avisos de gasto |
| Uso indebido para emergencias | Advertencias, enlaces oficiales, metodología y revisión de especialistas |

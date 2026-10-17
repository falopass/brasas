# Fuentes, licencias y reglas de interpretación

Revisado en octubre de 2026. Cada dato que BRASA muestra lleva su fuente y su hora; ninguna capa se completa con datos simulados.

## Detección de focos de calor

### NOAA GOES-R ABI L2 FDC (geoestacionario, cada 10 minutos)

- Producto: `ABI-L2-FDCF` (*Fire/Hot Spot Characterization*, disco completo), en AWS Open Data, sin clave:
  - `s3://noaa-goes19` — GOES-19, GOES-Este operacional desde abril de 2025 (en vivo).
  - `s3://noaa-goes16` — GOES-16, GOES-Este entre 2017 y abril de 2025 (casos 2023 y 2024). No hay archivo FDC público para enero de 2017.
- Proyección: grilla fija geoestacionaria (GOES-R PUG, vol. 5). BRASA convierte cada píxel a latitud/longitud y lo dibuja con su tamaño aproximado (~2 km en el nadir, 2–3 km en Chile central).
- Confianza según la máscara: 10/11/13 (y 30/31/33 con filtro temporal) = alta; 12/14/32/34 = media; 15/35 = baja. **Solo alta y media generan alertas.**
- Latencia típica: 10 a 20 minutos.

### NASA FIRMS (VIIRS y MODIS, órbita polar)

- API de áreas (CSV): `https://firms.modaps.eosdis.nasa.gov/api/area/csv/[MAP_KEY]/[PRODUCTO]/[oeste,sur,este,norte]/[1-5]/[fecha]`. Clave gratuita: <https://firms.modaps.eosdis.nasa.gov/api/map_key/>.
- En vivo: `VIIRS_NOAA20_NRT`, `VIIRS_NOAA21_NRT` (375 m). NOAA anunció que deja de entregar datos de **S-NPP el 2 de noviembre de 2026**: no depender de `VIIRS_SNPP_NRT`.
- Archivo científico para los casos: `VIIRS_NOAA20_SP` (desde 2018), `VIIRS_SNPP_SP` (desde 2012) y `MODIS_SP` (desde noviembre de 2000). El archivo SP se publica con meses de retraso; para fechas de los últimos 60 días BRASA usa los productos NRT.
- Ventanas de más de 5 días se consultan por tramos. La clave va en la URL: nunca se registra ni se devuelve en errores.
- FIRMS informa detecciones térmicas, no incendios confirmados.

## Territorio

- **Comunas y regiones**: Biblioteca del Congreso Nacional (BCN), mapas vectoriales, en alta resolución por región vía <https://github.com/caracena/chile-geojson>. BRASA las simplifica (unos 450 m) con `shapely.coverage_simplify`, que conserva los bordes compartidos. Las 345 comunas reemplazan las cajas aproximadas del MVP v0.1.
- Rapa Nui y el Archipiélago Juan Fernández se tratan como zonas propias. El Territorio Chileno Antártico se excluye.

## Meteorología

- **Pronóstico** (índice 30-30-30 y viento en las alertas): Open-Meteo, `api.open-meteo.com/v1/forecast`, horario, 7 días, consultas de varias ubicaciones en lotes de 50 comunas. Uso gratuito no comercial: antes de un uso comercial, contratar el plan correspondiente.
- **Reanálisis** (casos históricos): ERA5 de Copernicus vía Open-Meteo Archive, `archive-api.open-meteo.com/v1/archive`. Su resolución (~25 km) describe el ambiente general, no las ráfagas del frente de fuego.
- **Regla 30-30-30**: referencia que difunde CONAF para condiciones de propagación muy favorables. BRASA la aplica hora a hora; los niveles «alto» y «moderado» son criterios propios, documentados en `backend/risk.py`.

## Mapas base

| Capa | Fuente | Condiciones |
|---|---|---|
| Mapa (vectorial) | [OpenFreeMap](https://openfreemap.org) con el esquema OpenMapTiles y datos © OpenStreetMap | Gratuito, sin clave; con atribución. |
| Satélite | Sentinel-2 cloudless 2023 de EOX, <https://s2maps.eu> | **CC BY-NC-SA 4.0**: no comercial. Para la versión para empresas, contratar una licencia. |
| Relieve | OpenTopoMap | CC-BY-SA; servidores comunitarios de bajo volumen. |
| Sin conexión | Comunas y regiones BCN incluidas en la aplicación | Siempre disponible. |
| 3D | CesiumJS 1.145 (CDN jsDelivr) y relieve Cesium ion opcional | El token ion es público: restringirlo por dominio. |

Antes de recibir tráfico masivo, autoalojar las teselas vectoriales (por ejemplo, PMTiles de Chile) para no sobrecargar servicios comunitarios.

## Puntos de encuentro y servicios

- OpenStreetMap vía Overpass (`emergency=assembly_point`, `amenity=hospital|clinic|fire_station|police`), en caché por 24 h. La cobertura rural es incompleta. **Los puntos de encuentro oficiales los define cada municipio y SENAPRED.**

## Fuentes oficiales para contexto

- SENAPRED: <https://senapred.cl/> · Visor: <https://senapred.cl/visor-preparado/>. No se asume un feed público ni permiso de redistribución.
- CONAF: estadísticas <https://www.conaf.cl/centro-documentals/estadisticas-historicas/>. Comunas prioritarias 2026-27: pendientes de cargar desde el documento oficial (`web/data/prioritarias.json`).
- IDE Minagri (cartografía de incendios, SHP en UTM): <https://ide.minagri.gob.cl/descarga-de-capas-shp/desastres/>. Convertir con `scripts/convert_conaf.py`.
- Copernicus Data Space (Sentinel-2, STAC): <https://stac.dataspace.copernicus.eu/v1/>. Previsto para área quemada (dNBR) y sequedad de la vegetación.

## Reglas de interpretación (aplicadas en la interfaz)

1. Una detección térmica **no confirma un incendio**; su ausencia **no garantiza** que no haya fuego.
2. La **FRP** es potencia radiativa instantánea: no es energía acumulada ni superficie quemada.
3. La **huella** de un caso es la unión de píxeles calientes observados: no es un perímetro oficial y con GOES sobreestima la superficie.
4. Un **perímetro final** de CONAF se muestra como estado final, nunca como avance hora a hora.
5. Las cifras de contexto de los casos se marcan **«por verificar»** hasta contrastarlas con la fuente oficial.
6. **Nunca** se agregan drones, aeronaves, brigadas ni telemetría simulados a una vista con datos reales.

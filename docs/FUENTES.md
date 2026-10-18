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

## Fuentes oficiales (exploradas en octubre de 2026)

Exploración de solo lectura desde GitHub Actions (`.github/workflows/explorar-fuentes.yml`, `.github/scripts/explorar.py`), porque el entorno de desarrollo no llega a esos dominios. Cada fuente oficial se muestra **con su nombre, su hora y un enlace**, y nunca como si fuera de BRASA.

### En uso

| Fuente | Qué es | Acceso | Uso en BRASA |
|---|---|---|---|
| **CONAF · Botón Rojo** | Pronóstico oficial a 5 días de condiciones favorables para incendios, por comuna (horas en condición Botón Rojo y superficie). Capa del Depto. de Desarrollo e Investigación de la Gerencia de Protección contra Incendios Forestales (org. ArcGIS `geprif.conaf`, `A1ELWse9bRAi2JiV`), la del tablero <https://www.arcgis.com/apps/dashboards/41ee3c691359437aa9df2a09d7f6124e>. | `services5.arcgis.com/A1ELWse9bRAi2JiV/arcgis/rest/services/Boton_Rojo/FeatureServer/0/query`, pública, sin clave. Campos `date`, `com_id` (código de comuna), `horas`, `SUM_br_ha`, `proportion`. El tablero declara que la información es propiedad de CONAF. | Cada 3 h (`backend/providers/conaf.py`). Se muestra junto al 30-30-30, nunca como «incendio detectado». Un día con Botón Rojo pone el lugar en «día peligroso». |
| **CONAF · reporte público de incendios** | Incendios informados por CONAF en la temporada, con estado oficial (En combate, Controlado, Bajo observación, Extinguido), hora de inicio, superficie, coordenadas, comuna y ámbito. Publicado por la cuenta `deigeprif` de la Gerencia de Protección contra Incendios Forestales; lo usa, por ejemplo, el tablero de MINSAL. | `raw.githubusercontent.com/deigeprif/public/refs/heads/main/reporte/incendios.csv` (horas en hora de Chile, superficie con coma decimal). **El repositorio no declara licencia.** | Cada ciclo (10 min). Es la **única** vía a «confirmado», «controlado» y «extinguido según CONAF» de un incidente. Un incendio nuevo y no extinguido dentro del radio de un lugar genera un aviso «CONAF informa». |

**Pendiente:** pedir a CONAF autorización formal para redistribuir ambas fuentes (y avisar si cambian de formato); mientras tanto se citan siempre con enlace.

### Evaluadas y no usadas (por ahora)

- **SENAPRED, alertas vigentes:** la sección <https://senapred.cl/alertas/> es una aplicación React que consulta una API GraphQL interna (AWS AppSync) con credenciales incrustadas. No es un servicio público documentado: **BRASA no la usa** y enlaza a SENAPRED. Corresponde pedir a SENAPRED un acceso oficial (idealmente CAP).
- **«SENAPRED – Alertas vigentes por región (vista)» en ArcGIS:** la publica la organización «Incendio Arauco», no SENAPRED. No se usa como fuente oficial.
- **SIDCO (CONAF), KML de incendios en combate:** existe una exportación con clave (`sidco.conaf.cl/mapa/earth-data.php?key=…`) que un tercero dejó en un ítem público. Sin permiso de CONAF no se usa.
- **DMC (MeteoChile), avisos, alertas y alarmas en CAP 1.2:** RSS oficial <https://archivos.meteochile.gob.cl/portaldmc/rss/rss.php>, declarado «public domain». Candidata para la Fase 2 (avisos de calor extremo y viento por zona).
- **CONAF, otras capas de pronóstico** (misma organización): probabilidad de ignición (`PI`), humedad del combustible fino muerto (`HC`), viento (`VV`), humedad relativa (`HR`) y temperatura (`TP`). Candidatas para la capa de «condiciones» de la Fase 2.
- **Estadística histórica:** `if_temporadas_2010_2024` (IDE Minagri) y estadísticas de CONAF, para la sección Historia.

### Otras referencias

- SENAPRED: <https://senapred.cl/> · Visor: <https://senapred.cl/visor-preparado/>.
- CONAF: estadísticas <https://www.conaf.cl/centro-documentals/estadisticas-historicas/>. Comunas prioritarias 2026-27: pendientes de cargar desde el documento oficial (`web/data/prioritarias.json`).
- IDE Minagri (cartografía de incendios, SHP en UTM): <https://ide.minagri.gob.cl/descarga-de-capas-shp/desastres/>. Convertir con `scripts/convert_conaf.py`.
- Copernicus Data Space (Sentinel-2, STAC): <https://stac.dataspace.copernicus.eu/v1/>. Previsto para área quemada (dNBR) y sequedad de la vegetación.

## Incidentes (de puntos de calor a incendios)

`backend/incidents.py` agrupa las detecciones en **incidentes**: una detección se une a un incidente abierto si está a menos de 2 km + la media de las resoluciones de alguna de sus detecciones, y a menos de 6 h de la última. Si une a dos incidentes, se fusionan en el más antiguo.

| Estado | Regla |
|---|---|
| Señal de calor (`anomalia`) | Una sola detección confiable, o solo de confianza baja. |
| Posible incendio (`posible`) | ≥ 2 detecciones confiables en momentos distintos, o 2 sensores distintos (GOES + VIIRS). |
| Visto por vecinos (`reportado`) | Además, un reporte ciudadano verificado por moderación a ≤ 3 km. |
| Confirmado por CONAF (`confirmado`) / `controlado` | Unido a un incendio del reporte público de CONAF a ≤ 3 km (+ medio píxel) y en la misma ventana de tiempo. BRASA no confirma por su cuenta. |
| Sin calor nuevo (`extinguido`) | 24 h sin detecciones, o extinguido según CONAF. |

**Fuentes de calor fijas probables:** volcanes activos conocidos (`web/data/persistent_hotspots.json`, con su fuente) y celdas de ~2 km con calor en ≥ 8 días distintos de los últimos 30 (industria, antorchas). Si **toda** la evidencia de un incidente cae en ellas, se muestra pero no genera avisos ni pone un lugar en urgente.

## Reglas de interpretación (aplicadas en la interfaz)

1. Una detección térmica **no confirma un incendio**; su ausencia **no garantiza** que no haya fuego.
2. La **FRP** es potencia radiativa instantánea: no es energía acumulada ni superficie quemada.
3. La **huella** de un caso es la unión de píxeles calientes observados: no es un perímetro oficial y con GOES sobreestima la superficie.
4. Un **perímetro final** de CONAF se muestra como estado final, nunca como avance hora a hora.
5. Las cifras de contexto de los casos se marcan **«por verificar»** hasta contrastarlas con la fuente oficial.
6. Un incidente es una **agrupación de evidencia**, no un perímetro: «confirmado» solo con CONAF.
7. **Nunca** se agregan drones, aeronaves, brigadas ni telemetría simulados a una vista con datos reales.

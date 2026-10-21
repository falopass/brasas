# Fuentes, licencias y reglas de interpretación

Revisado en octubre de 2026. Cada dato que BRASA muestra lleva su fuente y su hora; ninguna capa se completa con datos simulados.

## Cómo se recorta a Chile

Cada proveedor limita lo que entrega de una forma distinta. Esta tabla es el contrato para auditar la aplicación: qué dato entra, con qué demora y dónde se corta el territorio. La columna «En el código» apunta al punto exacto donde se aplica el recorte.

| Fuente | Qué entrega | Latencia típica | Método de recorte | En el código |
|---|---|---|---|---|
| `firms` | Detecciones térmicas VIIRS (375 m) y MODIS (1 km), en vivo (NRT) y archivo científico (SP). | NRT: 1 a 3 h. SP: meses de retraso. | Caja `CHILE_BBOX` al pedir la API y, después, polígono comunal con tolerancia costera de 0,16°. | `backend/services.py:27`, `backend/providers/firms.py:94` |
| `goes` | Píxeles calientes del ABI-L2-FDCF (~2 km en el nadir, 3-4 km en Chile central), cada 10 min. | 10 a 20 min. | Caja `READ_WINDOW` `(-81.5, -56.5, -66.0, -17.0)`, sin polígono comunal. | `backend/providers/goes.py:31`, `backend/providers/goes.py:154` |
| `glm` | Destellos de rayos GLM-L2-LCFA con calidad nominal. | Archivos cada ~20 s; se consulta la última hora. | Caja `goes.READ_WINDOW`, heredada; sin polígono comunal. | `backend/providers/glm.py:63`, `backend/providers/glm.py:94` |
| `smoke` | Celdas y polígonos de humo del ABI-L2-ADPF (~10 min; de noche no hay detección). | ~10 min; se consulta la última hora. | Caja `goes.READ_WINDOW`, heredada; sin polígono comunal. | `backend/providers/smoke.py:68`, `backend/providers/smoke.py:129` |
| `overpass` | Puntos de encuentro, hospitales, clínicas, bomberos y Carabineros de OpenStreetMap. | A demanda; caché de 24 h por celda de 0,01°. | Sin recorte nacional: radio de 12 km alrededor del lugar consultado. | `backend/providers/overpass.py:61` |
| `weather` | Pronóstico horario, condiciones actuales, reanálisis ERA5, MP2,5 y lluvia de Open-Meteo. | Pronóstico a 7 días; se consulta al recalcular el riesgo por comuna (por defecto cada 3 h) y a demanda para las condiciones actuales. | Sin recorte propio: consulta las coordenadas que recibe (centros y puntos de evaluación de cada comuna). | `backend/providers/weather.py:79`, `backend/services.py:448` |
| `dmc` | Avisos CAP 1.2 de viento y calor extremo, con zonas y polígonos. | Avisos vigentes; se consulta cada hora. | Sin recorte en el proveedor: el polígono de cada zona se cruza con las comunas; si no hay polígono, se usa el nombre de la zona. | `backend/providers/dmc.py:145`, `backend/services.py:605` |
| `conaf` | Botón Rojo (5 días, por comuna), incendios informados (CSV de GEPRIF) y condiciones PI/HC/VV/HR/TP. | Botón Rojo cada 3 h; incendios cada ciclo (~10 min); condiciones: se revisan cada 3 h y las capas se publican una vez al día. | Botón Rojo: sin recorte propio, la capa declara `com_id`. Incendios: sin recorte geográfico, se aceptan las filas con coordenadas y fecha válidas. Condiciones: cada polígono se cruza con las comunas. | `backend/providers/conaf.py:144`, `backend/providers/conaf.py:332` |
| `conaf_dei` | Perímetro final oficial de un incendio (capa «Perimetro_final» de GEPRIF-CONAF), para la ficha del incidente. | Por evento; se consulta al ingerir el reporte de CONAF, a lo sumo una vez al día por incendio (apagado por defecto hasta la autorización de OFI-03). | Cuadro de ±0,2° alrededor del punto informado por CONAF y elección del polígono que contiene o queda más cerca del punto. | `backend/providers/conaf_dei.py:59`, `backend/providers/conaf_dei.py:127` |
| `noaa` | Índice ONI de El Niño/La Niña (anomalía de la región Niño 3.4). | Media móvil de 3 meses; se lee la última fila publicada. | Sin recorte: es un índice global. | `backend/providers/noaa.py:68` |

Notas:

- **La caja no es el recorte fino.** GOES, GLM y humo comparten `READ_WINDOW`, una caja que también cubre territorio de Argentina, Bolivia y Perú. Las detecciones de GOES que caen fuera de Chile se guardan con `comuna_code = None` (`backend/services.py:441`); GLM y humo se publican dentro de la misma caja, sin asignación comunal. FIRMS, en cambio, descarta cada punto fuera del polígono comunal.
- **Dos constantes para la misma caja.** `CHILE_BBOX` (`backend/services.py:27`) y `READ_WINDOW` (`backend/providers/goes.py:31`) tienen valores idénticos, pero viven en módulos distintos.
- **CONAF incendios no filtra por territorio.** `parse_fires` (`backend/providers/conaf.py:144`) acepta cualquier fila con latitud, longitud, identificador y fecha de inicio válidos; el recorte depende de que el CSV sea solo de Chile. Queda como hallazgo para decidir aparte.

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
- **Incendios nominados (CONAF-GEPRIF)**: la comuna de `web/data/incendios-nominados.json` y de `web/data/historia-comunas.json` es la que registra la capa `PUNTOS_DE_INICIO_2002_2024_MAYOR_A_50_HA` para el punto de inicio. Ese punto puede caer en la comuna vecina (180 de 3.214 filas, 5,6 %, al comparar con el trazado BCN); BRASA no reescribe la atribución de la fuente y la superficie también es la de la capa. La vista Historia lo declara junto a los datos (FUEGO-61).
- **Exposición (Censo 2024, INE)**: población, viviendas y hogares por comuna (`web/data/censo_2024.json`, generado por `scripts/local/build_censo.py` — ya documentado desde OFI-07; esta sección solo registra que ahora la ficha de comuna lo muestra). Capa pública `COMUNA_DPA_INDICADORES` del servicio `CENSO2024_V2_gdb` (`services5.arcgis.com/hUyD8u3TeZLKPe4T/.../FeatureServer/0/query`), la misma que alimenta el «Dashboard de indicadores» de <https://censo2024.ine.gob.cl/resultados/>. Licencia del contenido INE: **CC BY-SA 4.0**, con reconocimiento al INE (<https://www.ine.gob.cl/terminos-de-uso-y-licencia-de-datos-abiertos>). Alternativas revisadas: microdatos comuna-área (`storage.googleapis.com/bktdescargascenso2024/viv_hog_per_censo2024.zip`, ~300 MB) y las bases manzana–entidad; ambas más pesadas de lo que necesita la exposición. La comuna 12202 (Antártica) queda fuera del territorio de BRASA. Consultado el 19 de octubre de 2026.
- **Exposición (zona de interfaz urbano-forestal, CONAF GEPRIF)**: hectáreas y porcentaje de cada comuna en zona de interfaz (`web/data/interfaz.json`, generado por `scripts/local/build_interfaz.py`). Capa `riesgo_dissolve_point` del catálogo `services5.arcgis.com/A1ELWse9bRAi2JiV` (org `geprif.conaf`), la que alimenta el tablero «Zonas Interfaz» del hub <https://deigeprif.com> (ítem `09532374973a495bb185fcbe55711cd3`). Son zonas disueltas por comuna entregadas como puntos con `sup_ha` y `dpa_cod`; los polígonos solo existen como teselas vectoriales, así que la superficie es la que declara la capa y el cruce con los polígonos BCN verifica la asignación. Licencia: **uso público citando a CONAF como fuente**, declaración del ítem del tablero; la capa no declara licencia propia y la puerta de OFI-03 sigue firme. Catálogo consultado el 19 de octubre de 2026; capa re-descargada el 20 de octubre de 2026 con resultado idéntico.

## Meteorología

- **Pronóstico** (índice 30-30-30 y viento en las alertas): Open-Meteo, `api.open-meteo.com/v1/forecast`, horario, 7 días, consultas de varias ubicaciones en lotes de 50 comunas. Uso gratuito no comercial: antes de un uso comercial, contratar el plan correspondiente.
- **Reanálisis** (casos históricos): ERA5 de Copernicus vía Open-Meteo Archive, `archive-api.open-meteo.com/v1/archive`. Su resolución (~25 km) describe el ambiente general, no las ráfagas del frente de fuego.
- **Calidad del aire** (humo en la ficha de comuna, AGUA-05): MP2,5 pronosticado del modelo CAMS de Copernicus vía Open-Meteo Air Quality, `air-quality-api.open-meteo.com/v1/air-quality`, horario, 2 días, en el centro de cada comuna. Mismo uso gratuito no comercial que el pronóstico. Es un pronóstico de modelo, no una medición: las estaciones oficiales son las del SINCA (MMA). Consultado el 19 de octubre de 2026.
- **Regla 30-30-30**: referencia que difunde CONAF para condiciones de propagación muy favorables. BRASA la aplica hora a hora; los niveles «alto» y «moderado» son criterios propios, documentados en `backend/risk.py`.
- **Escenario estimado de propagación** (`backend/fwi.py`, `propagation_scenario`, FUEGO-02): velocidad y dirección dominante de avance en la ficha del incidente. Modelo: el ajuste viento + pendiente del sistema canadiense FBP (FCFDG 1992, informe ST-X-3, ecs. 39-51; Wotton et al. 2009, GLC-X-10) — la pendiente se convierte en un «viento equivalente» ladera arriba y ambos se suman como vectores; el FFMC del día aporta la humedad del combustible fino vía el ISI; la velocidad sale de la curva ROS del combustible de referencia **O-1b** (pasto en pie, totalmente curado). Supuestos a la vista en la respuesta de la API: viento y FFMC del centro de la comuna, combustible de referencia que no es el matorral chileno y, mientras no haya DEM, terreno plano. **Qué NO es**: no es una predicción, ni el perímetro ni el frente del incendio; por eso se rotula «escenario estimado».

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
| **CONAF · condiciones de pronóstico (PI/HC/VV/HR/TP)** | Pronóstico oficial diario del «Pronóstico de Riesgo» de GEPRIF: probabilidad de ignición, humedad del combustible fino muerto, viento, humedad relativa y temperatura, en grilla de ~2 km para 5 días. | `services5.arcgis.com/A1ELWse9bRAi2JiV/arcgis/rest/services/{PI,HC,VV,HR,TP}/FeatureServer/{0..4}/query`, público, sin clave. Campos `date`, `var`, `label` (clase) y `count_` (celdas del polígono disuelto). Licencia «uso público con cita a CONAF» declarada solo en algunos ítems: **confirmación por capa pendiente en el correo de OFI-03**. | Revisión de la firma de capas cada 3 h; al cambiar, la descarga corre por tandas (`backend/services.py`). Se resume por comuna con la peor clase del día (la mayor en PI/VV/TP, la más seca en HC/HR) y se muestra en la ficha de comuna como «Condiciones oficiales de CONAF», separado del 30-30-30 propio. |
| **DMC · avisos, alertas y alarmas (CAP 1.2)** | Avisos oficiales de la Dirección Meteorológica de Chile (MeteoChile) en formato CAP 1.2, con evento, severidad, vigencia y las zonas afectadas con su polígono. El RSS se declara «public domain». | RSS <https://archivos.meteochile.gob.cl/portaldmc/rss/rss.php> (público, sin clave) y un XML CAP por aviso. | Cada hora (`backend/providers/dmc.py`). Solo viento y calor extremo, que son los que cambian el comportamiento del fuego. El polígono de cada zona se cruza con las comunas reales; si el CAP no trae polígono se usa el nombre de la zona. Comprobado el 18 de octubre de 2026: 13 avisos, 4 de viento, uno de ellos sin polígono (Juan Fernández). |

**Pendiente:** pedir a CONAF autorización formal para redistribuir ambas fuentes (y avisar si cambian de formato); mientras tanto se citan siempre con enlace.

**Vigilancia semanal (OPS-02).** La prueba de humo de los lunes (`.github/scripts/fuentes_salud.py`) cubre, además del CSV de incendios, el FDCF, FIRMS, Open-Meteo y DMC, desde el 19 de octubre de 2026 también:

- Botón Rojo de CONAF: `services5.arcgis.com/A1ELWse9bRAi2JiV/arcgis/rest/services/Boton_Rojo/FeatureServer/0/query`.
- Repositorio público de GEPRIF: `raw.githubusercontent.com/deigeprif/public/refs/heads/main/reporte/incendios.csv`.
- Rayos GLM de GOES-19: `GLM-L2-LCFA` en `noaa-goes19.s3.amazonaws.com` (publicado en `/api/opendata/lightning.geojson`).
- Humo ABI-L2-ADPF: `ABI-L2-ADPF` en `noaa-goes19.s3.amazonaws.com` (publicado en `/api/opendata/smoke.geojson`).

### Evaluadas y no usadas (por ahora)

- **SENAPRED, alertas vigentes:** la sección <https://senapred.cl/alertas/> es una aplicación React que consulta una API GraphQL interna (AWS AppSync) con credenciales incrustadas. No es un servicio público documentado: **BRASA no la usa** y enlaza a SENAPRED. Corresponde pedir a SENAPRED un acceso oficial (idealmente CAP).
- **«SENAPRED – Alertas vigentes por región (vista)» en ArcGIS:** la publica la organización «Incendio Arauco», no SENAPRED. No se usa como fuente oficial.
- **SIDCO (CONAF), KML de incendios en combate:** existe una exportación con clave (`sidco.conaf.cl/mapa/earth-data.php?key=…`) que un tercero dejó en un ítem público. Sin permiso de CONAF no se usa.
- **DMC, otros eventos del mismo CAP:** tormentas eléctricas, lluvia y nevadas. El feed los trae, pero **BRASA no los muestra**: en un día de incendio no cambian qué hacer y taparían el aviso de viento. Si más adelante se usa el rayo como causa de ignición, la fuente ya está leída en `backend/providers/dmc.py`.
- **CONAF, otras capas de pronóstico** (misma organización): probabilidad de ignición (`PI`), humedad del combustible fino muerto (`HC`), viento (`VV`), humedad relativa (`HR`) y temperatura (`TP`). **En uso desde OFI-18** (tabla «En uso»); los endpoints están en «Hub GEPRIF-DEI y catálogo ArcGIS» más abajo.
- **Estadística histórica:** `if_temporadas_2010_2024` (IDE Minagri) y estadísticas de CONAF, para la sección Historia.

### Otras referencias

- SENAPRED: <https://senapred.cl/> · Visor: <https://senapred.cl/visor-preparado/>.
- CONAF: estadísticas <https://www.conaf.cl/centro-documentals/estadisticas-historicas/>. Comunas prioritarias 2026-27: CONAF informó 90 comunas priorizadas en el COGRID del 10-sep-2026 (<https://www.conaf.cl/gobierno-se-anticipa-a-eventual-complejo-escenario-estival-y-presenta-programa-para-la-prevencion-y-mitigacion-de-incendios-forestales/>) y entregó los planes a los municipios, pero al 19-oct-2026 no ha publicado el listado en un documento oficial (ni noticias, ni el centro documental, ni el catálogo ArcGIS de GEPRIF; las notas regionales del Programa de Empleo — Valparaíso anuncia 19 comunas sin detallarlas, La Araucanía reparte cupos en sus 32 — y el gestor documental de prevención tampoco lo traen). `web/data/prioritarias.json` sigue sin verificar; se carga solo cuando aparezca el documento.
- IDE Minagri (cartografía de incendios, SHP en UTM): <https://ide.minagri.gob.cl/descarga-de-capas-shp/desastres/>. Convertir con `scripts/convert_conaf.py`.
- Copernicus Data Space (Sentinel-2, STAC): <https://stac.dataspace.copernicus.eu/v1/>. Previsto para área quemada (dNBR) y sequedad de la vegetación.

### Hub GEPRIF-DEI (deigeprif.com) y catálogo ArcGIS

Verificado el 19 de octubre de 2026 en `docs/research/fuentes-meteologix-geprif.md` (INV-FUENTES).

- **`deigeprif.com`** es el hub público oficial del Departamento de Estudios e Investigación de la Gerencia de Protección contra Incendios Forestales de CONAF (GEPRIF-DEI): GitHub Pages que sirve una ArcGIS Experience con los tableros del departamento (Pronóstico de Riesgo, Botón Rojo, Reporte de temporada, Zonas Interfaz, FIRMS, GOES). **`meteograma.deigeprif.com`** es Pyrocast, su visor público de meteogramas por punto (GFS + ECMWF, índice HDWI, hindcast y capa FIRMS), sin API documentada. Ambos sirven como enlaces de referencia oficial en las fichas de BRASA.
- **Catálogo ArcGIS**: `services5.arcgis.com/A1ELWse9bRAi2JiV/arcgis/rest/services` lista ~80 FeatureServers públicos con consulta anónima y exportación a GeoJSON/CSV/KML. Las capas que importan:
  | Recurso | Frecuencia | Uso previsto |
  |---|---|---|
  | `PI`, `HC`, `VV`, `HR`, `TP` | Diaria; 5 capas por servicio (día 0 a 4) | **En uso**: «Condiciones oficiales de CONAF» en la ficha de comuna (OFI-18) |
  | `Perimetro_final` | Por evento | Perímetro oficial en la ficha de incidente (regla 4). Integrado en `backend/providers/conaf_dei.py` pero **apagado** (`CONAF_PERIMETRO_ENABLED`) hasta que el correo de OFI-03 confirme la licencia del servicio |
  | `PERÍMETROS_HISTORICOS_2014_2024…` y `PUNTOS_DE_INICIO_2002_2024_MAYOR_A_50_HA` | Estáticos | Historia: cicatrices e incendios nominados ≥50 ha |
  | `incendios_base` | Temporada en curso | Respaldo del CSV de incendios |
  | `firms` | Continua | Detecciones ya cruzadas con comuna/provincia/región; redundancia, no reemplazo del S3 de NOAA |
  | `riesgo_dissolve_point` (+ teselas `riesgo_interfaz_tiled`, leyenda `riesgo_legend`) | Estática | **En uso**: zona de interfaz urbano-forestal por comuna, en la ficha de Riesgo (OFI-08) |
- **Condición de uso**: los ítems «Zonas Interfaz» y «FIRMS» declaran que los datos son **de uso público, citando a CONAF como fuente**. La declaración aparece en esos dos ítems, no en todo el catálogo: **cada capa nueva se verifica antes de redistribuirla** y el permiso formal por ítem sigue la puerta de OFI-03 (correo a GEPRIF).
- **Regla de operación**: BRASA **solo consulta** (`Query` de lectura); nunca escribe en esos servicios. Parte del catálogo tiene habilitada la escritura anónima, una mala configuración del lado de CONAF: se avisa por el canal privado del correo de OFI-03, no en público.

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

## Recomendaciones de la sección «Prepárate» (CONT-05)

Cada recomendación de `web/js/views/preparate.js` enlaza su fuente oficial en la propia vista. Enlaces comprobados con sonda GET el 19 de octubre de 2026.

| Fuente | Respalda |
|---|---|
| SENAPRED, kit de emergencia — <https://senapred.cl/kit-de-emergencia/> | La mochila: agua, alimentos, medicamentos y recetas, documentos, linterna y radio, dinero, ropa y frazada, llaves. **Confirma el dato «dos litros de agua por persona al día»** (provisiones para 48-72 h, más dos litros adicionales por día como supervivencia). |
| SENAPRED, Familia Preparada — <https://senapred.cl/familia-preparada/> | El plan familiar (punto de encuentro, rutas, contacto fuera de la zona, necesidades especiales). |
| SENAPRED, incendios forestales — <https://senapred.cl/incendios-forestales/> | El 99 % de origen humano; mantenerse informado; evacuar a pie; ropa adecuada y cubrir vías respiratorias; no dejar animales amarrados; mensajes de texto en vez de llamadas; no regresar al área quemada; quemas con aviso a CONAF, herramientas con chispas, fogatas y colillas. |
| SENAPRED, humo de incendios forestales — <https://senapred.cl/humo-de-incendio-forestal/> | Mascarillas N95/KN95 y antiparras; qué hacer atrapado por el humo. |
| CONAF, «¿Cómo preparo mi casa y entorno frente a los incendios forestales?» — <https://www.conafprevencionincendios.cl/documento/manuales/> (PDF, 16 MB) | La lista «mi casa o parcela preparada»: techo y canaletas, franja de 1,5 m, poda, pasto y matorrales, leña y combustibles, cercos, manguera y fuente de agua. |
| CONAF, Manual Comunitario 2022 (Comunidad Preparada) — <https://oficinavirtual.conaf.cl/archivos/recursos/insumos_tecnicos/Proteccion%20de%20Incendios%20Forestales/Manual%20comunitario%20%202022.pdf> | Rutas de escape y punto de reunión, contacto fuera del área, auto con combustible, acceso despejado, cargador de celular, revisión de techos tras el incendio y riesgo de aluvión en suelo quemado. |
| CONAF, Comunidades Preparadas — <https://www.conaf.cl/incendios/prevencion-y-mitigacion/comunidades-preparadas-frente-a-los-incendios-forestales/> | La coordinación con vecinos. |
| MINSAL, División de Emergencias Sanitarias — <https://degreyd.minsal.cl/que-hacer-en-caso-de-incendios-forestales/> | Salir de inmediato al evacuar, cortar electricidad y gas, no fogatas ni colillas, retirar la basura. |
| SENADIS — <https://www.senadis.gob.cl/sala_prensa/d/noticias/9166/que-hacer-en-caso-de-emergencia> y <https://www.senadis.gob.cl/descarga/i/8212/documento> | La sección «si necesitas ayuda para salir» (ya enlazada). |
| SENAPRED, Dimensión Animal — <https://senapred.cl/dimension-animal/> y PDFs en bibliogrd.senapred.gob.cl | «Mascotas y animales de la parcela» (ya enlazada). |

Evaluadas y descartadas como enlace (contenido correcto, pero responden 403 a toda sonda GET automatizada desde servidores; funcionan en un navegador): gob.cl (`/noticias/` sobre evacuación y números de emergencia), denunciaseguro.cl (*4242, Subsecretaría de Prevención del Delito) y subprevenciondeldelito.gob.cl (timeout). Esas recomendaciones quedan respaldadas por SENAPRED y MINSAL; el *4242 de Denuncia Seguro se menciona en el texto sin enlace.

## Reglas de interpretación (aplicadas en la interfaz)

1. Una detección térmica **no confirma un incendio**; su ausencia **no garantiza** que no haya fuego.
2. La **FRP** es potencia radiativa instantánea: no es energía acumulada ni superficie quemada.
3. La **huella** de un caso es la unión de píxeles calientes observados: no es un perímetro oficial y con GOES sobreestima la superficie.
4. Un **perímetro final** de CONAF se muestra como estado final, nunca como avance hora a hora.
5. Las cifras de contexto de los casos se marcan **«por verificar»** hasta contrastarlas con la fuente oficial.
6. Un incidente es una **agrupación de evidencia**, no un perímetro: «confirmado» solo con CONAF.
7. **Nunca** se agregan drones, aeronaves, brigadas ni telemetría simulados a una vista con datos reales.

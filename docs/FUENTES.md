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
- **Exposición (Censo 2024, INE)**: población, viviendas y hogares por comuna (`web/data/censo_2024.json`, generado por `scripts/local/build_censo.py`). Capa pública `COMUNA_DPA_INDICADORES` del servicio `CENSO2024_V2_gdb` (`services5.arcgis.com/hUyD8u3TeZLKPe4T/.../FeatureServer/0/query`), la misma que alimenta el «Dashboard de indicadores» de <https://censo2024.ine.gob.cl/resultados/>. Licencia del contenido INE: **CC BY-SA 4.0**, con reconocimiento al INE (<https://www.ine.gob.cl/terminos-de-uso-y-licencia-de-datos-abiertos>). Alternativas revisadas: microdatos comuna-área (`storage.googleapis.com/bktdescargascenso2024/viv_hog_per_censo2024.zip`, ~300 MB) y las bases manzana–entidad; ambas más pesadas de lo que necesita la exposición. La comuna 12202 (Antártica) queda fuera del territorio de BRASA. Consultado el 19 de octubre de 2026.

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
| **DMC · avisos, alertas y alarmas (CAP 1.2)** | Avisos oficiales de la Dirección Meteorológica de Chile (MeteoChile) en formato CAP 1.2, con evento, severidad, vigencia y las zonas afectadas con su polígono. El RSS se declara «public domain». | RSS <https://archivos.meteochile.gob.cl/portaldmc/rss/rss.php> (público, sin clave) y un XML CAP por aviso. | Cada hora (`backend/providers/dmc.py`). Solo viento y calor extremo, que son los que cambian el comportamiento del fuego. El polígono de cada zona se cruza con las comunas reales; si el CAP no trae polígono se usa el nombre de la zona. Comprobado el 18 de octubre de 2026: 13 avisos, 4 de viento, uno de ellos sin polígono (Juan Fernández). |

**Pendiente:** pedir a CONAF autorización formal para redistribuir ambas fuentes (y avisar si cambian de formato); mientras tanto se citan siempre con enlace.

### Evaluadas y no usadas (por ahora)

- **SENAPRED, alertas vigentes:** la sección <https://senapred.cl/alertas/> es una aplicación React que consulta una API GraphQL interna (AWS AppSync) con credenciales incrustadas. No es un servicio público documentado: **BRASA no la usa** y enlaza a SENAPRED. Corresponde pedir a SENAPRED un acceso oficial (idealmente CAP).
- **«SENAPRED – Alertas vigentes por región (vista)» en ArcGIS:** la publica la organización «Incendio Arauco», no SENAPRED. No se usa como fuente oficial.
- **SIDCO (CONAF), KML de incendios en combate:** existe una exportación con clave (`sidco.conaf.cl/mapa/earth-data.php?key=…`) que un tercero dejó en un ítem público. Sin permiso de CONAF no se usa.
- **DMC, otros eventos del mismo CAP:** tormentas eléctricas, lluvia y nevadas. El feed los trae, pero **BRASA no los muestra**: en un día de incendio no cambian qué hacer y taparían el aviso de viento. Si más adelante se usa el rayo como causa de ignición, la fuente ya está leída en `backend/providers/dmc.py`.
- **CONAF, otras capas de pronóstico** (misma organización): probabilidad de ignición (`PI`), humedad del combustible fino muerto (`HC`), viento (`VV`), humedad relativa (`HR`) y temperatura (`TP`). Candidatas para la capa de «condiciones» de la Fase 2. Endpoints ya verificados: ver «Hub GEPRIF-DEI y catálogo ArcGIS» más abajo.
- **Estadística histórica:** `if_temporadas_2010_2024` (IDE Minagri) y estadísticas de CONAF, para la sección Historia.

### Otras referencias

- SENAPRED: <https://senapred.cl/> · Visor: <https://senapred.cl/visor-preparado/>.
- CONAF: estadísticas <https://www.conaf.cl/centro-documentals/estadisticas-historicas/>. Comunas prioritarias 2026-27: CONAF informó 90 comunas priorizadas en el COGRID del 10-sep-2026 (<https://www.conaf.cl/gobierno-se-anticipa-a-eventual-complejo-escenario-estival-y-presenta-programa-para-la-prevencion-y-mitigacion-de-incendios-forestales/>) y entregó los planes a los municipios, pero al 19-oct-2026 no ha publicado el listado en un documento oficial (ni noticias, ni el centro documental, ni el catálogo ArcGIS de GEPRIF). `web/data/prioritarias.json` sigue sin verificar; se carga solo cuando aparezca el documento.
- IDE Minagri (cartografía de incendios, SHP en UTM): <https://ide.minagri.gob.cl/descarga-de-capas-shp/desastres/>. Convertir con `scripts/convert_conaf.py`.
- Copernicus Data Space (Sentinel-2, STAC): <https://stac.dataspace.copernicus.eu/v1/>. Previsto para área quemada (dNBR) y sequedad de la vegetación.

### Hub GEPRIF-DEI (deigeprif.com) y catálogo ArcGIS

Verificado el 19 de octubre de 2026 en `docs/research/fuentes-meteologix-geprif.md` (INV-FUENTES).

- **`deigeprif.com`** es el hub público oficial del Departamento de Estudios e Investigación de la Gerencia de Protección contra Incendios Forestales de CONAF (GEPRIF-DEI): GitHub Pages que sirve una ArcGIS Experience con los tableros del departamento (Pronóstico de Riesgo, Botón Rojo, Reporte de temporada, Zonas Interfaz, FIRMS, GOES). **`meteograma.deigeprif.com`** es Pyrocast, su visor público de meteogramas por punto (GFS + ECMWF, índice HDWI, hindcast y capa FIRMS), sin API documentada. Ambos sirven como enlaces de referencia oficial en las fichas de BRASA.
- **Catálogo ArcGIS**: `services5.arcgis.com/A1ELWse9bRAi2JiV/arcgis/rest/services` lista ~80 FeatureServers públicos con consulta anónima y exportación a GeoJSON/CSV/KML. Las capas que importan:
  | Recurso | Frecuencia | Uso previsto |
  |---|---|---|
  | `PI`, `HC`, `VV`, `HR`, `TP` | Diaria; 5 capas por servicio (día 0 a 4) | Capa oficial de condiciones de pronóstico |
  | `Perimetro_final` | Por evento | Perímetro oficial en la ficha de incidente (regla 4) |
  | `PERÍMETROS_HISTORICOS_2014_2024…` y `PUNTOS_DE_INICIO_2002_2024_MAYOR_A_50_HA` | Estáticos | Historia: cicatrices e incendios nominados ≥50 ha |
  | `incendios_base` | Temporada en curso | Respaldo del CSV de incendios |
  | `firms` | Continua | Detecciones ya cruzadas con comuna/provincia/región; redundancia, no reemplazo del S3 de NOAA |
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

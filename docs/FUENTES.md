# Registro de fuentes verificadas (octubre de 2026)

## NASA FIRMS — detecciones térmicas

- Área CSV: <https://firms.modaps.eosdis.nasa.gov/api/area/>
- Clave gratuita: <https://firms.modaps.eosdis.nasa.gov/api/map_key/>
- Endpoint de datos: `/api/area/csv/[MAP_KEY]/[SOURCE]/[west,south,east,north]/[1-5]/[fecha_opcional]`
- Productos recientes elegidos: `VIIRS_NOAA20_NRT`, `VIIRS_NOAA21_NRT`.
- Producto de consulta retrospectiva inicial: `MODIS_SP`; verificar disponibilidad del archivo para la fecha requerida. Para historial amplio o retrocesos grandes hay que desarrollar carga por lotes y preservar productos con versionado.
- NASA indica que los datos FIRMS son detecciones de focos térmicos, no un catálogo de incendios oficialmente confirmados.
- NOAA anunció el cese de entrega S-NPP el 2 de noviembre de 2026: <https://www.nesdis.noaa.gov/news/cessation-of-suomi-national-polar-orbiting-partnership-s-npp-data-users-onafter-november-2-2026>.

## CONAF / IDE Minagri — cartografía histórica

- <https://ide.minagri.gob.cl/descarga-de-capas-shp/desastres/>
- Hay localizaciones y polígonos de incendios de magnitud en múltiples temporadas; deben descargarse de las fuentes oficiales, validarse y convertir su CRS de origen a WGS84.
- La página describe origen del registro en SIDCO/CENCOR para puntos y cartografía referencial para incendios de magnitud. **No es un API temporal de perímetros minuto a minuto**.
- Reportes estadísticos de CONAF: <https://www.conaf.cl/mapas-incendios-forestales/ocurrencia-nacional.htm>. No se ha verificado una API oficial estable para exportarlos; no hacer scraping automático sin revisión.
- Estadísticas históricas: <https://www.conaf.cl/centro-documentals/estadisticas-historicas/>.

## SENAPRED — alertas oficiales

- Web: <https://senapred.cl/>
- Visor: <https://senapred.cl/visor-preparado/>
- Prioritario para contexto oficial y seguridad. No asumir un feed JSON público ni permiso de redistribución hasta verificar documentación o convenio.

## Copernicus Data Space — Sentinel-2

- Catálogo STAC: <https://stac.dataspace.copernicus.eu/v1/>
- Documentación: <https://documentation.dataspace.copernicus.eu/APIs/STAC.html>
- Utilidad: descubrimiento de escenas, metadatos, fechas y productos. Procesar y validar imágenes para NBR/dNBR requiere pipeline independiente.

## Meteorología Open-Meteo

- <https://open-meteo.com/en/docs>
- Para el MVP se usa `api.open-meteo.com/v1/forecast` con bloque `current` (temperatura, humedad, velocidad y dirección de viento).
- El periodo histórico deberá consultar API apropiada en una siguiente fase.
- El plan sin clave se orienta a uso no comercial; antes de explotación comercial revisar términos, atribución y cuotas.

## CesiumJS y mapas

- API CesiumJS: <https://cesium.com/learn/cesiumjs-learn/cesiumjs-quickstart/>
- Token Cesium ion: <https://ion.cesium.com/tokens>.
- La cartografía base de OSM en este prototipo usa servidores comunitarios sólo para bajo tráfico de desarrollo, respetando attribution y caché: <https://operations.osmfoundation.org/policies/tiles/>.
- En producción usar un proveedor comercial/autohospedado que soporte cuota, crédito y uso de imágenes según términos.

## Reglas de interpretación

1. `FRP` representa potencia radiativa instantánea estimada, **no** energía acumulada ni hectáreas quemadas.
2. Una observación VIIRS/MODIS puede presentar latencia, incertidumbre, falsos positivos y omisiones.
3. Un polígono de una temporada no representa necesariamente la expansión temporal precisa del fuego.
4. Los mapas regionales preliminares basados en bbox pueden incluir territorio argentino/vecino. Sustituir por geometrías reales antes de publicar.
5. Las respuestas de API deben documentar versiones, proveedor, fecha de consulta y estado parcial. Nunca simular detecciones reales para llenar el mapa.

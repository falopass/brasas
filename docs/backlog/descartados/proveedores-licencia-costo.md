# Proveedores descartados por licencia, costo o cobertura (revisión 18-11-2026)

Registro de fuentes evaluadas en la revisión del `18-11-2026` (`CONSOLIDADO.md`, `atmosfera.md` y `mapa.md`) que **no deben integrarse** en BRASA por incompatibilidad de licencia, costo o falta de cobertura en Chile. Se documentan aquí para evitar reevaluarlas sin un cambio explícito de sus términos.

## Descartados por licencia o costo

| Proveedor | Qué aportaba | Motivo de descarte | Enlace de verificación |
|---|---|---|---|
| **PurpleAir API** | Sensores densos de PM2,5 en ciudades chilenas (~2 min) | Modelo de pago por puntos sin plan gratuito para aplicaciones públicas; su licencia prohíbe redistribuir datos crudos o exponerlos en apps públicas sin acuerdo comercial específico. Nota: al usar OpenAQ v3 (`OFI-38`) deben filtrarse fuera los sensores de terceros con esta restricción. | <https://api.purpleair.com/> |
| **IQAir AirVisual API** | Índice AQI / PM2,5 por ciudad | Plan gratuito *Community* (500 llamadas/día) restringido a uso personal sin redistribución ni publicación en app ciudadana; uso público requiere planes pagos (*Startup* / *Enterprise*) y duplica datos oficiales de SINCA. | <https://www.iqair.com/commercial-air-quality-monitors/api> |
| **Windy API** | Modelos numéricos (GFS, ICON, AROME, CAMS) | El plan gratuito de prueba (500 req/día) altera y desordena aleatoriamente los valores (inutilizable en emergencias); el plan Pro cuesta 990 EUR/año (10.000 req/día), excluye ECMWF en Point Forecast API y restringe redistribuir datos crudos. Open-Meteo y los datos directos ECMWF/GFS cubren mejor esta necesidad. | <https://api.windy.com/> |
| **Blitzortung** | Red terrestre VLF de rayos (~1 km de precisión) | Sus Términos de Uso prohíben explícitamente el uso comercial, el *scraping* y la conexión desde aplicaciones o sitios web de terceros, incluso para operadores de estaciones. Se mantiene GOES-19 / GOES-18 `GLM-L2-LCFA` (dominio público NOAA). | <https://www.blitzortung.org/en/terms_of_use.php> |
| **OroraTech** | Detección satelital térmica infrarroja comercial | Plataforma comercial sin acceso abierto gratuito verificable para aplicaciones ciudadanas (licencia y tarifas comerciales por confirmar solo si existiera convenio institucional). | <https://ororatech.com/> |
| **Esri World Imagery** | Mosaico satelital submétrico (<1 m) | Licencia propietaria / no abierta; el nivel gratuito (*ArcGIS Location Platform / Developer Essentials*) exige API Key para pruebas no comerciales, limita transacciones y prohíbe cachear teselas offline. | <https://developers.arcgis.com/> |
| **Satellogic** | Imágenes satelitales comerciales de muy alta resolución | Servicio comercial sin nivel abierto gratuito ni licencia de redistribución pública verificada (términos comerciales por confirmar). | <https://satellogic.com/> |
| **EOxCloudless 2024** | Mosaico Sentinel-2 global actualizado a 2024 | Licenciado bajo **CC BY-NC-SA 4.0** (solo no comercial y *share-alike*), incompatible con mantener el fondo satelital de BRASA bajo licencia abierta sin restricción NC (`NEG-05` eligió `EOxCloudless 2016`, CC BY 4.0, complementado ahora con NASA GIBS en `MAPA-180`). | <https://cloudless.eox.at/documentation/faq> |
| **IGM Chile (cartografía base)** | Toponimia e hidrografía oficial 1:50.000 | Sin licencia abierta explícita para reutilización masiva en aplicaciones web públicas (sujeto a propiedad intelectual del IGM salvo autorización formal). | <https://www.igm.cl/> |

## Fuentes revisadas sin cobertura útil sobre Chile (no integrar)

Documentadas en `CONSOLIDADO.md` y `atmosfera.md` para referencia técnica:

- **NOAA HRRR-Smoke:** cubre únicamente EE. UU. continental y Alaska (sustituido para Chile por `GOES-19 ABI-L2-AODF` en `DET-48` y `NOAA GEFS-Aerosols` en `ATMOS-01`).
- **EFFIS:** enfoque europeo/mediterráneo; para Chile corresponde **GWIS** (`OFI-34`).
- **Meteosat** y **Himawari:** satélites geoestacionarios fuera del hemisferio americano (cubierto por GOES-19 y GOES-18).
- **NOAA HMS (Hazard Mapping System):** análisis manual de humo centrado en Norteamérica.
- **FIRMS `LANDSAT_NRT` / `LANDSAT_URT`:** según NASA, cobertura NRT limitada a EE. UU. y Canadá.
